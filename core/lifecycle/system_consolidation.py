from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.
import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.config import load_config
from core.config.models import ConsolidationConfig

logger = logging.getLogger("animaworks.lifecycle")


def is_consolidation_enabled(anima_dir: Path) -> bool:
    """Resolve the per-Anima consolidation switch without credential lookup.

    ``status.json`` remains the strongest override, followed by
    ``anima_defaults.consolidation_enabled``. Errors retain the
    backward-compatible default of enabled.
    """
    try:
        status = json.loads((anima_dir / "status.json").read_text(encoding="utf-8"))
        override = status.get("consolidation_enabled")
        if isinstance(override, bool):
            return override
    except (OSError, json.JSONDecodeError):
        pass
    try:
        return load_config().anima_defaults.consolidation_enabled
    except Exception:
        logger.debug("Failed to resolve consolidation default for %s", anima_dir.name, exc_info=True)
        return True


def has_recent_activity(anima_dir: Path, *, days: int = 7, now: datetime | None = None) -> bool:
    """Return whether activity_log contains a timestamped entry in the window."""
    from core.time_utils import now_local

    current = now or now_local()
    cutoff = current - timedelta(days=max(1, days))
    log_dir = anima_dir / "activity_log"
    if not log_dir.is_dir():
        return False

    for log_path in sorted(log_dir.glob("*.jsonl"), reverse=True):
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            logger.debug("Failed to inspect activity log %s", log_path, exc_info=True)
            continue
        for line in reversed(lines):
            try:
                raw_ts = json.loads(line).get("ts")
                timestamp = datetime.fromisoformat(raw_ts) if isinstance(raw_ts, str) else None
                if timestamp is not None and timestamp.tzinfo is not None and timestamp >= cutoff:
                    return True
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
    return False


def should_skip_inactive_consolidation(
    anima_dir: Path,
    anima_name: str,
    consolidation_cfg: Any,
) -> bool:
    """Apply per-Anima disable and configurable inactivity guards."""
    if not is_consolidation_enabled(anima_dir):
        logger.info("Consolidation skipped for %s: consolidation_enabled=false", anima_name)
        return True

    defaults = ConsolidationConfig()
    enabled = getattr(consolidation_cfg, "inactivity_skip_enabled", defaults.inactivity_skip_enabled)
    days = getattr(consolidation_cfg, "inactivity_days", defaults.inactivity_days)
    if enabled and not has_recent_activity(anima_dir, days=days):
        logger.info(
            "Consolidation skipped for %s: no activity_log entries in the last %d days",
            anima_name,
            days,
        )
        return True
    return False


@dataclass(frozen=True)
class DailyConsolidationGate:
    """Decision details for daily consolidation eligibility."""

    should_run: bool
    activity_count: int
    episode_count: int
    threshold: int
    pending_backfill_days: int = 0


def evaluate_daily_consolidation_gate(
    anima_dir: Path,
    anima_name: str,
    *,
    threshold: int,
    hours: int = 24,
    backfill_days: int = 1,
    model: str | None = None,
    max_input_bytes: int = 200 * 1024,
    exclude_noop_cron: bool = False,
) -> DailyConsolidationGate:
    """Return whether daily consolidation should run for one anima.

    A pending unprocessed activity chunk within the configured recovery window
    also makes the daily job eligible, even when yesterday itself was quiet.
    """
    from core.memory.maintenance.consolidation import ConsolidationEngine

    engine = ConsolidationEngine(anima_dir, anima_name)
    episode_count = 0
    activity_count = 0
    try:
        episode_count = len(engine._collect_recent_episodes(hours=hours))
    except Exception:
        logger.debug("Failed to count recent episodes for %s", anima_name, exc_info=True)
    try:
        target_date, window_start, window_end = engine.previous_local_day_window()
        activity_count = engine.count_recent_activity_entries(
            hours=hours,
            since=window_start,
            until=window_end,
        )
    except Exception:
        target_date = None
        logger.debug("Failed to count recent activity entries for %s", anima_name, exc_info=True)

    pending_backfill_days = 0
    if backfill_days > 1 and target_date is not None and callable(getattr(engine, "local_day_window", None)):
        try:
            for offset in range(max(1, backfill_days)):
                candidate_date = target_date - timedelta(days=offset)
                pending, _filter_applied = engine.collect_pending_activity_chunks(
                    candidate_date,
                    model=model,
                    max_input_bytes=max_input_bytes,
                    exclude_noop_cron=exclude_noop_cron,
                )
                if pending:
                    pending_backfill_days += 1
        except Exception:
            logger.debug("Failed to inspect episode backfill window for %s", anima_name, exc_info=True)
            pending_backfill_days = 0

    return DailyConsolidationGate(
        should_run=activity_count >= threshold or episode_count >= threshold or pending_backfill_days > 0,
        activity_count=activity_count,
        episode_count=episode_count,
        threshold=threshold,
        pending_backfill_days=pending_backfill_days,
    )


