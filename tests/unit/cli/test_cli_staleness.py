"""Unit tests for CLI staleness fixes — log path, --local deprecation, exit code, env var."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── logs.py tests ─────────────────────────────────────────


class TestTailAllLogsServerPath:
    """Tests for _tail_all_logs server log path fix (animaworks.log, server-daemon.log)."""

    @patch("cli.commands.logs._follow_multiple_files")
    @patch("cli.commands.logs._show_last_lines")
    def test_tail_all_logs_finds_animaworks_log(
        self, mock_show: MagicMock, mock_follow: MagicMock, tmp_path: Path, capsys
    ) -> None:
        """Create tmp_path with animaworks.log; verify [SERVER] → animaworks.log in output."""
        from cli.commands.logs import _tail_all_logs

        (tmp_path / "animas").mkdir()
        (tmp_path / "animaworks.log").write_text("server log line\n", encoding="utf-8")

        _tail_all_logs(tmp_path)

        captured = capsys.readouterr()
        assert "[SERVER]" in captured.out
        assert "animaworks.log" in captured.out
        mock_follow.assert_called_once()
        call_args = mock_follow.call_args[0][0]
        assert "[SERVER]" in call_args
        assert call_args["[SERVER]"].name == "animaworks.log"

    @patch("cli.commands.logs._follow_multiple_files")
    @patch("cli.commands.logs._show_last_lines")
    def test_tail_all_logs_finds_daemon_log(
        self, mock_show: MagicMock, mock_follow: MagicMock, tmp_path: Path, capsys
    ) -> None:
        """Create both animaworks.log and server-daemon.log; verify both in log_files."""
        from cli.commands.logs import _tail_all_logs

        (tmp_path / "animas").mkdir()
        (tmp_path / "animaworks.log").write_text("server\n", encoding="utf-8")
        (tmp_path / "server-daemon.log").write_text("daemon\n", encoding="utf-8")

        _tail_all_logs(tmp_path)

        captured = capsys.readouterr()
        assert "[SERVER]" in captured.out
        assert "[SERVER-DAEMON]" in captured.out
        assert "animaworks.log" in captured.out
        assert "server-daemon.log" in captured.out
        call_args = mock_follow.call_args[0][0]
        assert "[SERVER]" in call_args
        assert "[SERVER-DAEMON]" in call_args

    @patch("cli.commands.logs._follow_multiple_files")
    @patch("cli.commands.logs._show_last_lines")
    def test_tail_all_logs_ignores_missing_server_log(
        self, mock_show: MagicMock, mock_follow: MagicMock, tmp_path: Path, capsys
    ) -> None:
        """Create only anima logs (no server logs); verify no [SERVER] key."""
        from cli.commands.logs import _tail_all_logs

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        alice_dir = animas_dir / "alice"
        alice_dir.mkdir()
        (alice_dir / "today.log").write_text("alice log\n", encoding="utf-8")
        (alice_dir / "current.log").write_text("today.log\n", encoding="utf-8")

        _tail_all_logs(tmp_path)

        captured = capsys.readouterr()
        assert "[SERVER]" not in captured.out
        assert "[alice]" in captured.out
        call_args = mock_follow.call_args[0][0]
        assert "[SERVER]" not in call_args

    @patch("cli.commands.logs._follow_multiple_files")
    @patch("cli.commands.logs._show_last_lines")
    def test_tail_all_logs_old_server_log_ignored(
        self, mock_show: MagicMock, mock_follow: MagicMock, tmp_path: Path, capsys
    ) -> None:
        """Create server.log (old name); verify it is NOT picked up."""
        from cli.commands.logs import _tail_all_logs

        (tmp_path / "animas").mkdir()
        (tmp_path / "server.log").write_text("old server log\n", encoding="utf-8")

        _tail_all_logs(tmp_path)

        captured = capsys.readouterr()
        assert "[SERVER]" not in captured.out
        assert "server.log" not in captured.out
        # _follow_multiple_files may not be called if log_files is empty
        if mock_follow.call_args is not None:
            call_args = mock_follow.call_args[0][0]
            assert "[SERVER]" not in call_args
        else:
            assert "No log files found" in captured.out


# ── anima.py --local deprecation tests ───────────────────


class TestLocalDeprecation:
    """Tests for --local deprecation warning in cmd_chat and cmd_heartbeat."""

    @patch("core.anima.DigitalAnima")
    @patch("core.paths.get_shared_dir", return_value=Path("/tmp/shared"))
    @patch("core.paths.get_animas_dir")
    @patch("core.init.ensure_runtime_dir")
    def test_cmd_chat_local_emits_deprecation_warning(
        self,
        mock_ensure: MagicMock,
        mock_animas_dir: MagicMock,
        mock_shared: MagicMock,
        mock_anima_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Create namespace with local=True; ensure DeprecationWarning is emitted."""
        from cli.commands.anima import cmd_chat

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        (animas_dir / "alice").mkdir()
        mock_animas_dir.return_value = animas_dir

        mock_anima = MagicMock()
        mock_anima.process_message = AsyncMock(return_value="Hello!")
        mock_anima_cls.return_value = mock_anima

        args = argparse.Namespace(
            local=True, anima="alice", message="Hi",
            from_person="human", gateway_url=None,
        )

        with pytest.warns(DeprecationWarning, match="--local is deprecated"):
            cmd_chat(args)

    @patch("core.anima.DigitalAnima")
    @patch("core.paths.get_shared_dir", return_value=Path("/tmp/shared"))
    @patch("core.paths.get_animas_dir")
    @patch("core.init.ensure_runtime_dir")
    def test_cmd_heartbeat_local_emits_deprecation_warning(
        self,
        mock_ensure: MagicMock,
        mock_animas_dir: MagicMock,
        mock_shared: MagicMock,
        mock_anima_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Same for heartbeat with local=True."""
        from cli.commands.anima import cmd_heartbeat

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        (animas_dir / "alice").mkdir()
        mock_animas_dir.return_value = animas_dir

        mock_result = MagicMock()
        mock_result.action = "skip"
        mock_result.summary = "No pending"
        mock_anima = MagicMock()
        mock_anima.run_heartbeat = AsyncMock(return_value=mock_result)
        mock_anima_cls.return_value = mock_anima

        args = argparse.Namespace(local=True, anima="alice", gateway_url=None)

        with pytest.warns(DeprecationWarning, match="--local is deprecated"):
            cmd_heartbeat(args)


# ── call_human.py exit code tests ────────────────────────


class TestCallHumanExitCode:
    """Tests for call_human CLI exit code (core.tools.call_human)."""

    @patch("core.tools.call_human._load_config")
    def test_cli_main_exits_1_when_all_not_supported(
        self, mock_load_config: MagicMock
    ) -> None:
        """Configure channels with only non-slack types; assert SystemExit 1."""
        from core.tools.call_human import cli_main

        mock_load_config.return_value = {
            "human_notification": {
                "enabled": True,
                "channels": [
                    {"type": "chatwork", "enabled": True},
                    {"type": "line", "enabled": True},
                ],
            },
        }

        with pytest.raises(SystemExit) as exc_info:
            cli_main(["Subject", "Body"])

        assert exc_info.value.code == 1

    @patch("core.tools.call_human._send_slack", new_callable=AsyncMock)
    @patch("core.tools.call_human._get_bot_token")
    @patch("core.tools.call_human._load_config")
    def test_cli_main_exits_0_when_slack_ok(
        self,
        mock_load_config: MagicMock,
        mock_get_token: MagicMock,
        mock_send_slack: AsyncMock,
    ) -> None:
        """Configure slack channel; mock _send_slack to return OK; assert exit 0."""
        from core.tools.call_human import cli_main

        mock_load_config.return_value = {
            "human_notification": {
                "enabled": True,
                "channels": [
                    {
                        "type": "slack",
                        "enabled": True,
                        "config": {"channel": "C123", "bot_token": "xoxb-fake"},
                    },
                ],
            },
        }
        mock_get_token.return_value = "xoxb-fake"
        mock_send_slack.return_value = ("OK", None)

        cli_main(["Subject", "Body"])
        mock_send_slack.assert_called_once()

    @patch("core.tools.call_human._send_slack", new_callable=AsyncMock)
    @patch("core.tools.call_human._get_bot_token")
    @patch("core.tools.call_human._load_config")
    def test_cli_main_exits_1_when_slack_error(
        self,
        mock_load_config: MagicMock,
        mock_get_token: MagicMock,
        mock_send_slack: AsyncMock,
    ) -> None:
        """Configure slack; mock _send_slack to return ERROR; assert SystemExit 1."""
        from core.tools.call_human import cli_main

        mock_load_config.return_value = {
            "human_notification": {
                "enabled": True,
                "channels": [
                    {
                        "type": "slack",
                        "enabled": True,
                        "config": {"channel": "C123", "bot_token": "xoxb-fake"},
                    },
                ],
            },
        }
        mock_get_token.return_value = "xoxb-fake"
        mock_send_slack.return_value = ("ERROR: channel_not_found", None)

        with pytest.raises(SystemExit) as exc_info:
            cli_main(["Subject", "Body"])

        assert exc_info.value.code == 1


# ── _gateway.py env var tests ────────────────────────────


class TestResolveGatewayUrl:
    """Tests for resolve_gateway_url environment variable unification."""

    def test_resolve_server_url_preferred_over_gateway_url(self) -> None:
        """Set both ANIMAWORKS_SERVER_URL and ANIMAWORKS_GATEWAY_URL; SERVER_URL wins."""
        from cli._gateway import resolve_gateway_url

        env = {
            "ANIMAWORKS_SERVER_URL": "http://server:18500",
            "ANIMAWORKS_GATEWAY_URL": "http://gateway:18501",
        }
        with patch.dict(os.environ, env, clear=False):
            args = argparse.Namespace(gateway_url=None)
            result = resolve_gateway_url(args)
        assert result == "http://server:18500"

    def test_resolve_gateway_url_fallback(self) -> None:
        """Set only ANIMAWORKS_GATEWAY_URL; assert it is used."""
        from cli._gateway import resolve_gateway_url

        env = {"ANIMAWORKS_GATEWAY_URL": "http://legacy:18501"}
        with patch.dict(os.environ, env, clear=False):
            args = argparse.Namespace(gateway_url=None)
            result = resolve_gateway_url(args)
        assert result == "http://legacy:18501"

    def test_resolve_default_when_no_env(self) -> None:
        """No env vars set; assert default http://localhost:18500."""
        from cli._gateway import resolve_gateway_url

        with patch.dict(
            os.environ,
            {"ANIMAWORKS_SERVER_URL": "", "ANIMAWORKS_GATEWAY_URL": ""},
            clear=False,
        ):
            args = argparse.Namespace(gateway_url=None)
            result = resolve_gateway_url(args)
        assert result == "http://localhost:18500"

    def test_resolve_cli_flag_overrides_all(self) -> None:
        """Set namespace gateway_url plus env vars; CLI flag wins."""
        from cli._gateway import resolve_gateway_url

        env = {
            "ANIMAWORKS_SERVER_URL": "http://server:18500",
            "ANIMAWORKS_GATEWAY_URL": "http://gateway:18501",
        }
        with patch.dict(os.environ, env, clear=False):
            args = argparse.Namespace(gateway_url="http://custom:9999")
            result = resolve_gateway_url(args)
        assert result == "http://custom:9999"
