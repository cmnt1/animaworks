from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for _persist_replied_to_for_a1 in CLI messaging module."""

import json
import os
from pathlib import Path
from unittest.mock import patch


class TestPersistRepliedToForA1:
    """Test _persist_replied_to_for_a1() writes to replied_to.jsonl."""

    def _path(self, root: Path, session_type: str = "unknown", thread_id: str = "default") -> Path:
        return root / "run" / "replied_to" / session_type / f"{thread_id}.jsonl"

    def _call(self, to: str) -> None:
        from cli.commands.messaging import _persist_replied_to_for_a1

        _persist_replied_to_for_a1(to)

    def test_writes_entry_when_env_set(self, tmp_path: Path) -> None:
        """When ANIMAWORKS_ANIMA_DIR is set, the function writes a JSONL entry."""
        with patch.dict(os.environ, {"ANIMAWORKS_ANIMA_DIR": str(tmp_path)}):
            self._call("mio")

        path = self._path(tmp_path)
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry == {
            "to": "mio",
            "success": True,
            "session_type": "unknown",
            "thread_id": "default",
            "request_id": "",
        }

    def test_appends_multiple_entries(self, tmp_path: Path) -> None:
        """Multiple calls append to the same file."""
        with patch.dict(os.environ, {"ANIMAWORKS_ANIMA_DIR": str(tmp_path)}):
            self._call("alice")
            self._call("bob")
            self._call("charlie")

        path = self._path(tmp_path)
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        names = [json.loads(line)["to"] for line in lines]
        assert names == ["alice", "bob", "charlie"]

    def test_noop_when_env_not_set(self, tmp_path: Path) -> None:
        """When ANIMAWORKS_ANIMA_DIR is not set, nothing is written."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANIMAWORKS_ANIMA_DIR", None)
            self._call("mio")

        # No run/ directory should be created anywhere
        assert not (tmp_path / "run").exists()

    def test_creates_run_directory(self, tmp_path: Path) -> None:
        """The run/ directory is created if it doesn't exist."""
        assert not (tmp_path / "run").exists()
        with patch.dict(os.environ, {"ANIMAWORKS_ANIMA_DIR": str(tmp_path)}):
            self._call("yuki")
        assert self._path(tmp_path).exists()

    def test_handles_write_error_gracefully(self, tmp_path: Path) -> None:
        """If writing fails, the function logs but does not raise."""
        # Point to a non-writable path
        bad_path = tmp_path / "readonly"
        bad_path.mkdir()
        readonly_file = self._path(bad_path)
        readonly_file.parent.mkdir(parents=True)
        readonly_file.touch()
        readonly_file.chmod(0o000)
        try:
            with patch.dict(os.environ, {"ANIMAWORKS_ANIMA_DIR": str(bad_path)}):
                # Should not raise
                self._call("mio")
        finally:
            readonly_file.chmod(0o644)

    def test_format_matches_toolhandler(self, tmp_path: Path) -> None:
        """Output format must match ToolHandler._persist_replied_to()."""
        with patch.dict(os.environ, {"ANIMAWORKS_ANIMA_DIR": str(tmp_path)}):
            self._call("test-anima")

        path = self._path(tmp_path)
        entry = json.loads(path.read_text(encoding="utf-8").strip())
        # Must have exactly these keys (same as ToolHandler format)
        assert set(entry.keys()) == {"to", "success", "session_type", "thread_id", "request_id"}
        assert isinstance(entry["to"], str)
        assert isinstance(entry["success"], bool)

    def test_uses_runtime_session_env(self, tmp_path: Path) -> None:
        """Runtime session env scopes the bridge file."""
        env = {
            "ANIMAWORKS_ANIMA_DIR": str(tmp_path),
            "ANIMAWORKS_REQUEST_ID": "req-123",
            "ANIMAWORKS_SESSION_TYPE": "chat",
            "ANIMAWORKS_THREAD_ID": "thread-a",
            "ANIMAWORKS_TRIGGER": "message:mio",
            "ANIMAWORKS_TOOL_SESSION_ID": "tool-123",
        }
        with patch.dict(os.environ, env):
            self._call("mio")

        path = self._path(tmp_path, "chat", "thread-a")
        entry = json.loads(path.read_text(encoding="utf-8").strip())
        assert entry["to"] == "mio"
        assert entry["session_type"] == "chat"
        assert entry["thread_id"] == "thread-a"
        assert entry["request_id"] == "req-123"
