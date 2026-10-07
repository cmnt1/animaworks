"""Unit tests for CLI Board adapters and operator paths."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_handler(anima_dir: Path, shared_dir: Path):
    from core.tooling.handler import ToolHandler

    messenger = MagicMock()
    messenger.anima_name = anima_dir.name
    messenger.shared_dir = shared_dir
    handler = ToolHandler(
        anima_dir=anima_dir,
        memory=MagicMock(),
        messenger=messenger,
        tool_registry=[],
    )
    return handler, messenger


# ── Board read ────────────────────────────────────────────


class TestCmdBoardRead:
    def test_anima_read_routes_through_read_channel(self, tmp_path: Path, capsys) -> None:
        from cli.commands.board import cmd_board_read

        args = argparse.Namespace(channel="general", limit=7, human_only=True)
        with (
            patch("cli.commands.board.current_anima_dir", return_value=tmp_path / "alice"),
            patch("cli._anima_tool.run_anima_tool", return_value='[{"text":"hi"}]') as run_tool,
        ):
            cmd_board_read(args)

        run_tool.assert_called_once_with(
            "read_channel",
            {"channel": "general", "limit": 7, "human_only": True},
        )
        assert json.loads(capsys.readouterr().out) == [{"text": "hi"}]

    @patch("core.messaging.messenger.Messenger")
    @patch("core.paths.get_shared_dir", return_value=Path("/tmp/shared"))
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    @patch("cli.commands.board.current_anima_dir", return_value=None)
    def test_operator_read_keeps_messenger_path(
        self,
        mock_context,
        mock_ensure,
        mock_shared,
        mock_messenger_cls,
        capsys,
    ) -> None:
        from cli.commands.board import cmd_board_read

        mock_messenger = MagicMock()
        mock_messenger.read_channel.return_value = [{"from": "alice", "text": "hello"}]
        mock_messenger_cls.return_value = mock_messenger
        cmd_board_read(argparse.Namespace(channel="general", limit=10, human_only=False))

        mock_messenger_cls.assert_called_once_with(Path("/tmp/shared"), "cli")
        mock_messenger.read_channel.assert_called_once_with("general", limit=10, human_only=False)
        assert json.loads(capsys.readouterr().out)[0]["from"] == "alice"


# ── Board post ────────────────────────────────────────────


class TestCmdBoardPost:
    @patch("cli.commands.board._notify_server_board_posted")
    @patch("cli.commands.board.fanout_board_mentions")
    @patch("core.messaging.messenger.Messenger")
    @patch("core.paths.get_shared_dir", return_value=Path("/tmp/shared"))
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    @patch("cli.commands.board.current_anima_dir", return_value=None)
    def test_operator_post_keeps_messenger_and_shared_fanout(
        self,
        mock_context,
        mock_ensure,
        mock_shared,
        mock_messenger_cls,
        mock_fanout,
        mock_notify,
        capsys,
    ) -> None:
        from cli.commands.board import cmd_board_post

        mock_messenger = MagicMock()
        mock_messenger_cls.return_value = mock_messenger
        args = argparse.Namespace(from_anima="alice", channel="general", text="Hello @bob")

        cmd_board_post(args)

        mock_messenger.post_channel.assert_called_once_with("general", "Hello @bob")
        mock_fanout.assert_called_once_with(mock_messenger, "alice", "general", "Hello @bob")
        mock_notify.assert_called_once_with("alice", "general", "Hello @bob")
        assert capsys.readouterr().out.strip() == "Posted to #general"

    def test_anima_post_uses_handler_fanout_once(
        self,
        tmp_path: Path,
        data_dir_at_tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys,
    ) -> None:
        from cli.commands.board import cmd_board_post

        anima_dir = data_dir_at_tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "status.json").write_text("{}", encoding="utf-8")
        shared_dir = data_dir_at_tmp_path / "shared"
        (shared_dir / "channels").mkdir(parents=True, exist_ok=True)
        handler, messenger = _make_handler(anima_dir, shared_dir)
        messenger.shared_dir = shared_dir
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))
        args = argparse.Namespace(from_anima="alice", channel="general", text="Hello @bob")

        with (
            patch("core.tooling.standalone._standalone_handler", return_value=handler),
            patch("core.messaging.board_fanout.fanout_board_mentions") as fanout,
            patch("cli.commands.board._notify_server_board_posted") as notify,
            patch.object(handler, "_fire_board_slack_sync"),
        ):
            cmd_board_post(args)

        messenger.post_channel.assert_called_once_with("general", "Hello @bob")
        fanout.assert_called_once()
        notify.assert_not_called()
        assert capsys.readouterr().out.strip() == "Posted to #general"

    def test_anima_post_refuses_impersonation(self, tmp_path: Path, capsys) -> None:
        from cli.commands.board import cmd_board_post

        args = argparse.Namespace(from_anima="bob", channel="general", text="hello")
        with (
            patch("cli.commands.board.current_anima_dir", return_value=tmp_path / "alice"),
            patch("cli._anima_tool.run_anima_tool") as run_tool,
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_board_post(args)

        assert exc_info.value.code == 1
        assert "alice" in capsys.readouterr().err
        run_tool.assert_not_called()

    @patch("cli.commands.board._notify_server_board_posted")
    @patch("cli.commands.board.fanout_board_mentions")
    @patch("core.messaging.messenger.Messenger")
    @patch("core.paths.get_shared_dir", return_value=Path("/tmp/shared"))
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    @patch("cli.commands.board.current_anima_dir", return_value=None)
    def test_operator_post_denied_channel_exits_without_fanout(
        self,
        mock_context,
        mock_ensure,
        mock_shared,
        mock_messenger_cls,
        mock_fanout,
        mock_notify,
        capsys,
    ) -> None:
        from cli.commands.board import cmd_board_post
        from core.exceptions import ChannelNotFoundError

        mock_messenger = MagicMock()
        mock_messenger.post_channel.side_effect = ChannelNotFoundError("missing")
        mock_messenger_cls.return_value = mock_messenger
        args = argparse.Namespace(from_anima="alice", channel="missing", text="hello")

        with pytest.raises(SystemExit) as exc_info:
            cmd_board_post(args)

        assert exc_info.value.code == 1
        assert "Error:" in capsys.readouterr().err
        mock_fanout.assert_not_called()
        mock_notify.assert_not_called()


# ── DM history ───────────────────────────────────────────


class TestCmdBoardDmHistory:
    def test_anima_dm_history_maps_all_tool_arguments(self, tmp_path: Path, capsys) -> None:
        from cli.commands.board import cmd_board_dm_history

        args = argparse.Namespace(
            from_anima="alice",
            peer="bob",
            limit=40,
            direction="sent",
            hours=24,
            keyword="deploy",
        )
        with (
            patch("cli.commands.board.current_anima_dir", return_value=tmp_path / "alice"),
            patch("cli._anima_tool.run_anima_tool", return_value="[]") as run_tool,
        ):
            cmd_board_dm_history(args)

        run_tool.assert_called_once_with(
            "read_dm_history",
            {"peer": "bob", "limit": 40, "direction": "sent", "hours": 24, "keyword": "deploy"},
        )
        assert capsys.readouterr().out.strip() == "[]"

    @patch("core.messaging.messenger.Messenger")
    @patch("core.paths.get_shared_dir", return_value=Path("/tmp/shared"))
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    @patch("cli.commands.board.current_anima_dir", return_value=None)
    def test_operator_dm_history_forwards_filter_flags(
        self,
        mock_context,
        mock_ensure,
        mock_shared,
        mock_messenger_cls,
        capsys,
    ) -> None:
        from cli.commands.board import cmd_board_dm_history

        mock_messenger = MagicMock()
        mock_messenger.read_dm_history.return_value = [{"from": "alice", "text": "deploy"}]
        mock_messenger_cls.return_value = mock_messenger
        args = argparse.Namespace(
            from_anima="alice",
            peer="bob",
            limit=40,
            direction="received",
            hours=12,
            keyword="deploy",
        )

        cmd_board_dm_history(args)

        mock_messenger.read_dm_history.assert_called_once_with(
            "bob",
            limit=40,
            direction="received",
            hours=12,
            keyword="deploy",
        )
        assert json.loads(capsys.readouterr().out)[0]["text"] == "deploy"

    def test_anima_dm_history_refuses_impersonation(self, tmp_path: Path, capsys) -> None:
        from cli.commands.board import cmd_board_dm_history

        args = argparse.Namespace(from_anima="bob", peer="carol", limit=20)
        with (
            patch("cli.commands.board.current_anima_dir", return_value=tmp_path / "alice"),
            patch("cli._anima_tool.run_anima_tool") as run_tool,
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_board_dm_history(args)

        assert exc_info.value.code == 1
        assert "alice" in capsys.readouterr().err
        run_tool.assert_not_called()


def test_board_dm_history_parser_exposes_schema_filters() -> None:
    from cli.parser import build_parser

    args = build_parser().parse_args(
        ["board", "dm-history", "alice", "bob", "--direction", "sent", "--hours", "24", "--keyword", "deploy"]
    )
    assert args.direction == "sent"
    assert args.hours == 24
    assert args.keyword == "deploy"


def test_operator_board_notification_uses_shared_core_path() -> None:
    from cli.commands.board import _notify_server_board_posted

    with patch("cli.commands.board.notify_server_message_sent") as notify:
        _notify_server_board_posted("alice", "general", "hello")

    notify.assert_called_once_with("alice", "#channel:general", "hello")
