from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

import server.routes.room as room_routes
from core.supervisor.ipc import IPCResponse
from server.room_manager import RoomManager
from server.routes.room import _build_compact_meeting_context, _meeting_stream


def _event_payload(frame: str) -> tuple[str, dict[str, Any]]:
    event = ""
    data = "{}"
    for line in frame.splitlines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data = line.removeprefix("data: ")
    return event, json.loads(data)


class _Supervisor:
    def __init__(self) -> None:
        self.processes = {"sakura": object(), "rin": object()}
        self.calls: list[str] = []

    async def send_request_stream(
        self,
        *,
        anima_name: str,
        method: str,
        params: dict[str, Any],
        timeout: float,
    ) -> AsyncIterator[IPCResponse]:
        self.calls.append(anima_name)
        if anima_name == "sakura":
            yield IPCResponse(
                id="req_sakura",
                error={"code": "IPC_TIMEOUT", "message": "stream timed out"},
            )
            return

        yield IPCResponse(
            id="req_rin",
            stream=True,
            chunk=json.dumps({"type": "text_delta", "text": "参加者から見ます。"}),
        )
        yield IPCResponse(
            id="req_rin",
            done=True,
            result={"response": "参加者から見ます。", "cycle_result": {"summary": "参加者から見ます。"}},
        )


class _DeltaOnlySupervisor:
    def __init__(self) -> None:
        self.processes = {"sakura": object()}

    async def send_request_stream(
        self,
        *,
        anima_name: str,
        method: str,
        params: dict[str, Any],
        timeout: float,
    ) -> AsyncIterator[IPCResponse]:
        yield IPCResponse(
            id="req_sakura",
            stream=True,
            chunk=json.dumps({"type": "text_delta", "text": "短く返します。"}),
        )
        yield IPCResponse(id="req_sakura", done=True, result={})


class _DuplicatedDoneSupervisor:
    def __init__(self) -> None:
        self.processes = {"karen": object()}

    async def send_request_stream(
        self,
        *,
        anima_name: str,
        method: str,
        params: dict[str, Any],
        timeout: float,
    ) -> AsyncIterator[IPCResponse]:
        yield IPCResponse(
            id="req_karen",
            stream=True,
            chunk=json.dumps({"type": "text_delta", "text": "Karen says ok."}),
        )
        yield IPCResponse(
            id="req_karen",
            done=True,
            result={
                "response": "Karen says ok.Karen says ok.",
                "cycle_result": {"summary": "Karen says ok.Karen says ok."},
            },
        )


class _AllParticipantsSupervisor:
    def __init__(self) -> None:
        self.processes = {"sakura": object(), "rin": object(), "yui": object()}
        self.calls: list[str] = []
        self.timeouts: list[float] = []

    async def send_request_stream(
        self,
        *,
        anima_name: str,
        method: str,
        params: dict[str, Any],
        timeout: float,
    ) -> AsyncIterator[IPCResponse]:
        self.calls.append(anima_name)
        self.timeouts.append(timeout)
        response = f"{anima_name} response"
        yield IPCResponse(
            id=f"req_{anima_name}",
            done=True,
            result={"response": response},
        )


class _KeepaliveOnlySupervisor:
    def __init__(self) -> None:
        self.processes = {"kanna": object()}

    async def send_request_stream(
        self,
        *,
        anima_name: str,
        method: str,
        params: dict[str, Any],
        timeout: float,
    ) -> AsyncIterator[IPCResponse]:
        while True:
            await asyncio.sleep(0.01)
            yield IPCResponse(
                id=f"req_{anima_name}",
                stream=True,
                chunk=json.dumps({"type": "keepalive"}),
            )


@pytest.mark.asyncio
async def test_meeting_stream_surfaces_ipc_error_and_falls_back_to_participants(tmp_path: Path):
    manager = RoomManager(tmp_path / "meetings")
    room = manager.create_room(
        participants=["sakura", "rin"],
        chair="sakura",
        created_by="taka",
        title="test",
    )
    supervisor = _Supervisor()

    frames = [
        frame
        async for frame in _meeting_stream(
            room.room_id,
            "議論を始めましょう",
            "taka",
            manager,
            supervisor,
        )
    ]

    events = [_event_payload(frame) for frame in frames]

    assert events[0] == ("speaker_queue", {"speakers": ["rin", "sakura"]})
    assert events[1] == ("speaker_start", {"speaker": "rin", "role": "participant"})
    assert any(
        event == "error" and payload["code"] == "IPC_TIMEOUT" and payload["speaker"] == "sakura"
        for event, payload in events
    )
    assert ("speaker_start", {"speaker": "sakura", "role": "chair"}) in events
    assert ("speaker_end", {"speaker": "sakura"}) in events
    assert ("speaker_start", {"speaker": "rin", "role": "participant"}) in events
    assert supervisor.calls == ["rin", "sakura"]

    stored_room = manager.get_room(room.room_id)
    assert stored_room is not None
    assert [(m["speaker"], m["text"]) for m in stored_room.conversation] == [
        ("taka", "議論を始めましょう"),
        ("rin", "参加者から見ます。"),
    ]


