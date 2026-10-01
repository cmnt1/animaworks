from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Engine-specific session identifier persistence over the shared StateWriter."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.execution.session.session_store import SessionEngine, SessionRecord, SessionStore
from core.platform.state_writer import get_state_writer, run_writer_sync


@dataclass(frozen=True)
class EngineSessionIds:
    """Read and write engine IDs using their established file layout.

    Codex stores a single-line thread ID; Cursor and Grok also persist a turn
    count. Mode S stores a JSON state document with context measurements.
    """

    engine: SessionEngine

    def path_for(self, anima_dir: Path, session_type: str, thread_id: str = "default") -> Path:
        """Return the existing engine-specific session path."""
        return SessionStore.path_for(self.engine, anima_dir, session_type, thread_id)

    def load(self, anima_dir: Path, session_type: str, thread_id: str = "default") -> SessionRecord | None:
        """Load a text-format session ID, including legacy turn-count formats."""
        if self.engine == "agent_sdk":
            raise ValueError("Mode S uses load_state() for its metadata-bearing JSON file")
        return SessionStore(self.path_for(anima_dir, session_type, thread_id)).read_text_record(
            with_turn_count=self.engine in {"cursor", "grok"},
            ignore_read_errors=self.engine in {"cursor", "grok"},
        )

    async def asave(
        self,
        anima_dir: Path,
        session_id: str,
        session_type: str,
        thread_id: str = "default",
        turn_count: int = 1,
    ) -> None:
        """Save a text-format ID through the process state writer."""
        if self.engine == "agent_sdk":
            raise ValueError("Mode S uses asave_state() for its metadata-bearing JSON file")
        await get_state_writer(anima_dir).save_session_record(
            self.engine,
            session_type,
            thread_id,
            {"session_id": session_id, "turn_count": turn_count},
        )

    def save(
        self,
        anima_dir: Path,
        session_id: str,
        session_type: str,
        thread_id: str = "default",
        turn_count: int = 1,
    ) -> None:
        """Synchronous compatibility adapter for local callers and tests."""
        writer = get_state_writer(anima_dir)
        run_writer_sync(writer, self.asave(anima_dir, session_id, session_type, thread_id, turn_count))

    def load_state(self, anima_dir: Path, session_type: str, thread_id: str = "default") -> dict[str, Any] | None:
        """Load Mode S's metadata-bearing JSON session document."""
        if self.engine != "agent_sdk":
            raise ValueError("load_state() is only supported for Mode S")
        try:
            data = SessionStore(self.path_for(anima_dir, session_type, thread_id)).read_json()
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    async def asave_state(
        self,
        anima_dir: Path,
        session_type: str,
        state: dict[str, Any],
        thread_id: str = "default",
    ) -> None:
        """Persist Mode S metadata through the process state writer."""
        if self.engine != "agent_sdk":
            raise ValueError("asave_state() is only supported for Mode S")
        await get_state_writer(anima_dir).save_session_record(
            self.engine,
            session_type,
            thread_id,
            state,
        )

    def save_state(
        self,
        anima_dir: Path,
        session_type: str,
        state: dict[str, Any],
        thread_id: str = "default",
    ) -> None:
        """Synchronous compatibility adapter for local callers and tests."""
        writer = get_state_writer(anima_dir)
        run_writer_sync(writer, self.asave_state(anima_dir, session_type, state, thread_id))

    async def aclear(self, anima_dir: Path, session_type: str, thread_id: str = "default") -> None:
        """Remove the persisted ID through the process state writer."""
        await get_state_writer(anima_dir).clear_session(self.engine, session_type, thread_id)

    def clear(self, anima_dir: Path, session_type: str, thread_id: str = "default") -> None:
        """Synchronous compatibility adapter for local callers and tests."""
        writer = get_state_writer(anima_dir)
        run_writer_sync(writer, self.aclear(anima_dir, session_type, thread_id))