def resolve_post_processing_cooldown_seconds(consolidation_cfg: Any) -> float:
    """Return configured cooldown between daily post-processing runs."""
    default = ConsolidationConfig().post_processing_cooldown_seconds
    value = (
        getattr(consolidation_cfg, "post_processing_cooldown_seconds", default)
        if consolidation_cfg is not None
        else default
    )
    if not isinstance(value, int | float):
        return float(default)
    return float(max(0, value))


async def run_daily_consolidation_post_processing(
    anima_name: str,
    anima_dir: Path,
    *,
    consolidation_cfg: Any,
    model: str,
) -> None:
    """Run framework-side daily consolidation post-processing."""
    if getattr(consolidation_cfg, "synaptic_downscaling_enabled", False) is True:
        try:
            from core.memory.maintenance.forgetting import ForgettingEngine

            forgetter = ForgettingEngine(anima_dir, anima_name)
            # The ForgettingEngine uses synchronous vector operations which must run
            # on a worker thread: inside the server process the vector store is
            # bridged to the owner event loop, so calling it directly on the
            # root loop raises (and silently scans 0 chunks).
            downscaling_result = await asyncio.to_thread(forgetter.synaptic_downscaling)
            logger.info("Synaptic downscaling for %s: %s", anima_name, downscaling_result)
        except Exception:
            logger.exception("Synaptic downscaling failed for anima=%s", anima_name)

    await run_knowledge_self_correction_if_enabled(
        anima_dir,
        anima_name,
        consolidation_cfg,
        model=model,
    )


async def run_weekly_integration_post_processing(
    anima_name: str,
    anima_dir: Path,
    *,
    consolidation_cfg: Any,
    model: str,
) -> None:
    """Run framework-side weekly integration post-processing."""
    if getattr(consolidation_cfg, "weekly_distillation_enabled", False) is True:
        await run_weekly_pattern_distillation(anima_dir, anima_name, model=model)


async def run_weekly_pattern_distillation(
    anima_dir: Path,
    anima_name: str,
    *,
    model: str,
) -> None:
    """Distill repeated activity patterns into procedures during weekly post-processing."""
    try:
        from core.memory.maintenance.distillation import ProceduralDistiller

        distiller = ProceduralDistiller(anima_dir, anima_name)
        result = await distiller.weekly_pattern_distill(model=model, days=7)
        logger.info("Weekly pattern distillation for %s: %s", anima_name, result)
    except Exception:
        logger.exception("Weekly pattern distillation failed for anima=%s", anima_name)


async def run_knowledge_self_correction_if_enabled(
    anima_dir: Path,
    anima_name: str,
    consolidation_cfg: Any,
    *,
    model: str,
) -> None:
    """Run post-consolidation knowledge correction when enabled."""
    default_cfg = ConsolidationConfig()
    if consolidation_cfg is not None:
        enabled = getattr(consolidation_cfg, "knowledge_self_correction_enabled", True)
    else:
        enabled = default_cfg.knowledge_self_correction_enabled
    if not enabled:
        return

    try:
        from core.lifecycle.knowledge_correction import (
            KnowledgeCorrectionLimits,
            run_post_consolidation_knowledge_correction,
        )

        limits = KnowledgeCorrectionLimits(
            max_reconsolidation_files=getattr(
                consolidation_cfg,
                "knowledge_self_correction_max_reconsolidation_files",
                default_cfg.knowledge_self_correction_max_reconsolidation_files,
            ),
            timeout_seconds=float(
                getattr(
                    consolidation_cfg,
                    "knowledge_self_correction_timeout_seconds",
                    default_cfg.knowledge_self_correction_timeout_seconds,
                )
            ),
        )
        result = await run_post_consolidation_knowledge_correction(
            anima_dir,
            anima_name,
            model=model,
            limits=limits,
        )
        logger.info("Knowledge self-correction post-processing for %s: %s", anima_name, result)
    except Exception:
        logger.exception("Knowledge self-correction failed for anima=%s", anima_name)
