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


@pytest.mark.asyncio
async def test_list_skills():
    captured = {}

    def handler(request):
        captured["params"] = request.url.params
        return httpx.Response(
            200,
            json={"anima": "sora", "thread_id": "default", "skills": [{"ref": "r1", "name": "foo"}]},
        )

    client = AnimaWorksClient("http://localhost:18500", transport=httpx.MockTransport(handler))
    res = await client.list_skills("sora", thread_id="t1")
    assert res["skills"][0]["name"] == "foo"
    assert captured["params"]["thread_id"] == "t1"


@pytest.mark.asyncio
async def test_get_active_skills():
    def handler(request):
        return httpx.Response(200, json={"anima": "sora", "accepted": [{"ref": "r1"}], "rejections": []})

    client = AnimaWorksClient("http://localhost:18500", transport=httpx.MockTransport(handler))
    res = await client.get_active_skills("sora", thread_id="default")
    assert res["accepted"][0]["ref"] == "r1"


@pytest.mark.asyncio
async def test_set_active_skills_replace():
    captured = {}

    def handler(request):
        captured.update({"body": request.content.decode(), "path": request.url.path})
        return httpx.Response(200, json={"accepted": [{"ref": "r1"}], "rejections": [], "warnings": []})

    client = AnimaWorksClient("http://localhost:18500", transport=httpx.MockTransport(handler))
    await client.set_active_skills("sora", "t1", ["r1", "r2"], confirm_risk=True)
    assert captured["path"] == "/api/animas/sora/skills/active"
    import json

    body = json.loads(captured["body"])
    assert body["refs"] == ["r1", "r2"]
    assert body["thread_id"] == "t1"
    assert body["confirm_risk"] is True


@pytest.mark.asyncio
async def test_list_channels():
    client = AnimaWorksClient(
        "http://localhost:18500",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=[{"name": "dev"}])),
    )
    assert await client.list_channels() == [{"name": "dev"}]


@pytest.mark.asyncio
async def test_read_channel():
    captured = {}

    def handler(request):
        captured["params"] = request.url.params
        captured["path"] = request.url.path
        return httpx.Response(200, json={"channel": "dev", "messages": []})

    client = AnimaWorksClient("http://localhost:18500", transport=httpx.MockTransport(handler))
    await client.read_channel("dev", limit=10)
    assert captured["path"] == "/api/channels/dev"
    assert captured["params"]["limit"] == "10"


@pytest.mark.asyncio
async def test_post_channel():
    captured = {}

    def handler(request):
        captured.update({"body": request.content.decode(), "path": request.url.path})
        return httpx.Response(200, json={"status": "ok", "channel": "dev"})

    client = AnimaWorksClient(
        "http://localhost:18500",
        from_person="me",
        transport=httpx.MockTransport(handler),
    )
    res = await client.post_channel("dev", "hello")
    assert res["status"] == "ok"
    import json

    assert json.loads(captured["body"])["text"] == "hello"
    assert json.loads(captured["body"])["from_name"] == "me"


@pytest.mark.asyncio
async def test_list_tasks_assignee_param():
    captured = {}

    def handler(request):
        captured["params"] = request.url.params
        return httpx.Response(200, json={"tasks": []})

    client = AnimaWorksClient("http://localhost:18500", transport=httpx.MockTransport(handler))
    await client.list_tasks(assignee="sora")
    assert captured["params"]["assignee"] == "sora"


@pytest.mark.asyncio
async def test_resolve_interaction_posts_decision():
    captured = {}

    def handler(request):
        captured.update({"body": request.content.decode(), "path": request.url.path})
        return httpx.Response(200, json={"status": "ok", "decision": "approve"})

    client = AnimaWorksClient("http://localhost:18500", transport=httpx.MockTransport(handler))
    await client.resolve_interaction("sora", "cb1", "approve", comment="")
    assert captured["path"] == "/api/animas/sora/interactions/cb1/resolve"
    import json

    assert json.loads(captured["body"])["decision"] == "approve"


@pytest.mark.asyncio
async def test_resolve_interaction_409_raises():
    def handler(request):
        return httpx.Response(409, json={"detail": "Already resolved"})

    client = AnimaWorksClient("http://localhost:18500", transport=httpx.MockTransport(handler))
    with pytest.raises(AnimaWorksClientError):
        await client.resolve_interaction("sora", "cb1", "approve")
