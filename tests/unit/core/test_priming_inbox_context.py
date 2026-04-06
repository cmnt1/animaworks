"""Unit tests for _get_recent_human_messages inbox trigger support."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_agent(anima_dir: Path, model: str = "claude-sonnet-4-20250514"):
    """Create AgentCore with all external dependencies mocked."""
    from core.schemas import ModelConfig

    mc = ModelConfig(model=model, api_key="test-key")
    memory = MagicMock()
    memory.read_permissions.return_value = ""
    memory.anima_dir = anima_dir
    memory.collect_distilled_knowledge.return_value = []

    messenger = MagicMock()

    with (
        patch("core.agent.ToolHandler"),
        patch("core.agent.AgentCore._check_sdk", return_value=False),
        patch("core.agent.AgentCore._init_tool_registry", return_value=[]),
        patch("core.agent.AgentCore._discover_personal_tools", return_value={}),
        patch("core.agent.AgentCore._create_executor") as mock_create,
    ):
        mock_executor = MagicMock()
        mock_create.return_value = mock_executor
        from core.agent import AgentCore

        agent = AgentCore(anima_dir, memory, mc, messenger)
        agent._executor = mock_executor
    return agent


class TestGetRecentHumanMessagesInbox:
    """_get_recent_human_messages should activate for inbox:* triggers."""

    def test_inbox_trigger_returns_messages(self, tmp_path: Path):
        agent = _make_agent(tmp_path)

        mock_turn = MagicMock()
        mock_turn.role = "human"
        mock_turn.content = "Hello from inbox"

        mock_state = MagicMock()
        mock_state.turns = [mock_turn]

        with patch("core.memory.conversation.ConversationMemory") as mock_conv_cls:
            mock_conv_cls.return_value.load.return_value = mock_state
            result = agent._get_recent_human_messages("inbox:alice")

        assert len(result) == 1
        assert result[0] == "Hello from inbox"

    def test_message_trigger_still_works(self, tmp_path: Path):
        """Regression: message:* trigger should still return messages."""
        agent = _make_agent(tmp_path)

        mock_turn = MagicMock()
        mock_turn.role = "human"
        mock_turn.content = "Hello from chat"

        mock_state = MagicMock()
        mock_state.turns = [mock_turn]

        with patch("core.memory.conversation.ConversationMemory") as mock_conv_cls:
            mock_conv_cls.return_value.load.return_value = mock_state
            result = agent._get_recent_human_messages("message:user1")

        assert len(result) == 1
        assert result[0] == "Hello from chat"

    def test_heartbeat_trigger_returns_empty(self, tmp_path: Path):
        """Regression: heartbeat trigger should still return empty."""
        agent = _make_agent(tmp_path)
        result = agent._get_recent_human_messages("heartbeat")
        assert result == []

    def test_cron_trigger_returns_empty(self, tmp_path: Path):
        """Regression: cron trigger should still return empty."""
        agent = _make_agent(tmp_path)
        result = agent._get_recent_human_messages("cron:daily")
        assert result == []

    def test_task_trigger_returns_empty(self, tmp_path: Path):
        """Regression: task trigger should still return empty."""
        agent = _make_agent(tmp_path)
        result = agent._get_recent_human_messages("task:abc123")
        assert result == []

    def test_inbox_with_multiple_senders(self, tmp_path: Path):
        agent = _make_agent(tmp_path)

        turns = []
        for msg in ["msg1", "msg2", "msg3"]:
            t = MagicMock()
            t.role = "human"
            t.content = msg
            turns.append(t)

        mock_state = MagicMock()
        mock_state.turns = turns

        with patch("core.memory.conversation.ConversationMemory") as mock_conv_cls:
            mock_conv_cls.return_value.load.return_value = mock_state
            result = agent._get_recent_human_messages("inbox:alice, bob")

        assert len(result) == 3

    def test_inbox_empty_conversation_returns_empty(self, tmp_path: Path):
        """When no conversation history exists, inbox should safely return empty."""
        agent = _make_agent(tmp_path)

        mock_state = MagicMock()
        mock_state.turns = []

        with patch("core.memory.conversation.ConversationMemory") as mock_conv_cls:
            mock_conv_cls.return_value.load.return_value = mock_state
            result = agent._get_recent_human_messages("inbox:alice")

        assert result == []

    def test_inbox_conversation_load_failure_returns_empty(self, tmp_path: Path):
        """If ConversationMemory fails to load, return empty gracefully."""
        agent = _make_agent(tmp_path)

        with patch("core.memory.conversation.ConversationMemory") as mock_conv_cls:
            mock_conv_cls.return_value.load.side_effect = FileNotFoundError("no session")
            result = agent._get_recent_human_messages("inbox:alice")

        assert result == []
