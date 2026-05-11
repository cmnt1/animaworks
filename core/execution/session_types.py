from __future__ import annotations

"""Shared runtime session-type helpers."""

SESSION_TYPE_CHAT = "chat"
SESSION_TYPE_HEARTBEAT = "heartbeat"
SESSION_TYPE_CRON = "cron"
SESSION_TYPE_TASK = "task"
SESSION_TYPE_INBOX = "inbox"


def resolve_runtime_session_type(trigger: str) -> str:
    """Resolve the persistent state namespace for a runtime trigger."""
    if trigger.startswith("message:"):
        return SESSION_TYPE_CHAT
    if trigger == "inbox" or trigger.startswith("inbox:"):
        return SESSION_TYPE_INBOX
    if trigger == "heartbeat" or trigger.startswith("consolidation:"):
        return SESSION_TYPE_HEARTBEAT
    if trigger.startswith("cron:"):
        return SESSION_TYPE_CRON
    if trigger.startswith("task:"):
        return SESSION_TYPE_TASK
    if trigger in {"", "manual", "chat", "bootstrap", "greet:user"}:
        return SESSION_TYPE_CHAT
    return SESSION_TYPE_TASK


def trigger_uses_chat_session(trigger: str) -> bool:
    """Return True only for user-facing human chat triggers."""
    return trigger.startswith("message:") or trigger in {"", "manual", "chat", "bootstrap", "greet:user"}


def is_persistent_codex_session(trigger: str) -> bool:
    """Return True when Codex thread IDs should be resumed across turns."""
    return trigger_uses_chat_session(trigger)
