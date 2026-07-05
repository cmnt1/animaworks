from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from core._agent_cycle import CycleMixin


class _ToolHandlerStub:
    def bind_runtime_session(self, ctx):
        self.ctx = ctx

    def set_active_session_type(self, session_type):
        self.session_type = session_type
        return None


class _StreamingAgentStub(CycleMixin):
    def __init__(self) -> None:
        self._tool_handler = _ToolHandlerStub()

    @asynccontextmanager
    async def _get_agent_lock(self, thread_id):
        yield

    async def _run_cycle_streaming_inner(self, *args, **kwargs):
        yield {"type": "text_delta", "text": "ok"}
        yield {
            "type": "cycle_done",
            "cycle_result": {
                "trigger": "message:cmnt",
                "session_type": "chat",
                "thread_id": "default",
                "request_id": "stale-request",
                "tool_session_id": "stale-tool-session",
                "summary": "ok",
            },
        }


@pytest.mark.asyncio
async def test_streaming_cycle_done_metadata_uses_runtime_context() -> None:
    agent = _StreamingAgentStub()

    events = [
        event
        async for event in agent.run_cycle_streaming(
            "meeting prompt",
            trigger="message:cmnt",
            thread_id="meeting-room-1",
        )
    ]

    result = events[-1]["cycle_result"]
    assert result["trigger"] == "message:cmnt"
    assert result["session_type"] == "chat"
    assert result["thread_id"] == "meeting-room-1"
    assert result["request_id"] != "stale-request"
    assert result["tool_session_id"] != "stale-tool-session"
