"""Unit tests for intent-based trigger filtering.

Covers the intent filter logic in core/supervisor/inbox_rate_limiter.py
(message_triggered_inbox).

Non-actionable messages (empty intent, ack, FYI) are deferred to the scheduled
heartbeat.  Actionable messages (report, question) and human-source
messages trigger an immediate heartbeat.

Internal delegation DMs are still treated as immediate/actionable so delegated
work starts promptly without waiting for the next scheduled heartbeat.
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.config.models import AnimaWorksConfig
from core.schemas import Message
from core.supervisor.inbox_rate_limiter import InboxRateLimiter
from core.supervisor.scheduler_manager import SchedulerManager

# ── Helpers ───────────────────────────────────────────────


def _default_config() -> AnimaWorksConfig:
    """Return an AnimaWorksConfig with default HeartbeatConfig.

    actionable_intents defaults to ["report", "question"].
    """
    return AnimaWorksConfig()


def _make_message(
    *,
    intent: str = "",
    source: str = "anima",
    from_person: str = "bob",
    to_person: str = "alice",
    content: str = "hello",
) -> Message:
    """Create a Message with the given intent and source."""
    return Message(
        from_person=from_person,
        to_person=to_person,
        content=content,
        intent=intent,
        source=source,
    )


def _make_limiter(messages: list[Message], anima_name: str = "alice") -> InboxRateLimiter:
    """Create an InboxRateLimiter with a mock anima.

    The anima's messenger.receive() returns *messages* and
    run_heartbeat is an AsyncMock.
    """
    mock_anima = MagicMock()
    # Nonexistent status.json → _read_anima_enabled defaults to True.
    mock_anima.anima_dir = Path("/nonexistent") / anima_name
    mock_anima.messenger = MagicMock()
    mock_anima.messenger.receive.return_value = messages
    mock_anima._lock = asyncio.Lock()
    mock_anima.run_heartbeat = AsyncMock(return_value=MagicMock())
    mock_anima.run_heartbeat.return_value.model_dump.return_value = {}

    mock_scheduler_mgr = MagicMock(spec=SchedulerManager)
    mock_scheduler_mgr.heartbeat_running = False

    limiter = InboxRateLimiter(
        anima=mock_anima,
        anima_name=anima_name,
        shutdown_event=asyncio.Event(),
        scheduler_mgr=mock_scheduler_mgr,
    )
    limiter._pending_trigger = True  # mimic the real trigger path
    return limiter


# ══════════════════════════════════════════════════════════
# InboxRateLimiter — message_triggered_inbox
# ══════════════════════════════════════════════════════════


class TestLimiterIntentFilter:
    """Intent filtering in InboxRateLimiter.message_triggered_inbox."""

    async def test_limiter_internal_delegation_triggers_inbox(self):
        """Internal delegation DMs should trigger inbox processing immediately."""
        messages = [_make_message(intent="delegation")]
        limiter = _make_limiter(messages)

        with patch(
            "core.supervisor.inbox_rate_limiter.load_config",
            return_value=_default_config(),
        ):
            await limiter.message_triggered_inbox()

        limiter._anima.process_inbox_message.assert_called_once()
        assert limiter._pending_trigger is False

    async def test_limiter_external_delegation_with_intent_triggers_inbox(self):
        """External platform messages with an explicit intent still trigger immediately."""
        messages = [_make_message(intent="delegation", source="slack")]
        limiter = _make_limiter(messages)

        with patch(
            "core.supervisor.inbox_rate_limiter.load_config",
            return_value=_default_config(),
        ):
            await limiter.message_triggered_inbox()

        limiter._anima.process_inbox_message.assert_called_once()
        assert limiter._pending_trigger is False

    async def test_limiter_empty_intent_skips_inbox(self):
        """Message with intent='' should NOT trigger inbox processing."""
        messages = [_make_message(intent="")]
        limiter = _make_limiter(messages)

        with patch(
            "core.supervisor.inbox_rate_limiter.load_config",
            return_value=_default_config(),
        ):
            await limiter.message_triggered_inbox()

        limiter._anima.process_inbox_message.assert_not_called()
        assert limiter._pending_trigger is False

    async def test_limiter_human_source_always_triggers(self):
        """Message with source='human' and intent='' should trigger.

        Human messages always bypass the intent filter.
        """
        messages = [_make_message(intent="", source="human")]
        limiter = _make_limiter(messages)

        with patch(
            "core.supervisor.inbox_rate_limiter.load_config",
            return_value=_default_config(),
        ):
            await limiter.message_triggered_inbox()

        limiter._anima.process_inbox_message.assert_called_once()
        assert limiter._pending_trigger is False

    async def test_limiter_slack_directed_triggers(self):
        """Message with source='slack' and intent='question' should trigger.

        Only directed external messages (non-empty intent) bypass the filter.
        """
        messages = [_make_message(intent="question", source="slack")]
        limiter = _make_limiter(messages)

        with patch(
            "core.supervisor.inbox_rate_limiter.load_config",
            return_value=_default_config(),
        ):
            await limiter.message_triggered_inbox()

        limiter._anima.process_inbox_message.assert_called_once()
        assert limiter._pending_trigger is False

    async def test_limiter_slack_undirected_defers(self):
        """Message with source='slack' and intent='' should defer.

        Non-directed external messages wait for the scheduled heartbeat.
        """
        messages = [_make_message(intent="", source="slack")]
        limiter = _make_limiter(messages)

        with patch(
            "core.supervisor.inbox_rate_limiter.load_config",
            return_value=_default_config(),
        ):
            await limiter.message_triggered_inbox()

        limiter._anima.process_inbox_message.assert_not_called()
        assert limiter._pending_trigger is False

    async def test_limiter_chatwork_directed_triggers(self):
        """Message with source='chatwork' and intent='question' should trigger."""
        messages = [_make_message(intent="question", source="chatwork")]
        limiter = _make_limiter(messages)

        with patch(
            "core.supervisor.inbox_rate_limiter.load_config",
            return_value=_default_config(),
        ):
            await limiter.message_triggered_inbox()

        limiter._anima.process_inbox_message.assert_called_once()
        assert limiter._pending_trigger is False

    async def test_limiter_mixed_messages_actionable_wins(self):
        """If any message has an actionable intent, inbox processing triggers."""
        messages = [
            _make_message(intent=""),              # non-actionable
            _make_message(intent="question"),       # actionable
        ]
        limiter = _make_limiter(messages)

        with patch(
            "core.supervisor.inbox_rate_limiter.load_config",
            return_value=_default_config(),
        ):
            await limiter.message_triggered_inbox()

        limiter._anima.process_inbox_message.assert_called_once()
        assert limiter._pending_trigger is False

    async def test_limiter_all_ack_messages_skip(self):
        """Multiple messages all with intent='' should NOT trigger."""
        messages = [
            _make_message(intent="", from_person="bob"),
            _make_message(intent="", from_person="carol"),
        ]
        limiter = _make_limiter(messages)

        with patch(
            "core.supervisor.inbox_rate_limiter.load_config",
            return_value=_default_config(),
        ):
            await limiter.message_triggered_inbox()

        limiter._anima.process_inbox_message.assert_not_called()
        assert limiter._pending_trigger is False
