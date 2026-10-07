from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for ToolHandler replied_to persistence in standalone CLI processes."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _set_runtime_env(monkeypatch: pytest.MonkeyPatch, anima_dir: Path) -> None:
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))
    monkeypatch.setenv("ANIMAWORKS_REQUEST_ID", "req-123")
    monkeypatch.setenv("ANIMAWORKS_SESSION_TYPE", "chat")
    monkeypatch.setenv("ANIMAWORKS_THREAD_ID", "thread-a")
    monkeypatch.setenv("ANIMAWORKS_TRIGGER", "message:bob")
    monkeypatch.setenv("ANIMAWORKS_TOOL_SESSION_ID", "tool-123")


def _message() -> MagicMock:
    message = MagicMock()
    message.type = "message"
    message.id = "msg-123"
    message.thread_id = "thread-123"
    return message


def test_standalone_send_persists_session_scoped_reply_and_executor_reads_it(
    data_dir_at_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.execution.base import BaseExecutor
    from core.execution.session.session_context import RuntimeSessionContext, runtime_session_scope
    from core.tooling.standalone import build_standalone_tool_handler

    alice_dir = data_dir_at_tmp_path / "animas" / "alice"
    alice_dir.mkdir(parents=True)
    (alice_dir / "status.json").write_text("{}", encoding="utf-8")
    bob_dir = data_dir_at_tmp_path / "animas" / "bob"
    bob_dir.mkdir()
    (bob_dir / "status.json").write_text("{}", encoding="utf-8")
    _set_runtime_env(monkeypatch, alice_dir)

    first_handler = build_standalone_tool_handler(alice_dir, for_mcp=False)
    first_handler._messenger.send = MagicMock(return_value=_message())
    result = first_handler.handle(
        "send_message",
        {"to": "bob", "content": "A status update", "intent": "report"},
    )
    assert "Message sent to bob" in result

    replied_to_path = alice_dir / "run" / "replied_to" / "chat" / "thread-a.jsonl"
    entries = [json.loads(line) for line in replied_to_path.read_text(encoding="utf-8").splitlines()]
    assert entries[-1] == {
        "to": "bob",
        "success": True,
        "session_type": "chat",
        "thread_id": "thread-a",
        "request_id": "req-123",
    }

    class _TestExecutor(BaseExecutor):
        async def execute(self, prompt, system_prompt="", tracker=None, shortterm=None, trigger="", images=None):
            raise NotImplementedError

    from core.schemas import ModelConfig

    executor = _TestExecutor(ModelConfig(model="test-model"), alice_dir)
    ctx = RuntimeSessionContext.from_env()
    assert ctx is not None
    with runtime_session_scope(ctx):
        assert executor._read_replied_to_file() == {"bob"}

    # A new CLI process builds a fresh handler, which restores the same run state
    # before dispatch and therefore keeps the per-run duplicate guard effective.
    second_handler = build_standalone_tool_handler(alice_dir, for_mcp=False)
    second_handler._messenger.send = MagicMock(return_value=_message())
    duplicate = second_handler.handle(
        "send_message",
        {"to": "bob", "content": "A second status update", "intent": "report"},
    )
    assert "already sent" in duplicate.lower() or "送信済み" in duplicate
    second_handler._messenger.send.assert_not_called()


def test_standalone_send_restores_unknown_session_reply_for_next_handler(
    data_dir_at_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.execution.session.session_context import RuntimeSessionContext
    from core.tooling.standalone import build_standalone_tool_handler

    alice_dir = data_dir_at_tmp_path / "animas" / "alice"
    alice_dir.mkdir(parents=True)
    (alice_dir / "status.json").write_text("{}", encoding="utf-8")
    bob_dir = data_dir_at_tmp_path / "animas" / "bob"
    bob_dir.mkdir()
    (bob_dir / "status.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(alice_dir))
    for name in (
        "ANIMAWORKS_REQUEST_ID",
        "ANIMAWORKS_SESSION_TYPE",
        "ANIMAWORKS_THREAD_ID",
        "ANIMAWORKS_TRIGGER",
        "ANIMAWORKS_TOOL_SESSION_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    assert RuntimeSessionContext.from_env() is None

    first_handler = build_standalone_tool_handler(alice_dir, for_mcp=False)
    first_handler._messenger.send = MagicMock(return_value=_message())
    result = first_handler.handle(
        "send_message",
        {"to": "bob", "content": "A status update", "intent": "report"},
    )
    assert "Message sent to bob" in result

    second_handler = build_standalone_tool_handler(alice_dir, for_mcp=False)
    second_handler._messenger.send = MagicMock(return_value=_message())
    duplicate = second_handler.handle(
        "send_message",
        {"to": "bob", "content": "A second status update", "intent": "report"},
    )
    assert "already sent" in duplicate.lower() or "送信済み" in duplicate
    second_handler._messenger.send.assert_not_called()


def test_cli_messaging_no_longer_has_a1_reply_file_copy() -> None:
    from cli.commands import messaging

    assert not hasattr(messaging, "_persist_replied_to_for_a1")
