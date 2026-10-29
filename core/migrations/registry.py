from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Migration registry: step definitions, runner, and result types."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from core.migrations.tracker import MigrationTracker

logger = logging.getLogger(__name__)

# ── Data models ─────────────────────────────────────────────


@dataclass
class StepResult:
    """Result of a single migration step execution."""

    changed: int
    skipped: int
    details: list[str]
    error: str | None = None


@dataclass
class MigrationStep:
    """A single migration step with metadata."""

    id: str
    name: str
    category: str  # "structural", "per_anima", "template_sync", "db_sync", "version"
    fn: Callable[[Path, bool, bool], StepResult]


@dataclass
class MigrationReport:
    """Aggregate report for an entire migration run."""

    steps: list[tuple[MigrationStep, StepResult]] = field(default_factory=list)
    total_changed: int = 0
    total_skipped: int = 0
    errors: list[str] = field(default_factory=list)


# ── Runner ──────────────────────────────────────────────────


class MigrationRunner:
    """Execute migration steps in order with dry-run support."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.tracker = MigrationTracker(data_dir)
        self._steps: list[MigrationStep] = []

    def register(self, step: MigrationStep) -> None:
        self._steps.append(step)

    # ── Execution ───────────────────────────────────────────

    def run_all(
        self,
        *,
        dry_run: bool = False,
        verbose: bool = False,
        force: bool = False,
    ) -> MigrationReport:
        """Run all registered steps.

        Steps already recorded in ``migration_state.json`` are skipped
        unless *force* is ``True``.
        """
        return self._run(
            self._steps,
            dry_run=dry_run,
            verbose=verbose,
            force=force,
        )

    def list_steps(self) -> list[dict]:
        """Return metadata for every registered step."""
        state = self.tracker.load()
        out: list[dict] = []
        for s in self._steps:
            applied_at = state.steps_applied.get(s.id)
            out.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "category": s.category,
                    "applied": applied_at is not None,
                    "applied_at": applied_at or "",
                }
            )
        return out

    # ── Internal ────────────────────────────────────────────

    def _run(
        self,
        steps: list[MigrationStep],
        *,
        dry_run: bool,
        verbose: bool,
        force: bool = False,
    ) -> MigrationReport:
        report = MigrationReport()
        for step in steps:
            if not force and self.tracker.is_step_applied(step.id):
                result = StepResult(changed=0, skipped=1, details=["already applied"])
                report.steps.append((step, result))
                report.total_skipped += 1
                logger.debug("[%s] skipped (already applied)", step.name)
                continue

            try:
                result = step.fn(self.data_dir, dry_run, verbose)
            except Exception as exc:
                logger.exception("[%s] unhandled error", step.name)
                result = StepResult(changed=0, skipped=0, details=[], error=str(exc))

            report.steps.append((step, result))
            report.total_changed += result.changed
            report.total_skipped += result.skipped

            if result.error:
                report.errors.append(f"{step.name}: {result.error}")
                logger.error("[%s] error: %s", step.name, result.error)
            elif not dry_run and result.changed > 0:
                self.tracker.mark_applied(step.id)

            logger.info(
                "[%s] changed=%d skipped=%d%s",
                step.name,
                result.changed,
                result.skipped,
                f" ERROR={result.error}" if result.error else "",
            )

        return report
