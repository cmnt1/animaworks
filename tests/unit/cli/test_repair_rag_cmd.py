from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _access_context(result: dict):
    @contextmanager
    def context(*_args, **_kwargs):
        yield SimpleNamespace(repair=MagicMock(return_value=result))

    return context


def _anima_dirs(data_dir: Path, monkeypatch) -> Path:
    animas_dir = data_dir / "animas"
    (animas_dir / "sora").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("core.paths.get_animas_dir", lambda: animas_dir)
    return animas_dir


def test_repair_rag_requires_full(capsys: pytest.CaptureFixture[str]) -> None:
    from cli.commands.repair_rag_cmd import repair_rag_command

    args = argparse.Namespace(anima="sora", full=False, shared=True)
    with pytest.raises(SystemExit) as exc:
        repair_rag_command(args)

    assert exc.value.code == 2
    assert "requires --full" in capsys.readouterr().err


def test_repair_rag_success(capsys: pytest.CaptureFixture[str], data_dir: Path, monkeypatch) -> None:
    from cli.commands.repair_rag_cmd import repair_rag_command

    _anima_dirs(data_dir, monkeypatch)
    service = MagicMock()
    access_context = _access_context(
        {"ok": True, "status": "success", "chunks_indexed": 12, "archive_path": "/tmp/archive/vectordb"}
    )
    args = argparse.Namespace(anima="sora", full=True, shared=True, reason="manual_test")

    with (
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
        patch("core.memory.rag.cli_access.open_vector_access", side_effect=access_context) as open_access,
    ):
        repair_rag_command(args)

    open_access.assert_called_once_with("sora", data_dir / "animas" / "sora", purpose="manual_test")
    assert "RAG repair succeeded" in capsys.readouterr().out


def test_repair_rag_failure_exits_one(capsys: pytest.CaptureFixture[str], data_dir: Path, monkeypatch) -> None:
    from cli.commands.repair_rag_cmd import repair_rag_command

    _anima_dirs(data_dir, monkeypatch)
    service = MagicMock()
    args = argparse.Namespace(anima="sora", full=True, shared=False, reason="manual_repair_rag_cli")
    with (
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
        patch(
            "core.memory.rag.cli_access.open_vector_access",
            side_effect=_access_context({"ok": False, "status": "failed", "last_error": "boom"}),
        ),
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


def test_repair_rag_suspect_only_repairs_targets_one_by_one(
    capsys: pytest.CaptureFixture[str], data_dir: Path, monkeypatch
) -> None:
    from cli.commands.repair_rag_cmd import repair_rag_command

    animas_dir = _anima_dirs(data_dir, monkeypatch)
    (animas_dir / "rin").mkdir()
    service = MagicMock()
    service.discover_suspect_animas.return_value = ["sora", "rin"]
    access_context = _access_context({"ok": True, "status": "success", "chunks_indexed": 3})
    args = argparse.Namespace(
        anima=None,
        all=False,
        suspect_only=True,
        list_suspects=False,
        full=True,
        shared=True,
        window_minutes=60,
        reason="manual_repair_rag_cli",
    )

    with (
        patch("core.memory.rag.repair.get_repair_service", return_value=service),
        patch("core.memory.rag.cli_access.open_vector_access", side_effect=access_context) as open_access,
    ):
        repair_rag_command(args)

    assert open_access.call_count == 2
    service.discover_suspect_animas.assert_called_once_with(window_minutes=60)
    assert capsys.readouterr().out.count("RAG repair succeeded") == 2
