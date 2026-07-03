# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Cross-process LLM rate guard (fleet-wide circuit breaker).

Records rate-limit / overload state for a provider *family* in a single shared
JSON file so every Anima process checks it before hammering the same shared
credential.  When one Anima hits a 429 the others skip that backend until the
recorded window expires, instead of amplifying the throttle across ~27
processes.

The guard is fail-open by design: any read or write error is swallowed and
treated as "not blocked".  A broken guard must never stop a healthy call — the
same lesson as the shared-knowledge-DB corruption cascade, where a self-heal
mechanism became the outage.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config.schemas import LlmRateGuardConfig

logger = logging.getLogger("animaworks.execution.rate_guard")

_STATE_FILENAME = "llm_rate_guard.json"


def _load_guard_config() -> LlmRateGuardConfig:
    """Load the guard config, falling back to defaults on any failure."""
    from core.config.schemas import LlmRateGuardConfig

    try:
        from core.config import load_config

        return load_config().llm_rate_guard
    except Exception:
        logger.debug("failed to load llm_rate_guard config; using defaults", exc_info=True)
        return LlmRateGuardConfig()


def _current_anima_name() -> str:
    """Best-effort identity for the ``updated_by`` field (observability only)."""
    name = os.environ.get("ANIMAWORKS_ANIMA_NAME")
    if name:
        return name
    anima_dir = os.environ.get("ANIMAWORKS_ANIMA_DIR")
    if anima_dir:
        return Path(anima_dir).name
    return "unknown"


class LlmRateGuard:
    """File-backed, fail-open rate guard keyed by provider family."""

    def __init__(
        self,
        *,
        config: LlmRateGuardConfig | None = None,
        path: Path | None = None,
    ) -> None:
        self._config = config
        self._path = path

    @property
    def config(self) -> LlmRateGuardConfig:
        if self._config is None:
            self._config = _load_guard_config()
        return self._config

    def _resolve_path(self) -> Path:
        if self._path is not None:
            return self._path
        from core.paths import get_shared_dir

        return get_shared_dir() / _STATE_FILENAME

    def blocked_remaining(self, provider_family: str) -> float:
        """Return seconds this family stays blocked, or ``0.0`` if free.

        Read-only: never rewrites the file (so normal calls only ``stat`` +
        read).  Any error is treated as "not blocked" (fail-open).
        """
        if not self.config.enabled:
            return 0.0
        try:
            state = self._read_state()
        except Exception:
            logger.debug("rate guard read failed; failing open", exc_info=True)
            return 0.0

        entry = state.get(provider_family)
        if not isinstance(entry, dict):
            return 0.0
        blocked_until = entry.get("blocked_until")
        if not isinstance(blocked_until, (int, float)):
            return 0.0
        remaining = float(blocked_until) - time.time()
        return remaining if remaining > 0 else 0.0

    def report_block(self, provider_family: str, seconds: float, reason: str) -> None:
        """Record a block for *provider_family* lasting *seconds*.

        ``seconds`` is clamped to ``[0, max_block_seconds]``; a non-positive
        value falls back to ``default_block_seconds``.  Writes are atomic
        (tmp + ``os.replace``); any failure is swallowed (fail-open) — the
        next successful ``report_block`` replaces the file wholesale.
        """
        cfg = self.config
        if not cfg.enabled:
            return

        try:
            block_s = float(seconds)
        except (TypeError, ValueError):
            block_s = float(cfg.default_block_seconds)
        if block_s <= 0:
            block_s = float(cfg.default_block_seconds)
        block_s = min(block_s, float(cfg.max_block_seconds))

        try:
            state = self._read_state()
        except Exception:
            logger.debug("rate guard read-before-write failed; starting fresh", exc_info=True)
            state = {}

        state[provider_family] = {
            "blocked_until": time.time() + block_s,
            "reason": reason,
            "updated_by": _current_anima_name(),
        }
        try:
            self._write_state(state)
        except Exception:
            logger.debug("rate guard write failed; failing open", exc_info=True)
            return
        logger.info(
            "LLM rate guard: %s blocked for %.0fs (%s)",
            provider_family,
            block_s,
            reason,
        )

    def _read_state(self) -> dict:
        path = self._resolve_path()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def _write_state(self, state: dict) -> None:
        path = self._resolve_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                logger.debug("failed to unlink temp guard file %s", tmp_path, exc_info=True)
            raise


_shared_guard: LlmRateGuard | None = None


def get_rate_guard() -> LlmRateGuard:
    """Return the process-wide shared rate guard (config resolved lazily)."""
    global _shared_guard
    if _shared_guard is None:
        _shared_guard = LlmRateGuard()
    return _shared_guard


__all__ = ["LlmRateGuard", "get_rate_guard"]
