"""Unit tests for Mode A tool output limits aligned with Mode S (Claude Code)."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.tooling.handler import ToolHandler
from core.tooling.handler_base import (
    _CMD_HEAD_BYTES,
    _CMD_TAIL_BYTES,
    _CMD_TRUNCATE_BYTES,
    _GLOB_MAX_ENTRIES,
    _GREP_MAX_MATCHES,
)


def _make_handler(tmp_path: Path) -> ToolHandler:
    """Create a ToolHandler with minimal mocked dependencies."""
    anima_dir = tmp_path / "animas" / "test"
    anima_dir.mkdir(parents=True)
    (anima_dir / "permissions.md").write_text("", encoding="utf-8")

    memory = MagicMock()
    memory.read_permissions.return_value = ""
    memory.search_memory_text.return_value = []

    return ToolHandler(
        anima_dir=anima_dir,
        memory=memory,
        messenger=None,
        tool_registry=[],
    )


class TestMaxToolOutputBytes:
    """Verify _MAX_TOOL_OUTPUT_BYTES is 50_000."""

    def test_max_tool_output_bytes_is_50k(self) -> None:
        assert ToolHandler._MAX_TOOL_OUTPUT_BYTES == 50_000


class TestExecuteCommandTruncation:
    """Verify execute_command output is truncated at 10KB with head/tail split."""

    def test_execute_command_output_truncated_at_10kb_with_head_tail(self, tmp_path: Path) -> None:
        """Output exceeding 10KB is truncated with head + tail format."""
        handler = _make_handler(tmp_path)
        handler._memory.read_permissions.return_value = "## コマンド実行\n- echo: OK"

        # Create output > 10KB (e.g. 15KB)
        long_output = "x" * 15_000

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (long_output, "")
        mock_proc.returncode = 0

        with (
            patch("core.tooling.handler_files._rewrite_command_with_rtk", side_effect=lambda c: (c, False)),
            patch("core.tooling.handler_files.subprocess.Popen", return_value=mock_proc),
        ):
            result = handler.handle("execute_command", {"command": "echo x"})

        assert len(result.encode("utf-8", errors="replace")) < len(long_output.encode("utf-8"))
        assert "... [truncated:" in result
        assert "bytes total] ..." in result
        # Head portion (5KB) should be present at start
        assert result.startswith("x")
        # Tail portion (3KB) appears after the truncation marker
        assert "15000" in result

    def test_execute_command_output_under_limit_not_truncated(self, tmp_path: Path) -> None:
        """Output under 10KB is returned as-is."""
        handler = _make_handler(tmp_path)
        handler._memory.read_permissions.return_value = "## コマンド実行\n- echo: OK"

        short_output = "hello world"

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (short_output, "")
        mock_proc.returncode = 0

        with (
            patch("core.tooling.handler_files._rewrite_command_with_rtk", side_effect=lambda c: (c, False)),
            patch("core.tooling.handler_files.subprocess.Popen", return_value=mock_proc),
        ):
            result = handler.handle("execute_command", {"command": "echo hello"})

        assert result == short_output


class TestSearchCodeMaxMatches:
    """Verify search_code returns max 200 matches."""

    def test_search_code_caps_at_200_matches(self, tmp_path: Path) -> None:
        """When more than 200 matches exist, result is capped at 200."""
        handler = _make_handler(tmp_path)
        anima_dir = tmp_path / "animas" / "test"

        # Create a file with 250 lines each containing "match"
        lines = [f"line {i} match here" for i in range(250)]
        (anima_dir / "many_matches.py").write_text("\n".join(lines), encoding="utf-8")

        result = handler.handle("search_code", {"pattern": "match"})

        match_lines = [
            ln
            for ln in result.splitlines()
            if "match" in ln and ln.strip() and not ln.strip().startswith("(truncated at")
        ]
        assert len(match_lines) == _GREP_MAX_MATCHES
        assert "truncated at 200 matches" in result


class TestListDirectoryMaxEntries:
    """Verify list_directory returns max 500 entries."""

    def test_list_directory_caps_at_500_entries(self, tmp_path: Path) -> None:
        """When more than 500 entries exist, result is capped at 500."""
        handler = _make_handler(tmp_path)
        anima_dir = tmp_path / "animas" / "test"
        subdir = anima_dir / "many_files"
        subdir.mkdir(parents=True)

        # Create 600 files
        for i in range(600):
            (subdir / f"file_{i:04d}.txt").write_text("x", encoding="utf-8")

        result = handler.handle("list_directory", {"path": str(subdir), "recursive": False})

        lines = [
            ln
            for ln in result.splitlines()
            if ln.strip()
            and ln != "(empty directory)"
            and not ln.strip().startswith("(truncated at")
        ]
        assert len(lines) == _GLOB_MAX_ENTRIES
        assert "truncated at 500 entries" in result
        assert "total: 600" in result


class TestConstantsValues:
    """Verify Mode S-aligned constant values."""

    def test_cmd_truncate_bytes(self) -> None:
        assert _CMD_TRUNCATE_BYTES == 10_000

    def test_cmd_head_bytes(self) -> None:
        assert _CMD_HEAD_BYTES == 5_000

    def test_cmd_tail_bytes(self) -> None:
        assert _CMD_TAIL_BYTES == 3_000

    def test_grep_max_matches(self) -> None:
        assert _GREP_MAX_MATCHES == 200

    def test_glob_max_entries(self) -> None:
        assert _GLOB_MAX_ENTRIES == 500
