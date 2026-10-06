"""Unit tests for cli/commands/anima.py — Anima management CLI."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── cmd_create_anima ────────────────────────────────────


class TestCmdCreateAnima:
    def test_running_server_owns_anima_creation(self, tmp_path, capsys):
        from cli.commands.anima import cmd_create_anima

        data_dir = tmp_path / "runtime"
        data_dir.mkdir()
        source = tmp_path / "sheet.md"
        source.write_text("# Character: alice\n", encoding="utf-8")
        response = MagicMock(status_code=200)
        response.json.return_value = {"status": "ok", "anima_dir": str(data_dir / "animas" / "alice")}
        args = argparse.Namespace(from_md=str(source), template=None, name="alice", supervisor="boss", role="engineer")

        with (
            patch("core.paths.get_data_dir", return_value=data_dir),
            patch("core.platform.pid.is_server_running", return_value=True),
            patch("core.anima.factory.create_from_md") as local_create,
            patch("core.internal_api.host_api.post", return_value=response) as host_post,
        ):
            cmd_create_anima(args)

        local_create.assert_not_called()
        payload = host_post.call_args.kwargs["json"]
        assert payload["creation_type"] == "character_sheet"
        assert payload["character_sheet_content"] == "# Character: alice\n"
        assert payload["name"] == "alice"
        assert payload["supervisor"] == "boss"
        assert payload["role"] == "engineer"
        assert "Created anima 'alice'" in capsys.readouterr().out

    @patch("core.config.register_anima_in_config")
    @patch("core.anima.factory.create_from_md")
    @patch("core.paths.get_animas_dir")
    @patch("core.paths.get_data_dir")
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    def test_create_from_md(
        self,
        mock_ensure,
        mock_data_dir,
        mock_animas_dir,
        mock_create_md,
        mock_register,
        tmp_path,
        capsys,
    ):
        from cli.commands.anima import cmd_create_anima

        data_dir = tmp_path / ".animaworks"
        data_dir.mkdir()
        animas_dir = data_dir / "animas"
        animas_dir.mkdir()

        mock_data_dir.return_value = data_dir
        mock_animas_dir.return_value = animas_dir

        anima_dir = animas_dir / "alice"
        anima_dir.mkdir()
        mock_create_md.return_value = anima_dir

        md_file = tmp_path / "alice.md"
        md_file.write_text("# Alice", encoding="utf-8")

        args = argparse.Namespace(from_md=str(md_file), template=None, name="alice")
        cmd_create_anima(args)

        captured = capsys.readouterr()
        assert "alice" in captured.out

    @patch("core.config.register_anima_in_config")
    @patch("core.anima.factory.create_from_template")
    @patch("core.paths.get_animas_dir")
    @patch("core.paths.get_data_dir")
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    def test_create_from_template(
        self,
        mock_ensure,
        mock_data_dir,
        mock_animas_dir,
        mock_create_tpl,
        mock_register,
        tmp_path,
        capsys,
    ):
        from cli.commands.anima import cmd_create_anima

        data_dir = tmp_path / ".animaworks"
        data_dir.mkdir()
        animas_dir = data_dir / "animas"
        animas_dir.mkdir()

        mock_data_dir.return_value = data_dir
        mock_animas_dir.return_value = animas_dir

        anima_dir = animas_dir / "alice"
        anima_dir.mkdir()
        mock_create_tpl.return_value = anima_dir

        args = argparse.Namespace(from_md=None, template="basic", name="alice")
        cmd_create_anima(args)

        captured = capsys.readouterr()
        assert "alice" in captured.out

    @patch("core.config.register_anima_in_config")
    @patch("core.anima.factory.validate_anima_name", return_value=None)
    @patch("core.anima.factory.create_blank")
    @patch("core.paths.get_animas_dir")
    @patch("core.paths.get_data_dir")
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    def test_create_blank(
        self,
        mock_ensure,
        mock_data_dir,
        mock_animas_dir,
        mock_create,
        mock_validate,
        mock_register,
        tmp_path,
        capsys,
    ):
        from cli.commands.anima import cmd_create_anima

        data_dir = tmp_path / ".animaworks"
        data_dir.mkdir()
        animas_dir = data_dir / "animas"
        animas_dir.mkdir()

        mock_data_dir.return_value = data_dir
        mock_animas_dir.return_value = animas_dir

        anima_dir = animas_dir / "bob"
        anima_dir.mkdir()
        mock_create.return_value = anima_dir

        args = argparse.Namespace(from_md=None, template=None, name="bob")
        cmd_create_anima(args)

        captured = capsys.readouterr()
        assert "bob" in captured.out

    @patch("core.paths.get_animas_dir")
    @patch("core.paths.get_data_dir")
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    def test_create_blank_no_name(self, mock_ensure, mock_data_dir, mock_animas_dir, tmp_path):
        from cli.commands.anima import cmd_create_anima

        data_dir = tmp_path / ".animaworks"
        data_dir.mkdir()
        animas_dir = data_dir / "animas"
        animas_dir.mkdir()
        mock_data_dir.return_value = data_dir
        mock_animas_dir.return_value = animas_dir

        args = argparse.Namespace(from_md=None, template=None, name=None)
        with pytest.raises(SystemExit):
            cmd_create_anima(args)

    @patch("core.anima.factory.validate_anima_name", return_value="Invalid name")
    @patch("core.paths.get_animas_dir")
    @patch("core.paths.get_data_dir")
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    def test_create_blank_invalid_name(self, mock_ensure, mock_data_dir, mock_animas_dir, mock_validate, tmp_path):
        from cli.commands.anima import cmd_create_anima

        data_dir = tmp_path / ".animaworks"
        data_dir.mkdir()
        animas_dir = data_dir / "animas"
        animas_dir.mkdir()
        mock_data_dir.return_value = data_dir
        mock_animas_dir.return_value = animas_dir

        args = argparse.Namespace(from_md=None, template=None, name="INVALID")
        with pytest.raises(SystemExit):
            cmd_create_anima(args)


# ── cmd_chat ─────────────────────────────────────────────


class TestCmdChat:
    @patch("core.anima.digital_anima.DigitalAnima")
    @patch("core.paths.get_shared_dir", return_value=Path("/tmp/shared"))
    @patch("core.paths.get_animas_dir")
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    def test_chat_local(
        self,
        mock_ensure,
        mock_animas_dir,
        mock_shared,
        mock_dp_cls,
        tmp_path,
        capsys,
    ):
        from cli.commands.anima import cmd_chat

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        anima_dir = animas_dir / "alice"
        anima_dir.mkdir()
        mock_animas_dir.return_value = animas_dir

        mock_anima = MagicMock()
        mock_anima.process_message = AsyncMock(return_value="Hello!")
        mock_dp_cls.return_value = mock_anima

        args = argparse.Namespace(
            local=True,
            anima="alice",
            message="Hi",
            from_person="human",
            gateway_url=None,
        )
        cmd_chat(args)

        captured = capsys.readouterr()
        assert "Hello!" in captured.out

    @patch("core.paths.get_animas_dir")
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    def test_chat_local_anima_not_found(self, mock_ensure, mock_animas_dir, tmp_path):
        from cli.commands.anima import cmd_chat

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        mock_animas_dir.return_value = animas_dir

        args = argparse.Namespace(
            local=True,
            anima="nobody",
            message="Hi",
            from_person="human",
            gateway_url=None,
        )
        with pytest.raises(SystemExit):
            cmd_chat(args)

    @patch("httpx.request")
    def test_chat_remote(self, mock_request, capsys):
        from cli.commands.anima import cmd_chat

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "Remote reply"}
        mock_request.return_value = mock_resp

        args = argparse.Namespace(
            local=False,
            anima="alice",
            message="Hi",
            from_person="human",
            gateway_url="http://localhost:18500",
        )
        cmd_chat(args)

        captured = capsys.readouterr()
        assert "Remote reply" in captured.out

    @patch("httpx.request", side_effect=__import__("httpx").ConnectError("fail"))
    def test_chat_remote_connection_error(self, mock_request):
        from cli.commands.anima import cmd_chat

        args = argparse.Namespace(
            local=False,
            anima="alice",
            message="Hi",
            from_person="human",
            gateway_url="http://localhost:18500",
        )
        with pytest.raises(SystemExit):
            cmd_chat(args)

    def test_chat_no_message_non_tty_exits_2(self, capsys):
        from cli.commands.anima import cmd_chat

        args = argparse.Namespace(
            local=False,
            anima="sora",
            message=None,
            from_person="human",
            gateway_url=None,
            thread_id="default",
            no_tui=False,
        )
        not_tty = MagicMock()
        not_tty.isatty.return_value = False
        with (
            patch("cli.commands.anima.sys.stdin", not_tty),
            patch("cli.commands.anima.sys.stdout", not_tty),
            pytest.raises(SystemExit) as exc,
        ):
            cmd_chat(args)
        assert exc.value.code == 2
        captured = capsys.readouterr()
        assert "TUI requires a terminal" in captured.err


# ── cmd_heartbeat ────────────────────────────────────────


class TestCmdHeartbeat:
    @patch("core.anima.digital_anima.DigitalAnima")
    @patch("core.paths.get_shared_dir", return_value=Path("/tmp/shared"))
    @patch("core.paths.get_animas_dir")
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    def test_heartbeat_local(
        self,
        mock_ensure,
        mock_animas_dir,
        mock_shared,
        mock_dp_cls,
        tmp_path,
        capsys,
    ):
        from cli.commands.anima import cmd_heartbeat

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        anima_dir = animas_dir / "alice"
        anima_dir.mkdir()
        mock_animas_dir.return_value = animas_dir

        mock_result = MagicMock()
        mock_result.action = "skip"
        mock_result.summary = "No pending tasks"
        mock_anima = MagicMock()
        mock_anima.run_heartbeat = AsyncMock(return_value=mock_result)
        mock_dp_cls.return_value = mock_anima

        args = argparse.Namespace(
            local=True,
            anima="alice",
            gateway_url=None,
        )
        cmd_heartbeat(args)

        captured = capsys.readouterr()
        assert "skip" in captured.out

    @patch("core.paths.get_animas_dir")
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    def test_heartbeat_local_not_found(self, mock_ensure, mock_animas_dir, tmp_path):
        from cli.commands.anima import cmd_heartbeat

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        mock_animas_dir.return_value = animas_dir

        args = argparse.Namespace(
            local=True,
            anima="nobody",
            gateway_url=None,
        )
        with pytest.raises(SystemExit):
            cmd_heartbeat(args)

    @patch("httpx.request")
    def test_heartbeat_remote(self, mock_request, capsys):
        from cli.commands.anima import cmd_heartbeat

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"action": "skip"}
        mock_request.return_value = mock_resp

        args = argparse.Namespace(
            local=False,
            anima="alice",
            gateway_url="http://localhost:18500",
        )
        cmd_heartbeat(args)

        captured = capsys.readouterr()
        assert "skip" in captured.out

    @patch("httpx.request", side_effect=__import__("httpx").ConnectError("fail"))
    def test_heartbeat_remote_error(self, mock_request):
        from cli.commands.anima import cmd_heartbeat

        args = argparse.Namespace(
            local=False,
            anima="alice",
            gateway_url="http://localhost:18500",
        )
        with pytest.raises(SystemExit):
            cmd_heartbeat(args)


# ── resolve_default_anima ───────────────────────────────


class TestResolveDefaultAnima:
    def _anima(self, animas_dir: Path, name: str, status: str) -> None:
        (animas_dir / name).mkdir(parents=True)
        (animas_dir / name / "status.json").write_text(status, encoding="utf-8")

    def test_configured_default_wins(self, tmp_path):
        from cli.commands.anima import resolve_default_anima

        cfg = MagicMock()
        cfg.cli.default_anima = "mei"
        with (
            patch("core.config.load_config", return_value=cfg),
            patch("core.paths.get_animas_dir", return_value=tmp_path),
        ):
            assert resolve_default_anima() == "mei"

    def test_single_enabled_top_level(self, tmp_path):
        from cli.commands.anima import resolve_default_anima

        self._anima(tmp_path, "boss", '{"supervisor": null}')
        self._anima(tmp_path, "worker", '{"supervisor": "boss"}')
        self._anima(tmp_path, "off", '{"supervisor": null, "enabled": false}')
        cfg = MagicMock()
        cfg.cli.default_anima = ""
        with (
            patch("core.config.load_config", return_value=cfg),
            patch("core.paths.get_animas_dir", return_value=tmp_path),
        ):
            assert resolve_default_anima() == "boss"

    def test_ambiguous_returns_none(self, tmp_path, capsys):
        from cli.commands.anima import resolve_default_anima

        self._anima(tmp_path, "a", '{"supervisor": null}')
        self._anima(tmp_path, "b", '{"supervisor": null}')
        cfg = MagicMock()
        cfg.cli.default_anima = ""
        with (
            patch("core.config.load_config", return_value=cfg),
            patch("core.paths.get_animas_dir", return_value=tmp_path),
        ):
            assert resolve_default_anima() is None
        assert "a, b" in capsys.readouterr().err
