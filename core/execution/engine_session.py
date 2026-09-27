from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared operations for persisted engine sessions."""

import logging
from dataclasses import dataclass
from pathlib import Path

from core.execution.session_store import SessionEngine, SessionStore
from core.execution.session_types import is_resumable_trigger, resolve_runtime_session_type

logger = logging.getLogger(__name__)

MAX_RESUME_TURNS = 10
_ENGINE_SESSIONS: tuple[SessionEngine, ...] = ("agent_sdk", "codex", "cursor", "grok")


@dataclass(frozen=True)
class ResumeDecision:
    """Session state loaded before a turn-limited engine execution."""

    session_id: str | None
    turn_count: int
    resumable: bool
    rotated: bool


def clear_engine_session(
    anima_dir: Path,
    engine: SessionEngine,
    session_type: str,
    thread_id: str = "default",
) -> None:
    """Clear one engine's persisted session while preserving its storage format."""
    if engine == "agent_sdk":
        # Keep the SDK's state lock and metadata-aware cleanup as the authority.
        from core.execution.engines.claude._sdk_session import _clear_session_id

        _clear_session_id(anima_dir, session_type, thread_id)
        return
    SessionStore(SessionStore.path_for(engine, anima_dir, session_type, thread_id)).clear()


def clear_all_engine_sessions(anima_dir: Path, session_type: str, thread_id: str = "default") -> None:
    """Best-effort cleanup of one session namespace across all engines."""
    for engine in _ENGINE_SESSIONS:
        try:
            clear_engine_session(anima_dir, engine, session_type, thread_id)
        except Exception:
            logger.debug(
                "Failed to clear %s session (%s/%s)",
                engine,
                session_type,
                thread_id,
                exc_info=True,
            )


def load_turn_limited_session(
    anima_dir: Path,
    engine: SessionEngine,
    trigger: str,
    thread_id: str,
    *,
    max_turns: int = MAX_RESUME_TURNS,
) -> ResumeDecision:
    """Load a resumable text session and rotate it once its turn limit is reached."""
    resumable = is_resumable_trigger(trigger)
    if not resumable:
        return ResumeDecision(session_id=None, turn_count=0, resumable=False, rotated=False)

    store = SessionStore(SessionStore.path_for(engine, anima_dir, resolve_runtime_session_type(trigger), thread_id))
    record = store.read_text_record(with_turn_count=True, ignore_read_errors=True)
    if record is None:
        return ResumeDecision(session_id=None, turn_count=0, resumable=True, rotated=False)
    if SessionStore.turn_limit_reached(record.turn_count, max_turns):
        store.clear()
        return ResumeDecision(session_id=None, turn_count=0, resumable=True, rotated=True)
    return ResumeDecision(
        session_id=record.session_id,
        turn_count=record.turn_count,
        resumable=True,
        rotated=False,
    )


def next_turn_count(
    decision: ResumeDecision,
    *,
    resumed: bool,
    rotated_during_run: bool,
) -> tuple[int, bool]:
    """Return the saved turn count and whether the session should rotate next turn."""
    rotated = decision.rotated or rotated_during_run
    new_turn = 1 if rotated or not resumed else decision.turn_count + 1
    rotation_pending = decision.resumable and not rotated and new_turn >= MAX_RESUME_TURNS
    return new_turn, rotation_pending
