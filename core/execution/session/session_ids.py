from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Engine-specific session identifier persistence over the shared store."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.execution.session.session_store import SessionEngine, SessionRecord, SessionStore


@dataclass(frozen=True)
class EngineSessionIds:
    """Read and write an engine's IDs using its established file layout.

    Codex stores a single-line thread ID; Cursor and Grok also persist a turn
    count. Mode S stores a JSON state document with context measurements, so
    its state methods intentionally expose that document to the SDK-specific
    metadata layer instead of flattening it to a text record.
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

    def save(
        self,
        anima_dir: Path,
        session_id: str,
        session_type: str,
        thread_id: str = "default",
        turn_count: int = 1,
    ) -> None:
        """Save a text-format ID without changing its established wire format."""
        if self.engine == "agent_sdk":
            raise ValueError("Mode S uses save_state() for its metadata-bearing JSON file")
        SessionStore(self.path_for(anima_dir, session_type, thread_id)).write_text_record(
            SessionRecord(session_id, turn_count),
            with_turn_count=self.engine in {"cursor", "grok"},
        )

    def load_state(self, anima_dir: Path, session_type: str, thread_id: str = "default") -> dict[str, Any] | None:
        """Load Mode S's metadata-bearing JSON session document."""
        if self.engine != "agent_sdk":
            raise ValueError("load_state() is only supported for Mode S")
        try:
            data = SessionStore(self.path_for(anima_dir, session_type, thread_id)).read_json()
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def save_state(
        self,
        anima_dir: Path,
        session_type: str,
        state: dict[str, Any],
        thread_id: str = "default",
    ) -> None:
        """Atomically save Mode S's metadata-bearing JSON session document."""
        if self.engine != "agent_sdk":
            raise ValueError("save_state() is only supported for Mode S")
        SessionStore(self.path_for(anima_dir, session_type, thread_id)).write_json(state)

    def clear(self, anima_dir: Path, session_type: str, thread_id: str = "default") -> None:
        """Remove the persisted ID while leaving its path and format unchanged."""
        SessionStore(self.path_for(anima_dir, session_type, thread_id)).clear()
