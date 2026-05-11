from __future__ import annotations

from core.execution.session_types import (
    is_chat_session_type,
    is_clean_start_session,
    is_persistent_codex_session,
    resolve_runtime_session_type,
    trigger_uses_chat_session,
)


def test_inbox_trigger_is_not_chat_session() -> None:
    assert resolve_runtime_session_type("inbox:sakura") == "inbox"
    assert trigger_uses_chat_session("inbox:sakura") is False
    assert is_persistent_codex_session("inbox:sakura") is False
    assert is_clean_start_session("inbox:sakura") is True


def test_human_message_trigger_is_chat_session() -> None:
    assert resolve_runtime_session_type("message:admin") == "chat"
    assert trigger_uses_chat_session("message:admin") is True
    assert is_persistent_codex_session("message:admin") is True
    assert is_clean_start_session("message:admin") is False


def test_legacy_chat_trigger_is_chat_session() -> None:
    for trigger in ("", "manual", "chat", "bootstrap", "greet:user"):
        assert resolve_runtime_session_type(trigger) == "chat"
        assert trigger_uses_chat_session(trigger) is True
        assert is_persistent_codex_session(trigger) is True
        assert is_clean_start_session(trigger) is False


def test_background_triggers_are_separate_sessions() -> None:
    assert resolve_runtime_session_type("heartbeat") == "heartbeat"
    assert resolve_runtime_session_type("consolidation:nightly") == "heartbeat"
    assert resolve_runtime_session_type("cron:daily") == "cron"
    assert resolve_runtime_session_type("task:demo") == "task"
    assert resolve_runtime_session_type("unknown") == "task"
    assert is_persistent_codex_session("heartbeat") is False
    assert is_persistent_codex_session("task:demo") is False
    for trigger in ("heartbeat", "consolidation:nightly", "cron:daily", "task:demo", "unknown"):
        assert trigger_uses_chat_session(trigger) is False
        assert is_clean_start_session(trigger) is True


def test_session_type_predicates() -> None:
    assert is_chat_session_type("chat") is True
    for session_type in ("inbox", "heartbeat", "cron", "task"):
        assert is_chat_session_type(session_type) is False
