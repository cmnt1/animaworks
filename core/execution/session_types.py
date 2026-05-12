from __future__ import annotations

"""Shared runtime session-type helpers."""

SESSION_TYPE_CHAT = "chat"
SESSION_TYPE_HEARTBEAT = "heartbeat"
SESSION_TYPE_CRON = "cron"
SESSION_TYPE_TASK = "task"
SESSION_TYPE_INBOX = "inbox"

CHAT_SESSION_TYPES: frozenset[str] = frozenset({SESSION_TYPE_CHAT})
NON_CHAT_CLEAN_SESSION_TYPES: frozenset[str] = frozenset(
    {
        SESSION_TYPE_HEARTBEAT,
        SESSION_TYPE_CRON,
        SESSION_TYPE_TASK,
        SESSION_TYPE_INBOX,
    }
)
"""Session types that must start clean for every run."""

CHAT_TRIGGERS: frozenset[str] = frozenset({"", "manual", "chat", "bootstrap", "greet:user"})


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
    if trigger in CHAT_TRIGGERS:
        return SESSION_TYPE_CHAT
    return SESSION_TYPE_TASK


def is_chat_session_type(session_type: str) -> bool:
    """Return True when a session type is the persistent human-chat namespace."""
    return session_type in CHAT_SESSION_TYPES


def trigger_uses_chat_session(trigger: str) -> bool:
    """Return True only for user-facing human chat triggers."""
    return trigger.startswith("message:") or trigger in CHAT_TRIGGERS


def is_clean_start_session(trigger: str) -> bool:
    """Return True when a trigger must start from a clean non-chat session."""
    return resolve_runtime_session_type(trigger) in NON_CHAT_CLEAN_SESSION_TYPES


def is_persistent_codex_session(trigger: str) -> bool:
    """Return True when Codex thread IDs should be resumed across turns."""
    return trigger_uses_chat_session(trigger)
