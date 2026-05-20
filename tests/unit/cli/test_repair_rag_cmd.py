from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from core.memory.rag.repair import RepairResult


def test_repair_rag_requires_full(capsys: pytest.CaptureFixture[str]) -> None:
    from cli.commands.repair_rag_cmd import repair_rag_command

    args = argparse.Namespace(anima="sora", full=False, shared=True)

    with pytest.raises(SystemExit) as exc:
        repair_rag_command(args)

    assert exc.value.code == 2
    assert "requires --full" in capsys.readouterr().err


def test_repair_rag_success(capsys: pytest.CaptureFixture[str]) -> None:
    from cli.commands.repair_rag_cmd import repair_rag_command

    service = MagicMock()
    service.repair_anima_if_allowed.return_value = RepairResult(
        status="success",
        anima_name="sora",
        reason="manual_repair_rag_cli",
        chunks_indexed=12,
        quarantine_path="/tmp/archive/vectordb-corrupt",
    )
    args = argparse.Namespace(anima="sora", full=True, shared=True)

    with patch("core.memory.rag.repair.get_repair_service", return_value=service):
        repair_rag_command(args)

    service.repair_anima_if_allowed.assert_called_once_with(
        "sora",
        reason="manual_repair_rag_cli",
        collection=None,
        source="cli",
        include_shared=True,
    )
    assert "RAG repair succeeded" in capsys.readouterr().out


def test_repair_rag_failure_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    from cli.commands.repair_rag_cmd import repair_rag_command

    service = MagicMock()
    service.repair_anima_if_allowed.return_value = RepairResult(
        status="failed",
        anima_name="sora",
        reason="manual_repair_rag_cli",
        error="boom",
        stage="reindex",
    )
    args = argparse.Namespace(anima="sora", full=True, shared=False)

    with (
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
        pytest.raises(SystemExit) as exc,
    ):
        repair_rag_command(args)

    assert exc.value.code == 1
    assert "boom" in capsys.readouterr().err


def test_repair_rag_list_suspects_does_not_require_full(capsys: pytest.CaptureFixture[str]) -> None:
    from cli.commands.repair_rag_cmd import repair_rag_command

    service = MagicMock()
    service.discover_suspect_animas.return_value = ["sora", "rin"]
    args = argparse.Namespace(
        anima=None,
        all=False,
        suspect_only=False,
        list_suspects=True,
        full=False,
        shared=False,
        window_minutes=60,
    )

    with patch("core.memory.rag.repair.get_repair_service", return_value=service):
        repair_rag_command(args)

    service.discover_suspect_animas.assert_called_once_with(window_minutes=60)
    assert "sora" in capsys.readouterr().out


def test_repair_rag_suspect_only_runs_bulk_repair(capsys: pytest.CaptureFixture[str]) -> None:
    from cli.commands.repair_rag_cmd import repair_rag_command

    service = MagicMock()
    service.discover_suspect_animas.return_value = ["sora"]
    service.repair_animas_if_allowed.return_value = {
        "sora": RepairResult(status="success", anima_name="sora", reason="manual_repair_rag_cli", chunks_indexed=3)
    }
    args = argparse.Namespace(
        anima=None,
        all=False,
        suspect_only=True,
        list_suspects=False,
        full=True,
        shared=True,
        window_minutes=60,
    )

    with patch("core.memory.rag.repair.get_repair_service", return_value=service):
        repair_rag_command(args)

    service.repair_animas_if_allowed.assert_called_once_with(
        ["sora"],
        reason="manual_repair_rag_cli",
        source="cli",
        include_shared=True,
    )
    assert "RAG repair succeeded" in capsys.readouterr().out
