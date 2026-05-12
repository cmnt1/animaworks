# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""E2E regression for non-chat clean session isolation."""

from __future__ import annotations

import pytest

from core.execution._sdk_session import _load_session_id, _save_session_id
from core.execution.codex_sdk import _load_thread_id, _save_thread_id
from core.memory.shortterm import SessionState, ShortTermMemory, StreamCheckpoint
from tests.helpers.mocks import patch_agent_sdk

pytestmark = pytest.mark.e2e


async def test_inbox_run_clears_non_chat_residue_without_touching_chat(make_agent_core):
    agent = make_agent_core(name="non-chat-isolation", model="claude-sonnet-4-6")
    agent._sdk_available = True
    anima_dir = agent.anima_dir

    chat_shortterm = ShortTermMemory(anima_dir, session_type="chat")
    chat_shortterm.save(SessionState(session_id="chat-shortterm", trigger="message:admin"))
    _save_session_id(anima_dir, "chat-sdk-session", "chat")
    _save_thread_id(anima_dir, "chat-codex-thread", "chat")

    inbox_shortterm = ShortTermMemory(anima_dir, session_type="inbox", thread_id="inbox")
    inbox_shortterm.save(SessionState(session_id="stale-inbox-shortterm", trigger="inbox:sakura"))
    inbox_checkpoint = inbox_shortterm.save_checkpoint(
        StreamCheckpoint(
            trigger="inbox:sakura",
            original_prompt="old inbox prompt",
            completed_tools=[{"tool_name": "old", "tool_id": "tool-1", "summary": "old"}],
        )
    )
    _save_session_id(anima_dir, "stale-inbox-sdk-session", "inbox", thread_id="inbox")
    _save_thread_id(anima_dir, "stale-inbox-codex-thread", "inbox", "inbox")

    with patch_agent_sdk(response_text="inbox processed"):
        result = await agent.run_cycle(
            "process inbox",
            trigger="inbox:sakura",
            thread_id="inbox",
        )

    assert result.summary == "inbox processed"

    assert chat_shortterm.has_pending()
    assert _load_session_id(anima_dir, "chat") == "chat-sdk-session"
    assert _load_thread_id(anima_dir, "chat") == "chat-codex-thread"

    assert not inbox_shortterm.has_pending()
    assert not inbox_checkpoint.exists()
    assert _load_session_id(anima_dir, "inbox", thread_id="inbox") is None
    assert _load_thread_id(anima_dir, "inbox", "inbox") is None