@pytest.mark.asyncio
async def test_meeting_stream_preserves_text_delta_when_done_result_is_empty(tmp_path: Path):
    manager = RoomManager(tmp_path / "meetings")
    room = manager.create_room(
        participants=["sakura"],
        chair="sakura",
        created_by="taka",
        title="test",
    )
    supervisor = _DeltaOnlySupervisor()

    frames = [
        frame
        async for frame in _meeting_stream(
            room.room_id,
            "短く返してください",
            "taka",
            manager,
            supervisor,
        )
    ]

    events = [_event_payload(frame) for frame in frames]

    assert ("text_delta", {"text": "短く返します。", "speaker": "sakura"}) in events
    assert not any(event == "error" and payload["code"] == "EMPTY_RESPONSE" for event, payload in events)

    stored_room = manager.get_room(room.room_id)
    assert stored_room is not None
    assert [(m["speaker"], m["text"]) for m in stored_room.conversation] == [
        ("taka", "短く返してください"),
        ("sakura", "短く返します。"),
    ]


@pytest.mark.asyncio
async def test_meeting_stream_does_not_store_duplicated_done_response_after_delta(tmp_path: Path):
    manager = RoomManager(tmp_path / "meetings")
    room = manager.create_room(
        participants=["karen"],
        chair="karen",
        created_by="taka",
        title="test",
    )
    supervisor = _DuplicatedDoneSupervisor()

    frames = [
        frame
        async for frame in _meeting_stream(
            room.room_id,
            "please check",
            "taka",
            manager,
            supervisor,
        )
    ]

    events = [_event_payload(frame) for frame in frames]

    assert ("speaker_queue", {"speakers": ["karen"]}) in events
    assert ("text_delta", {"text": "Karen says ok.", "speaker": "karen"}) in events

    stored_room = manager.get_room(room.room_id)
    assert stored_room is not None
    assert [(m["speaker"], m["text"]) for m in stored_room.conversation] == [
        ("taka", "please check"),
        ("karen", "Karen says ok."),
    ]


@pytest.mark.asyncio
async def test_meeting_stream_routes_everyone_request_to_participants_before_chair(tmp_path: Path):
    manager = RoomManager(tmp_path / "meetings")
    room = manager.create_room(
        participants=["sakura", "rin", "yui"],
        chair="sakura",
        created_by="taka",
        title="test",
    )
    supervisor = _AllParticipantsSupervisor()

    frames = [
        frame
        async for frame in _meeting_stream(
            room.room_id,
            "それぞれ返事してください",
            "taka",
            manager,
            supervisor,
        )
    ]

    events = [_event_payload(frame) for frame in frames]

    assert supervisor.calls == ["rin", "yui", "sakura"]
    assert all(timeout >= room_routes.MEETING_MIN_STREAM_TIMEOUT for timeout in supervisor.timeouts)
    assert events[0] == ("speaker_queue", {"speakers": ["rin", "yui", "sakura"]})
    assert events[1] == ("speaker_start", {"speaker": "rin", "role": "participant"})


@pytest.mark.asyncio
async def test_meeting_stream_wall_timeout_ends_keepalive_only_speaker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(room_routes, "MEETING_MIN_STREAM_TIMEOUT", 0.03)
    monkeypatch.setattr(room_routes, "MEETING_MAX_STREAM_TIMEOUT", 0.05)
    manager = RoomManager(tmp_path / "meetings")
    room = manager.create_room(
        participants=["kanna"],
        chair="kanna",
        created_by="taka",
        title="test",
    )
    supervisor = _KeepaliveOnlySupervisor()

    frames = [
        frame
        async for frame in _meeting_stream(
            room.room_id,
            "応答してください",
            "taka",
            manager,
            supervisor,
        )
    ]

    events = [_event_payload(frame) for frame in frames]

    assert events[0] == ("speaker_queue", {"speakers": ["kanna"]})
    assert events[1] == ("speaker_start", {"speaker": "kanna", "role": "chair"})
    assert any(
        event == "error" and payload["code"] == "STREAM_TIMEOUT" and payload["speaker"] == "kanna"
        for event, payload in events
    )
    assert ("speaker_end", {"speaker": "kanna"}) in events
    assert not any(event == "error" and payload["code"] == "EMPTY_RESPONSE" for event, payload in events)

    stored_room = manager.get_room(room.room_id)
    assert stored_room is not None
    assert [(m["speaker"], m["text"]) for m in stored_room.conversation] == [
        ("taka", "応答してください"),
    ]


def test_compact_meeting_context_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(room_routes, "MEETING_CONTEXT_MAX_MESSAGES", 2)
    monkeypatch.setattr(room_routes, "MEETING_CONTEXT_MAX_CHARS", 120)
    monkeypatch.setattr(room_routes, "MEETING_CONTEXT_ENTRY_MAX_CHARS", 80)
    manager = RoomManager(tmp_path / "meetings")
    room = manager.create_room(
        participants=["sakura", "rin"],
        chair="sakura",
        created_by="taka",
        title="test",
    )
    manager.append_message(room.room_id, "taka", "human", "old " + ("x" * 200))
    manager.append_message(room.room_id, "rin", "participant", "middle " + ("y" * 200))
    manager.append_message(room.room_id, "sakura", "chair", "latest " + ("z" * 200))
    room = manager.get_room(room.room_id)
    assert room is not None

    context = _build_compact_meeting_context(room)

    assert "old " not in context
    assert "latest " in context
    assert len(context) <= room_routes.MEETING_CONTEXT_MAX_CHARS + len("[older meeting context truncated]\n")
