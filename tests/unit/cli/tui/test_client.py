# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import httpx
import pytest

from cli.tui.client import (
    AnimaWorksClient,
    AnimaWorksClientError,
    _ws_url,
    parse_ws_message,
)

SSE_BODY = (
    "id: resp:1\n"
    "event: stream_start\n"
    'data: {"response_id": "resp"}\n'
    "\n"
    "id: resp:2\n"
    "event: text_delta\n"
    'data: {"text": "hello"}\n'
    "\n"
    "id: resp:3\n"
    "event: done\n"
    'data: {"summary": "done body"}\n'
    "\n"
)


def test_ws_url():
    assert _ws_url("http://localhost:18500") == "ws://localhost:18500/ws"
    assert _ws_url("https://example.com") == "wss://example.com/ws"
    assert _ws_url("http://h:1/") == "ws://h:1/ws"


def test_parse_ws_message_str():
    t, payload, pong = parse_ws_message('{"type": "ping", "ts": 1}')
    assert t == "ping"
    assert payload == {"ts": 1}
    assert pong is True


def test_parse_ws_message_event_key():
    t, payload, pong = parse_ws_message('{"event": "anima.status", "data": {"name": "a"}}')
    assert t == "anima.status"
    assert payload == {"name": "a"}
    assert pong is False


def test_parse_ws_message_bytes():
    t, payload, pong = parse_ws_message(b'{"type": "anima.tool_activity", "data": {}}')
    assert t == "anima.tool_activity"
    assert pong is False


def test_parse_ws_message_garbage():
    t, _, pong = parse_ws_message("not json")
    assert t == "_ws_status"
    assert pong is False


@pytest.mark.asyncio
async def test_list_animas():
    client = AnimaWorksClient(
        "http://localhost:18500",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=[{"name": "sora", "status": "idle"}])),
    )
    animas = await client.list_animas()
    assert animas == [{"name": "sora", "status": "idle"}]


@pytest.mark.asyncio
async def test_get_history_passes_params():
    captured = {}

    def handler(request):
        captured["params"] = request.url.params
        return httpx.Response(200, json={"sessions": []})

    client = AnimaWorksClient("http://localhost:18500", transport=httpx.MockTransport(handler))
    await client.get_history("sora", thread_id="t1", limit=20)
    assert captured["params"]["thread_id"] == "t1"
    assert captured["params"]["limit"] == "20"


@pytest.mark.asyncio
async def test_chat_stream_returns_events_in_order():
    client = AnimaWorksClient(
        "http://localhost:18500",
        timeout=None,
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, content=SSE_BODY.encode(), headers={"content-type": "text/event-stream"})
        ),
    )
    events = [ev async for ev in client.chat_stream("sora", "hi")]
    assert [e.event for e in events] == ["stream_start", "text_delta", "done"]
    assert events[1].data == {"text": "hello"}
    assert events[2].data == {"summary": "done body"}


@pytest.mark.asyncio
async def test_interrupt_posts_thread_id():
    captured = {}

    def handler(request):
        captured["params"] = request.url.params
        captured["path"] = request.url.path
        return httpx.Response(200, json={"status": "interrupted"})

    client = AnimaWorksClient("http://localhost:18500", transport=httpx.MockTransport(handler))
    res = await client.interrupt("sora", thread_id="t9")
    assert res == {"status": "interrupted"}
    assert captured["path"] == "/api/animas/sora/interrupt"
    assert captured["params"]["thread_id"] == "t9"


@pytest.mark.asyncio
async def test_chat_stream_http_error_raises_client_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = AnimaWorksClient("http://localhost:18500", transport=httpx.MockTransport(handler))
    with pytest.raises(AnimaWorksClientError):
        async for _ in client.chat_stream("sora", "hi"):
            pass
