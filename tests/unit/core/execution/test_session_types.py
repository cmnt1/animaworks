from __future__ import annotations

from core.execution.session_types import (
    is_persistent_codex_session,
    resolve_runtime_session_type,
    trigger_uses_chat_session,
)


def test_inbox_trigger_is_not_chat_session() -> None:
    assert resolve_runtime_session_type("inbox:sakura") == "inbox"
    assert trigger_uses_chat_session("inbox:sakura") is False
    assert is_persistent_codex_session("inbox:sakura") is False


def test_human_message_trigger_is_chat_session() -> None:
    assert resolve_runtime_session_type("message:admin") == "chat"
    assert trigger_uses_chat_session("message:admin") is True
    assert is_persistent_codex_session("message:admin") is True


def test_legacy_chat_trigger_is_chat_session() -> None:
    assert resolve_runtime_session_type("chat") == "chat"
    assert trigger_uses_chat_session("chat") is True
    assert is_persistent_codex_session("chat") is True


def test_background_triggers_are_separate_sessions() -> None:
    assert resolve_runtime_session_type("heartbeat") == "heartbeat"
    assert resolve_runtime_session_type("cron:daily") == "cron"
    assert resolve_runtime_session_type("task:demo") == "task"
    assert is_persistent_codex_session("heartbeat") is False
    assert is_persistent_codex_session("task:demo") is False
