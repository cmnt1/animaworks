from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for external reply metadata in inbox message formatting.

Verifies that when external platform messages are received via Messenger
and processed through InboxMixin._process_inbox_messages, the formatted
output contains the current reply metadata instead of the old
[platform=... channel=... ts=...] format.
"""

import json
from pathlib import Path
from unittest.mock import patch

from core.messenger import Messenger


def _create_external_inbox_message(
    shared_dir: Path,
    to_name: str,
    *,
    source: str = "slack",
    from_person: str = "slack:U12345",
    content: str = "hello from slack",
    external_channel_id: str = "C67890",
    source_message_id: str = "1709123456.789012",
    external_user_id: str = "U12345",
    external_thread_ts: str = "",
) -> Path:
    """Create a synthetic external platform inbox message file."""
    inbox_dir = shared_dir / "inbox" / to_name
    inbox_dir.mkdir(parents=True, exist_ok=True)

    msg_data = {
        "id": f"test-{source}-msg-001",
        "from_person": from_person,
        "to_person": to_name,
        "content": content,
        "type": "message",
        "source": source,
        "external_channel_id": external_channel_id,
        "source_message_id": source_message_id,
        "external_user_id": external_user_id,
        "external_thread_ts": external_thread_ts,
    }

    msg_path = inbox_dir / f"test-{source}-msg-001.json"
    msg_path.write_text(json.dumps(msg_data, ensure_ascii=False), encoding="utf-8")
    return msg_path


class TestReplyInstructionInInboxFormatting:
    """Verify reply metadata appears in formatted inbox output."""

    def test_slack_message_has_auto_reply_instruction(self, tmp_path: Path) -> None:
        """Slack inbox message gets Discord migration auto-reply metadata."""
        shared = tmp_path / "shared"
        _create_external_inbox_message(shared, "alice", source="slack")

        messenger = Messenger(shared_dir=shared, anima_name="alice")
        items = messenger.receive_with_paths()
        assert len(items) == 1

        msg = items[0].msg
        from core._anima_inbox import _build_reply_instruction

        result = _build_reply_instruction(msg)

        assert "auto_reply" in result
        assert "reply_instruction" not in result
        assert "Slackは廃止されました" in result
        assert "slack_channel_postは使用できません" in result
        assert "platform=" not in result

    def test_discord_message_has_reply_instruction(self, tmp_path: Path) -> None:
        """Discord inbox message gets tool-based [reply_instruction: ...]."""
        shared = tmp_path / "shared"
        _create_external_inbox_message(
            shared,
            "alice",
            source="discord",
            from_person="discord:U12345",
            external_thread_ts="T67890",
        )

        messenger = Messenger(shared_dir=shared, anima_name="alice")
        items = messenger.receive_with_paths()
        msg = items[0].msg

        from core._anima_inbox import _build_reply_instruction

        with patch("core._anima_inbox._is_auto_response_enabled_discord", return_value=False):
            result = _build_reply_instruction(msg)

        assert "reply_instruction" in result
        assert "use tool discord_channel_post" in result
        assert 'channel_id="C67890"' in result
        assert 'text="<@U12345> {返信内容}"' in result
        assert 'thread_id="T67890"' in result
        assert "platform=" not in result

    def test_chatwork_message_has_reply_instruction(self, tmp_path: Path) -> None:
        """Chatwork inbox message gets [reply_instruction: ...] for chatwork."""
        shared = tmp_path / "shared"
        _create_external_inbox_message(
            shared,
            "alice",
            source="chatwork",
            from_person="chatwork:12345678",
            external_channel_id="12345678",
            source_message_id="",
            external_user_id="",
        )

        messenger = Messenger(shared_dir=shared, anima_name="alice")
        items = messenger.receive_with_paths()
        msg = items[0].msg

        from core._anima_inbox import _build_reply_instruction

        result = _build_reply_instruction(msg)

        assert "reply_instruction" in result
        assert "animaworks-tool chatwork send" in result
        assert "12345678" in result

    def test_discord_no_thread_when_ts_missing(self, tmp_path: Path) -> None:
        """Discord message without thread id omits thread_id from reply instruction."""
        shared = tmp_path / "shared"
        _create_external_inbox_message(
            shared,
            "alice",
            source="discord",
            from_person="discord:U12345",
            external_thread_ts="",
        )

        messenger = Messenger(shared_dir=shared, anima_name="alice")
        items = messenger.receive_with_paths()
        msg = items[0].msg

        from core._anima_inbox import _build_reply_instruction

        with patch("core._anima_inbox._is_auto_response_enabled_discord", return_value=False):
            result = _build_reply_instruction(msg)
        assert "thread_id=" not in result
        assert "discord_channel_post" in result

    def test_discord_no_mention_when_user_id_missing(self, tmp_path: Path) -> None:
        """Discord message without external_user_id omits @mention."""
        shared = tmp_path / "shared"
        _create_external_inbox_message(
            shared,
            "alice",
            source="discord",
            from_person="discord:",
            external_user_id="",
        )

        messenger = Messenger(shared_dir=shared, anima_name="alice")
        items = messenger.receive_with_paths()
        msg = items[0].msg

        from core._anima_inbox import _build_reply_instruction

        with patch("core._anima_inbox._is_auto_response_enabled_discord", return_value=False):
            result = _build_reply_instruction(msg)
        assert "<@" not in result
        assert "discord_channel_post" in result

    def test_no_reply_instruction_without_channel_id(self, tmp_path: Path) -> None:
        """Message without external_channel_id gets no reply instruction (caller guard)."""
        shared = tmp_path / "shared"
        _create_external_inbox_message(
            shared,
            "alice",
            source="slack",
            external_channel_id="",
        )

        messenger = Messenger(shared_dir=shared, anima_name="alice")
        items = messenger.receive_with_paths()
        msg = items[0].msg

        assert msg.external_channel_id == ""
