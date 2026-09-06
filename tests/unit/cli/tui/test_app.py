# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio

import pytest

from cli.tui.app import AnimaChatApp
from cli.tui.sse import SseEvent
from cli.tui.widgets import ToolCard


class FakeClient:
    """A stub AnimaWorksClient with the same async interface."""

    def __init__(self, *, animas=None, history=None, ws_events=None):
        self.animas = animas or [{"name": "sora", "status": "idle"}]
        self.history = history or {"sessions": []}
        self._ws_events = ws_events or []
        self.interrupt_calls = 0
        self.messages = []
        self.chat_queue: asyncio.Queue = asyncio.Queue()

    async def list_animas(self):
        return self.animas

    async def get_history(self, anima, *, thread_id="default", limit=50):
        return self.history

    async def interrupt(self, anima, *, thread_id):
        self.interrupt_calls += 1
        return {"status": "interrupted"}

    async def chat_stream(self, anima, message, *, thread_id="default", resume=None, last_event_id=None):
        self.messages.append(message)
        while True:
            ev = await self.chat_queue.get()
            if ev is None:
                return
            yield ev

    async def ws_events(self):
        for ev in self._ws_events:
            yield ev
        await asyncio.Event().wait()


def _history_with(*messages):
    msgs = [{"ts": "1", "role": "human", "content": content} for content in messages]
    return {"sessions": [{"messages": msgs}]}


async def _pump(n=40):
    for _ in range(n):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_startup_shows_history():
    client = FakeClient(history=_history_with("Hello from history"))
    app = AnimaChatApp(client=client, anima_name="sora")
    async with app.run_test() as _:
        await _pump()
        from cli.tui.widgets import HumanTurn

        turns = list(app.query(HumanTurn))
        assert len(turns) >= 1
        assert any("Hello from history" in t._text for t in turns)


@pytest.mark.asyncio
async def test_streaming_renders_text_and_tool_card():
    client = FakeClient()
    app = AnimaChatApp(client=client, anima_name="sora")
    async with app.run_test() as pilot:
        await _pump()
        app.input_container.focus_input()
        await _pump()
        await pilot.press("h", "e", "l", "l", "o")
        await pilot.press("enter")
        await _pump()

        assert client.messages == ["hello"]

        # Feed a full streaming sequence.
        await client.chat_queue.put(SseEvent("text_delta", {"text": "part1 "}))
        await client.chat_queue.put(SseEvent("text_delta", {"text": "part2"}))
        await client.chat_queue.put(SseEvent("tool_start", {"tool_name": "Bash", "tool_id": "t1"}))
        await client.chat_queue.put(
            SseEvent("tool_end", {"tool_id": "t1", "tool_name": "Bash", "result_summary": "ok"})
        )
        await client.chat_queue.put(SseEvent("done", {"summary": "final summary"}))
        await client.chat_queue.put(None)
        await _pump()

        assert app.current is not None
        assert "final summary" in app.current._body
        assert len(list(app.query(ToolCard))) == 1


@pytest.mark.asyncio
async def test_escape_calls_interrupt_when_busy():
    client = FakeClient()
    app = AnimaChatApp(client=client, anima_name="sora")
    async with app.run_test() as _:
        await _pump()
        app.busy = True
        app.action_maybe_interrupt()
        await _pump()
        assert client.interrupt_calls == 1
        assert app.busy is False


@pytest.mark.asyncio
async def test_escape_does_nothing_when_idle():
    client = FakeClient()
    app = AnimaChatApp(client=client, anima_name="sora")
    async with app.run_test() as _:
        await _pump()
        app.busy = False
        app.action_maybe_interrupt()
        await _pump()
        assert client.interrupt_calls == 0


@pytest.mark.asyncio
async def test_thinking_toggle():
    client = FakeClient()
    app = AnimaChatApp(client=client, anima_name="sora")
    async with app.run_test() as _:
        await _pump()
        assert app.show_thinking is False
        await app._handle_message("/thinking")
        assert app.show_thinking is True
        await app._handle_message("/thinking")
        assert app.show_thinking is False


@pytest.mark.asyncio
async def test_unknown_command_not_sent_to_server():
    client = FakeClient()
    app = AnimaChatApp(client=client, anima_name="sora")
    async with app.run_test() as _:
        await _pump()
        await app._handle_message("/definitely-not-a-command")
        await _pump()
        assert client.messages == []
