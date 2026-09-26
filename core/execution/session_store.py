from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""L1 persistence primitives for engine session identifiers."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SessionEngine = Literal["agent_sdk", "codex", "cursor", "grok"]


@dataclass(frozen=True)
class SessionRecord:
    """Persisted engine session ID and its optional turn counter."""

    session_id: str
    turn_count: int = 0


class SessionStore:
    """Shared file store while retaining each engine's established file format.

    The paths and serializers here intentionally mirror the existing S/C/D/X
    layouts.  In particular, changing a path or text-file shape would break
    session resume for existing Anima directories.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def sdk_state_filename(session_type: str, thread_id: str = "default") -> str:
        """Return the established S session-state filename."""
        if thread_id != "default":
            return f"current_session_{session_type}_{thread_id}.json"
        return f"current_session_{session_type}.json"

    @staticmethod
    def path_for(
        engine: SessionEngine,
        anima_dir: Path,
        session_type: str,
        thread_id: str = "default",
    ) -> Path:
        """Return the existing persistence path for an engine session."""
        if engine == "agent_sdk":
            return anima_dir / "state" / SessionStore.sdk_state_filename(session_type, thread_id)

        base = anima_dir / "shortterm" / session_type
        if engine == "codex":
            filename = "codex_thread_id.txt"
            if thread_id != "default":
                return base / thread_id / filename
            return base / filename
        if engine == "cursor":
            filename = "cursor_chat_id.txt"
            if thread_id != "default":
                return base / thread_id / filename
            return base / filename
        if engine == "grok":
            return base / thread_id / "grok_session_id.txt"
        raise ValueError(f"unsupported session engine: {engine}")

    @staticmethod
    def turn_limit_reached(turn_count: int, max_turns: int) -> bool:
        """Whether a D/X resumable session has reached its turn limit."""
        return turn_count >= max_turns

    @staticmethod
    def prompt_size_exceeded(prompt_size: int, prompt_limit: int) -> bool:
        """Whether C must start a fresh session to avoid oversized resume."""
        return prompt_size > prompt_limit

    def read_text_record(
        self,
        *,
        with_turn_count: bool,
        ignore_read_errors: bool = False,
    ) -> SessionRecord | None:
        """Load a legacy text session file, optionally including its turn line."""
        if not self.path.is_file():
            return None
        try:
            contents = self.path.read_text(encoding="utf-8")
        except OSError:
            if ignore_read_errors:
                return None
            raise

        if with_turn_count:
            lines = contents.strip().splitlines()
            session_id = lines[0].strip() if lines else ""
            if not session_id:
                return None
            try:
                turn_count = int(lines[1].strip()) if len(lines) > 1 else 0
            except (ValueError, IndexError):
                turn_count = 0
            return SessionRecord(session_id, turn_count)

        session_id = contents.strip()
        return SessionRecord(session_id) if session_id else None

    def write_text_record(self, record: SessionRecord, *, with_turn_count: bool) -> None:
        """Write a session ID using its pre-existing engine-specific text shape."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        contents = f"{record.session_id}\n{record.turn_count}" if with_turn_count else record.session_id
        self.path.write_text(contents, encoding="utf-8")

    def read_json(self) -> Any:
        """Read a JSON state file; callers retain their existing validation."""
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write_json(self, data: dict[str, Any]) -> None:
        """Atomically write JSON state, preserving the SDK's durable format."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp:
                temp_name = temp.name
                json.dump(data, temp, ensure_ascii=False)
                temp.write("\n")
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temp_name, self.path)
            temp_name = None
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass

    def clear(self) -> None:
        """Remove this engine session file if it exists."""
        self.path.unlink(missing_ok=True)
