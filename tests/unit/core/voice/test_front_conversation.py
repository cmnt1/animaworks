# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the transport-agnostic front conversation service."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.i18n import t
from core.voice.front_conversation import (
    ASK_ANIMA_DELEGATION_NOTE,
    VOICE_MODE_SUFFIX,
    FrontConversation,
)
from core.voice.voice_config import load_per_anima_voice_front


def _make_lane(*deltas: str, healthy: bool = True) -> MagicMock:
    lane = MagicMock()
    lane.check_health = AsyncMock(return_value=healthy)
    lane.reset_turn = MagicMock()

    async def stream(_text: str, **_kwargs):
        for delta in deltas:
            yield delta

    lane.stream = stream
    return lane


def _make_conversation(supervisor: MagicMock | None = None, **kwargs) -> FrontConversation:
    return FrontConversation(
        anima_name="aoi",
        supervisor=supervisor or MagicMock(),
        front_model="openai/qwen3.6-35b-a3b",
        front_api_base="http://localhost:8000/v1",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_stream_turn_yields_deltas_and_exposes_completion_metadata() -> None:
    conversation = _make_conversation()
    lane = _make_lane("こんにちは", '！ <!-- emotion: {"emotion": "smile"} -->')
    conversation.set_lane(lane)
    record = AsyncMock()

    with patch.object(conversation, "record_conversation", record):
        deltas = [
            delta
            async for delta in conversation.stream_turn(
                "やあ",
                from_person="human",
            )
        ]

    assert deltas == ["こんにちは", '！ <!-- emotion: {"emotion": "smile"} -->']
    assert conversation.last_full_text == "".join(deltas)
    assert conversation.last_emotion == "smile"
    assert conversation.last_completed is True
    lane.reset_turn.assert_called_once_with()
    record.assert_awaited_once_with("やあ", "".join(deltas), "human", record_user=True)


@pytest.mark.asyncio
async def test_ask_anima_returns_ack_then_queues_and_drains_result() -> None:
    captured: dict = {}

    async def stream(**kwargs):
        captured.update(kwargs)
        yield SimpleNamespace(done=True, chunk=None, result={"cycle_result": {"summary": "調査が完了しました"}})

    supervisor = MagicMock()
    supervisor.send_request_stream = MagicMock(side_effect=stream)
    conversation = _make_conversation(supervisor)

    ack = conversation.ask_anima("  調査して  ")
    assert ack == "受理しました (job 1)。完了したら知らせます"
    assert not conversation.has_delegation_results()

    await asyncio.wait_for(conversation.wait_delegation_done(), timeout=1)

    assert not conversation.has_pending_delegations()
    assert conversation.has_delegation_results()
    assert conversation.drain_delegation_results() == "[ask_anima完了 job 1: 調査が完了しました]"
    assert not conversation.has_delegation_results()
    assert captured["anima_name"] == "aoi"
    assert captured["method"] == "process_message"
    assert captured["params"]["message"] == "調査して" + ASK_ANIMA_DELEGATION_NOTE
    assert captured["params"]["voice_mode"] is False


@pytest.mark.asyncio
async def test_ask_anima_allows_only_one_running_delegation() -> None:
    release = asyncio.Event()
    started = asyncio.Event()

    async def stream(**_kwargs):
        started.set()
        await release.wait()
        yield SimpleNamespace(done=True, chunk=None, result={"cycle_result": {"summary": "done"}})

    supervisor = MagicMock()
    supervisor.send_request_stream = MagicMock(side_effect=stream)
    conversation = _make_conversation(supervisor, max_concurrent_delegations=2)

    assert conversation.ask_anima("first") == "受理しました (job 1)。完了したら知らせます"
    await asyncio.wait_for(started.wait(), timeout=1)
    assert conversation.ask_anima("second") == t("voice.ask_anima_in_progress", job=1, request="first")
    assert conversation.has_pending_delegations()
    supervisor.send_request_stream.assert_called_once()

    release.set()
    await asyncio.wait_for(conversation.wait_delegation_done(), timeout=1)
    assert not conversation.has_pending_delegations()

    assert conversation.ask_anima("after completion") == "受理しました (job 2)。完了したら知らせます"
    await asyncio.wait_for(conversation.wait_delegation_done(), timeout=1)
    assert supervisor.send_request_stream.call_count == 2


@pytest.mark.asyncio
async def test_stream_turn_prepends_drained_delegation_results() -> None:
    async def delegated_stream(**_kwargs):
        yield SimpleNamespace(done=True, chunk=None, result={"cycle_result": {"summary": "完了"}})

    supervisor = MagicMock()
    supervisor.send_request_stream = MagicMock(side_effect=delegated_stream)
    conversation = _make_conversation(supervisor)
    assert conversation.ask_anima("作業")
    await asyncio.wait_for(conversation.wait_delegation_done(), timeout=1)

    streamed_inputs: list[str] = []
    lane = MagicMock()
    lane.reset_turn = MagicMock()

    async def front_stream(text: str, **_kwargs):
        streamed_inputs.append(text)
        yield "報告します"

    lane.stream = front_stream
    conversation.set_lane(lane)
    with patch.object(conversation, "record_conversation", AsyncMock()):
        deltas = [delta async for delta in conversation.stream_turn("次の話題", from_person="human")]

    assert streamed_inputs == ["[ask_anima完了 job 1: 完了]\n\n次の話題"]
    assert deltas == ["報告します"]
    assert not conversation.has_delegation_results()


@pytest.mark.asyncio
async def test_stream_turn_stops_when_should_stop_becomes_true() -> None:
    stopped = False
    conversation = _make_conversation()
    lane = MagicMock()
    lane.reset_turn = MagicMock()

    async def stream(_text: str, **_kwargs):
        nonlocal stopped
        yield "first"
        stopped = True
        yield "discarded"

    lane.stream = stream
    conversation.set_lane(lane)
    record = AsyncMock()

    with patch.object(conversation, "record_conversation", record):
        deltas = [
            delta
            async for delta in conversation.stream_turn(
                "prompt",
                from_person="human",
                should_stop=lambda: stopped,
            )
        ]

    assert deltas == ["first"]
    assert conversation.last_full_text == "first"
    assert conversation.last_completed is False
    record.assert_not_awaited()


@pytest.mark.parametrize(
    ("record", "record_user", "should_record_user"),
    [(True, True, True), (True, False, False), (False, True, None)],
)
@pytest.mark.asyncio
async def test_stream_turn_respects_record_flags(
    record: bool, record_user: bool, should_record_user: bool | None
) -> None:
    conversation = _make_conversation()
    conversation.set_lane(_make_lane("返答"))
    record_method = AsyncMock()

    with patch.object(conversation, "record_conversation", record_method):
        async for _delta in conversation.stream_turn(
            "user prompt",
            from_person="alice",
            record=record,
            record_user=record_user,
        ):
            pass

    if should_record_user is None:
        record_method.assert_not_awaited()
    else:
        record_method.assert_awaited_once_with(
            "user prompt",
            "返答",
            "alice",
            record_user=should_record_user,
        )


@pytest.mark.asyncio
async def test_deferred_conversation_record_waits_for_transport_queueing() -> None:
    conversation = _make_conversation()
    conversation.set_lane(_make_lane("complete"))
    record = AsyncMock()

    with patch.object(conversation, "record_conversation", record):
        deltas = [
            delta
            async for delta in conversation.stream_turn(
                "prompt",
                from_person="human",
                defer_record=True,
            )
        ]
        record.assert_not_awaited()
        await conversation.record_pending_turn()

    assert deltas == ["complete"]
    record.assert_awaited_once_with("prompt", "complete", "human", record_user=True)


@pytest.mark.asyncio
async def test_check_health_returns_false_for_unhealthy_enabled_lane() -> None:
    conversation = _make_conversation()
    lane = _make_lane(healthy=False)
    conversation.set_lane(lane)

    assert conversation.enabled is True
    assert await conversation.check_health() is False
    lane.check_health.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_stream_full_agent_calls_process_message_with_voice_params() -> None:
    response = object()
    captured: dict = {}

    async def stream(**kwargs):
        captured.update(kwargs)
        yield response

    supervisor = MagicMock()
    supervisor.send_request_stream = MagicMock(side_effect=stream)
    conversation = _make_conversation(supervisor, ipc_timeout=42.0)

    items = [item async for item in conversation.stream_full_agent("hello", from_person="alice")]

    assert items == [response]
    assert captured == {
        "anima_name": "aoi",
        "method": "process_message",
        "params": {
            "message": "hello" + VOICE_MODE_SUFFIX,
            "from_person": "alice",
            "intent": "",
            "stream": True,
            "voice_mode": True,
            "images": [],
            "attachment_paths": [],
        },
        "timeout": 42.0,
    }


def test_load_per_anima_voice_front_prefers_status_json(tmp_path) -> None:
    anima_dir = tmp_path / "animas" / "aoi"
    anima_dir.mkdir(parents=True)
    (anima_dir / "status.json").write_text(
        json.dumps({"voice": {"front_model": "local/fast", "front_api_base": "http://per-anima"}}),
        encoding="utf-8",
    )
    global_config = SimpleNamespace(front_model="global/model", front_api_base="http://global")

    assert load_per_anima_voice_front(tmp_path / "animas", "aoi", global_config) == (
        "local/fast",
        "http://per-anima",
    )


def test_load_per_anima_voice_front_falls_back_to_global_config(tmp_path) -> None:
    global_config = SimpleNamespace(front_model="global/model", front_api_base="http://global")

    assert load_per_anima_voice_front(tmp_path, "missing", global_config) == (
        "global/model",
        "http://global",
    )


@pytest.mark.asyncio
async def test_record_conversation_uses_running_anima_ipc() -> None:
    handle = MagicMock()
    handle.is_alive.return_value = True
    handle.state = SimpleNamespace(value="running")
    supervisor = MagicMock()
    supervisor.processes = {"aoi": handle}
    supervisor.send_request = AsyncMock()
    conversation = _make_conversation(supervisor)

    await conversation.record_conversation("hello", "hi", "alice", record_user=False)

    supervisor.send_request.assert_awaited_once_with(
        "aoi",
        "append_conversation_turns",
        {
            "thread_id": "default",
            "turns": [{"role": "assistant", "content": "hi"}],
        },
    )
