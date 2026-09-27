"""Unit tests for cli/commands/messaging.py — Messaging CLI commands."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── cmd_send ─────────────────────────────────────────────


class TestCmdSend:
    @patch("cli.commands.messaging._notify_server_message_sent")
    @patch("core.messaging.messenger.Messenger")
    @patch("core.paths.get_shared_dir", return_value=Path("/tmp/shared"))
    @patch("core.infra.runtime_init.ensure_runtime_dir")
    def test_send_success(
        self,
        mock_ensure,
        mock_shared,
        mock_messenger_cls,
        mock_notify,
        capsys,
    ):
        from cli.commands.messaging import cmd_send

        mock_msg = MagicMock()
        mock_msg.from_person = "alice"
        mock_msg.to_person = "bob"
        mock_msg.id = "msg001"
        mock_msg.thread_id = "thread001"

        mock_messenger = MagicMock()
        mock_messenger.send.return_value = mock_msg
        mock_messenger_cls.return_value = mock_messenger

        args = argparse.Namespace(
            from_person="alice",
            to_person="bob",
            message="Hello Bob",
            thread_id=None,
            reply_to=None,
        )
        cmd_send(args)

        captured = capsys.readouterr()
        assert "alice" in captured.out
        assert "bob" in captured.out
        mock_notify.assert_called_once_with("alice", "bob", "Hello Bob", "msg001")


# ── _notify_server_message_sent ──────────────────────────


class TestNotifyServer:
    @patch("cli.commands.server._is_process_alive", return_value=False)
    @patch("cli.commands.server._read_pid", return_value=123)
    def test_server_not_alive(self, mock_pid, mock_alive):
        from cli.commands.messaging import _notify_server_message_sent

        # Should return silently
        _notify_server_message_sent("alice", "bob", "test")

    @patch("cli.commands.server._read_pid", return_value=None)
    def test_no_pid(self, mock_pid):
        from cli.commands.messaging import _notify_server_message_sent

        _notify_server_message_sent("alice", "bob", "test")

    @patch("httpx.post")
    @patch("cli.commands.server._is_process_alive", return_value=True)
    @patch("cli.commands.server._read_pid", return_value=123)
    def test_successful_notification(self, mock_pid, mock_alive, mock_post):
        from cli.commands.messaging import _notify_server_message_sent

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        _notify_server_message_sent("alice", "bob", "hello")

        mock_post.assert_called_once()

    @patch("httpx.post")
    @patch("cli.commands.server._is_process_alive", return_value=True)
    @patch("cli.commands.server._read_pid", return_value=123)
    def test_message_id_in_payload(self, mock_pid, mock_alive, mock_post):
        from cli.commands.messaging import _notify_server_message_sent

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        _notify_server_message_sent("alice", "bob", "hello", "msg_123")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["message_id"] == "msg_123"

    @patch("httpx.post", side_effect=Exception("connection error"))
    @patch("cli.commands.server._is_process_alive", return_value=True)
    @patch("cli.commands.server._read_pid", return_value=123)
    def test_notification_failure_silent(self, mock_pid, mock_alive, mock_post):
        from cli.commands.messaging import _notify_server_message_sent

        # Should not raise
        _notify_server_message_sent("alice", "bob", "hello")


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
