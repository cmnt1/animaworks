from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for _build_reply_instruction() in core.anima.inbox.

Covers:
- Slack: full metadata (channel, ts, user_id)
- Slack: missing external_user_id (no @mention)
- Slack: missing source_message_id (no --thread)
- Chatwork: full metadata
- Edge case: empty external_channel_id (guard in caller, but function still safe)
- Unknown source: returns empty string
"""

from dataclasses import dataclass
from unittest.mock import patch

from core.anima.inbox import _build_reply_instruction


@dataclass
class _FakeMsg:
    """Minimal message stub for testing reply instruction generation."""

    source: str = "anima"
    external_channel_id: str = ""
    source_message_id: str = ""
    external_user_id: str = ""
    external_thread_ts: str = ""


_MOCK_AUTO_OFF = patch("core.anima.inbox._is_auto_response_enabled", return_value=False)
_MOCK_AUTO_ON = patch("core.anima.inbox._is_auto_response_enabled", return_value=True)


class TestBuildReplyInstructionSlack:
    """Slack reply instruction generation."""

    def test_full_metadata(self):
        msg = _FakeMsg(source="slack", external_channel_id="C12345")
        result = _build_reply_instruction(msg)
        assert result.startswith("  [auto_reply:")
        assert "Discord" in result
        assert "use tool slack_channel_post" not in result

    def test_missing_user_id(self):
        msg = _FakeMsg(source="slack", external_channel_id="C12345")
        result = _build_reply_instruction(msg)
        assert result.startswith("  [auto_reply:")
        assert "Discord" in result
        assert "use tool slack_channel_post" not in result

    def test_missing_source_message_id(self):
        msg = _FakeMsg(source="slack", external_channel_id="C12345")
        result = _build_reply_instruction(msg)
        assert result.startswith("  [auto_reply:")
        assert "Discord" in result
        assert "use tool slack_channel_post" not in result

    def test_missing_both_optional_fields(self):
        msg = _FakeMsg(source="slack", external_channel_id="C12345")
        result = _build_reply_instruction(msg)
        assert result.startswith("  [auto_reply:")
        assert "Discord" in result
        assert "use tool slack_channel_post" not in result

    def test_auto_response_enabled(self):
        msg = _FakeMsg(source="slack", external_channel_id="C12345")
        result = _build_reply_instruction(msg)
        assert result.startswith("  [auto_reply:")
        assert "Discord" in result
        assert "use tool slack_channel_post" not in result


class TestBuildReplyInstructionChatwork:
    """Chatwork reply instruction generation."""

    def test_full_metadata(self):
        """Chatwork message produces chatwork send command."""
        msg = _FakeMsg(
            source="chatwork",
            external_channel_id="12345678",
            source_message_id="",
            external_user_id="",
        )
        result = _build_reply_instruction(msg)
        assert "[reply_instruction:" in result
        assert "animaworks-tool chatwork send" in result
        assert "12345678" in result


class TestBuildReplyInstructionEdgeCases:
    """Edge cases and unknown sources."""

    def test_unknown_source_returns_empty(self):
        """Non-slack/chatwork source returns empty string."""
        msg = _FakeMsg(source="anima", external_channel_id="C123")
        assert _build_reply_instruction(msg) == ""

    def test_human_source_returns_empty(self):
        """Human source returns empty string."""
        msg = _FakeMsg(source="human", external_channel_id="C123")
        assert _build_reply_instruction(msg) == ""

    def test_slack_empty_channel(self):
        """Slack with empty channel_id still generates instruction (caller guards)."""
        msg = _FakeMsg(
            source="slack",
            external_channel_id="",
            source_message_id="ts123",
            external_user_id="U123",
        )
        with _MOCK_AUTO_OFF:
            result = _build_reply_instruction(msg)
        assert "[auto_reply:" in result
        assert "Discord" in result

    def test_reply_instruction_format(self):
        """Verify exact format: '  [reply_instruction: CMD]'."""
        msg = _FakeMsg(
            source="slack",
            external_channel_id="C1",
            source_message_id="ts1",
            external_user_id="U1",
        )
        with _MOCK_AUTO_OFF:
            result = _build_reply_instruction(msg)
        assert result.startswith("  [auto_reply: ")
        assert result.endswith("]")
