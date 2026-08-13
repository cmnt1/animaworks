from __future__ import annotations

import argparse
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from cli.commands.mcp_cmd import mcp_command


def test_mcp_command_sets_environment_without_running_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    anima_dir = tmp_path / "animas" / "librarian"
    anima_dir.mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    for name in ("ANIMAWORKS_ANIMA_DIR", "ANIMAWORKS_MCP_PROJECT", "ANIMAWORKS_MCP_TOOLS"):
        monkeypatch.delenv(name, raising=False)
    for name in ("ANIMAWORKS_VECTOR_URL", "ANIMAWORKS_EMBED_URL", "ANIMAWORKS_RERANK_URL"):
        monkeypatch.delenv(name, raising=False)
    args = argparse.Namespace(
        anima="librarian",
        project="animaworks",
        tools="search_memory,read_memory_file",
    )

    with (
        patch("cli.commands.mcp_cmd._setup_server_delegation", return_value=False) as delegation,
        patch("core.mcp.server.main", new=AsyncMock()) as server_main,
    ):
        mcp_command(args)

    delegation.assert_called_once_with()
    server_main.assert_awaited_once_with()
    assert capsys.readouterr().out == ""
    assert os.environ["ANIMAWORKS_ANIMA_DIR"] == str(anima_dir)
    assert os.environ["ANIMAWORKS_MCP_PROJECT"] == "animaworks"
    assert os.environ["ANIMAWORKS_MCP_TOOLS"] == "search_memory,read_memory_file"
    assert "ANIMAWORKS_VECTOR_URL" not in os.environ
    for name in ("ANIMAWORKS_ANIMA_DIR", "ANIMAWORKS_MCP_PROJECT", "ANIMAWORKS_MCP_TOOLS"):
        os.environ.pop(name, None)


def test_mcp_command_rejects_missing_anima(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    args = argparse.Namespace(anima="missing", project=None, tools="search_memory")

    with pytest.raises(SystemExit, match="1"):
        mcp_command(args)
