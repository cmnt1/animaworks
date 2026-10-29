"""Unit tests for cli/commands/messaging.py — Messaging CLI commands."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _create_anima(animas_dir: Path, name: str, company: str = "") -> Path:
    anima_dir = animas_dir / name
    anima_dir.mkdir(parents=True, exist_ok=True)
    status = {"company": company} if company else {}
    (anima_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    return anima_dir


def _make_handler(anima_dir: Path, shared_dir: Path):
    from core.tooling.handler import ToolHandler

    messenger = MagicMock()
    messenger.anima_name = anima_dir.name
    messenger.shared_dir = shared_dir
    message = MagicMock()
    message.type = "message"
    message.id = "msg001"
    message.thread_id = "thread001"
    messenger.send.return_value = message
    handler = ToolHandler(
        anima_dir=anima_dir,
        memory=MagicMock(),
        messenger=messenger,
        tool_registry=[],
    )
    return handler, messenger


# ── cmd_send ─────────────────────────────────────────────


class TestCmdSend:
    def test_anima_send_routes_through_send_message(self, tmp_path: Path, capsys) -> None:
        from cli.commands.messaging import cmd_send

        anima_dir = tmp_path / "animas" / "alice"
        args = argparse.Namespace(
            from_person="alice",
            to_person="bob",
            message="Hello Bob",
            thread_id="thread-1",
            reply_to="msg-0",
            intent="question",
        )
        with (
            patch("cli.commands.messaging.current_anima_dir", return_value=anima_dir),
            patch("cli._anima_tool.run_anima_tool", return_value="Message sent to bob") as run_tool,
        ):
            cmd_send(args)

        run_tool.assert_called_once_with(
            "send_message",
            {
                "to": "bob",
                "content": "Hello Bob",
                "intent": "question",
                "thread_id": "thread-1",
                "reply_to": "msg-0",
            },
        )
        assert capsys.readouterr().out.strip() == "Message sent to bob"

    def test_anima_send_refuses_impersonation(self, tmp_path: Path, capsys) -> None:
        from cli.commands.messaging import cmd_send

        args = argparse.Namespace(
            from_person="bob",
            to_person="carol",
            message="Hello",
            thread_id=None,
            reply_to=None,
            intent="report",
        )
        with (
            patch("cli.commands.messaging.current_anima_dir", return_value=tmp_path / "animas" / "alice"),
            patch("cli._anima_tool.run_anima_tool") as run_tool,
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_send(args)

        assert exc_info.value.code == 1
        assert "alice" in capsys.readouterr().err
        run_tool.assert_not_called()

    def test_anima_send_prints_handler_error_and_exits_nonzero(self, tmp_path: Path, capsys) -> None:
        from cli.commands.messaging import cmd_send

        error = json.dumps({"status": "error", "error_type": "Blocked", "message": "cross-company"})
        args = argparse.Namespace(
            from_person="alice",
            to_person="bob",
            message="Hello",
            thread_id=None,
            reply_to=None,
            intent="report",
        )
        with (
            patch("cli.commands.messaging.current_anima_dir", return_value=tmp_path / "animas" / "alice"),
            patch("cli._anima_tool.run_anima_tool", return_value=error),
            pytest.raises(SystemExit) as exc_info,
        ):
            cmd_send(args)

        assert exc_info.value.code == 1
        assert capsys.readouterr().out.strip() == error

    def test_self_send_is_rejected_by_tool_handler(
        self,
        tmp_path: Path,
        data_dir_at_tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys,
    ) -> None:
        from cli.commands.messaging import cmd_send

        anima_dir = _create_anima(data_dir_at_tmp_path / "animas", "alice")
        shared_dir = data_dir_at_tmp_path / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        handler, messenger = _make_handler(anima_dir, shared_dir)
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))
        args = argparse.Namespace(
            from_person="alice",
            to_person="alice",
            message="note to self",
            thread_id=None,
            reply_to=None,
            intent="report",
        )

        with patch("core.tooling.standalone._standalone_handler", return_value=handler), pytest.raises(SystemExit) as exc_info:
            cmd_send(args)

        assert exc_info.value.code == 1
        assert "Error:" in capsys.readouterr().out
        messenger.send.assert_not_called()

    def test_cross_company_error_is_returned_from_tool_handler(
        self,
        tmp_path: Path,
        data_dir_at_tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys,
    ) -> None:
        from cli.commands.messaging import cmd_send

        animas_dir = data_dir_at_tmp_path / "animas"
        anima_dir = _create_anima(animas_dir, "alice", "company-a")
        _create_anima(animas_dir, "bob", "company-b")
        shared_dir = data_dir_at_tmp_path / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        handler, messenger = _make_handler(anima_dir, shared_dir)
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))
        args = argparse.Namespace(
            from_person="alice",
            to_person="bob",
            message="Hello",
            thread_id=None,
            reply_to=None,
            intent="report",
        )

        with patch("core.tooling.standalone._standalone_handler", return_value=handler), pytest.raises(SystemExit) as exc_info:
            cmd_send(args)

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "bob" in output or "company" in output.lower() or "会社" in output
        messenger.send.assert_not_called()

    @patch("core.messaging.sender.resolve_sender_source", return_value="human")
    @patch("cli.commands.messaging._notify_server_message_sent")
    @patch("core.messaging.messenger.Messenger")
    @patch("core.paths.get_shared_dir", return_value=Path("/tmp/shared"))
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    @patch("cli.commands.messaging.current_anima_dir", return_value=None)
    def test_operator_send_still_uses_messenger(
        self,
        mock_context,
        mock_ensure,
        mock_shared,
        mock_messenger_cls,
        mock_notify,
        mock_sender_source,
        capsys,
    ) -> None:
        from cli.commands.messaging import cmd_send

        mock_message = MagicMock()
        mock_message.from_person = "operator"
        mock_message.to_person = "bob"
        mock_message.id = "msg001"
        mock_message.thread_id = "thread001"
        mock_messenger = MagicMock()
        mock_messenger.send.return_value = mock_message
        mock_messenger_cls.return_value = mock_messenger
        args = argparse.Namespace(
            from_person="operator",
            to_person="bob",
            message="Hello Bob",
            thread_id=None,
            reply_to=None,
            intent="report",
        )

        cmd_send(args)

        mock_sender_source.assert_called_once_with("operator")
        mock_messenger.send.assert_called_once_with(
            to="bob",
            content="Hello Bob",
            thread_id="",
            reply_to="",
            intent="report",
            source="human",
        )
        mock_notify.assert_called_once_with("operator", "bob", "Hello Bob", "msg001")
        assert "operator (human)" in capsys.readouterr().out


def test_operator_message_notification_uses_shared_core_path() -> None:
    from cli.commands.messaging import _notify_server_message_sent

    with patch("cli.commands.messaging.notify_server_message_sent") as notify:
        _notify_server_message_sent("alice", "bob", "hello", "msg_123")

    notify.assert_called_once_with("alice", "bob", "hello", "msg_123")


# ── cmd_status ───────────────────────────────────────────


class TestCmdStatus:
    @patch("httpx.request")
    def test_status_success(self, mock_request, capsys):
        from cli.commands.messaging import cmd_status

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "animas": 2,
            "scheduler_running": True,
            "jobs": [{"id": "hb1", "name": "heartbeat", "next_run": "2026-01-01"}],
        }
        mock_request.return_value = mock_resp

        args = argparse.Namespace(gateway_url="http://localhost:18500")
        cmd_status(args)

        captured = capsys.readouterr()
        assert "Animas: 2" in captured.out
        assert "running" in captured.out

    @patch("httpx.request", side_effect=__import__("httpx").ConnectError("fail"))
    def test_status_connection_error(self, mock_request):
        from cli.commands.messaging import cmd_status

        args = argparse.Namespace(gateway_url="http://localhost:18500")
        with pytest.raises(SystemExit):
            cmd_status(args)
