# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the background meeting-round layer in server.routes.room.

A meeting round must survive client disconnects (page reloads): the round
runs as a background task, clients only subscribe to its event feed, and a
reloaded client can re-attach and read progress from round_status events.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import server.routes.room as room_routes
from server.routes.chat_chunk_handler import _format_sse
from server.routes.room import (
    _ACTIVE_ROUNDS,
    _ActiveRound,
    _parse_sse_event,
    _round_event_feed,
    _start_meeting_round,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    _ACTIVE_ROUNDS.clear()
    yield
    _ACTIVE_ROUNDS.clear()


class TestParseSseEvent:
    def test_round_trips_format_sse(self) -> None:
        frame = _format_sse("speaker_start", {"speaker": "sakura", "role": "chair"})
        event, payload = _parse_sse_event(frame)
        assert event == "speaker_start"
        assert payload == {"speaker": "sakura", "role": "chair"}

    def test_multiline_json_payload(self) -> None:
        frame = _format_sse("text_delta", {"text": "line1\nline2"})
        event, payload = _parse_sse_event(frame)
        assert event == "text_delta"
        assert payload == {"text": "line1\nline2"}

    def test_garbage_returns_empty(self) -> None:
        assert _parse_sse_event("not an sse frame") == ("", {})


class TestActiveRoundState:
    def test_note_event_tracks_progress(self) -> None:
        r = _ActiveRound("room1")
        r.note_event("speaker_queue", {"speakers": ["a", "b"]})
        assert r.speakers == ["a", "b"]

        r.note_event("speaker_start", {"speaker": "a"})
        assert r.current_speaker == "a"
        assert r.speaker_started_at is not None

        r.note_event("speaker_end", {"speaker": "a"})
        assert r.completed == ["a"]
        assert r.current_speaker == ""
        assert r.speaker_started_at is None

        status = r.status_payload()
        assert status["active"] is True
        assert status["remaining"] == ["b"]
        assert status["completed"] == ["a"]

    def test_redirect_target_joins_speakers(self) -> None:
        r = _ActiveRound("room1")
        r.note_event("speaker_queue", {"speakers": ["a"]})
        r.note_event("speaker_start", {"speaker": "z"})
        assert "z" in r.speakers


def _fake_round_frames(events, *, delay=0.0, progressed=None):
    """Build a _meeting_stream stand-in emitting the given (event, payload) list."""

    async def _gen(room_id, message, from_person, room_manager, supervisor):
        for event, payload in events:
            if delay:
                await asyncio.sleep(delay)
            if progressed is not None:
                progressed.append(event)
            yield _format_sse(event, payload)

    return _gen


class TestBackgroundRound:
    @pytest.mark.asyncio
    async def test_round_continues_after_listener_disconnect(self, monkeypatch) -> None:
        progressed: list[str] = []
        events = [
            ("speaker_queue", {"speakers": ["a", "b"]}),
            ("speaker_start", {"speaker": "a", "role": "chair"}),
            ("speaker_end", {"speaker": "a"}),
            ("speaker_start", {"speaker": "b", "role": "participant"}),
            ("speaker_end", {"speaker": "b"}),
            ("done", {"summary": "Meeting round complete"}),
        ]
        monkeypatch.setattr(
            room_routes,
            "_meeting_stream",
            _fake_round_frames(events, delay=0.01, progressed=progressed),
        )

        round_ = _start_meeting_round("room1", "msg", "human", None, None)
        feed = _round_event_feed(round_, snapshot=False)

        # Consume one frame, then drop the feed (simulates a page reload).
        first = await anext(feed)
        assert _parse_sse_event(first)[0] == "speaker_queue"
        await feed.aclose()

        await asyncio.wait_for(round_.task, timeout=5)

        assert progressed == [e for e, _ in events]
        assert round_.done is True
        assert round_.completed == ["a", "b"]
        assert "room1" not in _ACTIVE_ROUNDS

    @pytest.mark.asyncio
    async def test_second_round_rejected_while_active(self, monkeypatch) -> None:
        release = asyncio.Event()

        async def _blocking(room_id, message, from_person, room_manager, supervisor):
            await release.wait()
            yield _format_sse("done", {"summary": "ok"})

        monkeypatch.setattr(room_routes, "_meeting_stream", _blocking)

        round_ = _start_meeting_round("room1", "msg", "human", None, None)
        with pytest.raises(HTTPException) as exc_info:
            _start_meeting_round("room1", "msg2", "human", None, None)
        assert exc_info.value.status_code == 409

        release.set()
        await asyncio.wait_for(round_.task, timeout=5)
        # After completion a new round may start again.
        release.clear()
        round2 = _start_meeting_round("room1", "msg3", "human", None, None)
        release.set()
        await asyncio.wait_for(round2.task, timeout=5)

    @pytest.mark.asyncio
    async def test_attach_feed_gets_snapshot_then_live_events(self, monkeypatch) -> None:
        gate = asyncio.Event()

        async def _gated(room_id, message, from_person, room_manager, supervisor):
            yield _format_sse("speaker_queue", {"speakers": ["a"]})
            yield _format_sse("speaker_start", {"speaker": "a", "role": "chair"})
            await gate.wait()
            yield _format_sse("speaker_end", {"speaker": "a"})
            yield _format_sse("done", {"summary": "Meeting round complete"})

        monkeypatch.setattr(room_routes, "_meeting_stream", _gated)

        round_ = _start_meeting_round("room1", "msg", "human", None, None)
        # Let the round progress to mid-turn (speaker a is "speaking").
        for _ in range(50):
            if round_.current_speaker == "a":
                break
            await asyncio.sleep(0.01)
        assert round_.current_speaker == "a"

        # Late subscriber (reloaded client) attaches with a snapshot.
        feed = _round_event_feed(round_, snapshot=True)
        event, payload = _parse_sse_event(await anext(feed))
        assert event == "round_status"
        assert payload["current_speaker"] == "a"
        assert payload["active"] is True

        gate.set()
        received = [_parse_sse_event(f)[0] async for f in feed]
        assert received == ["speaker_end", "done"]
        await asyncio.wait_for(round_.task, timeout=5)

    @pytest.mark.asyncio
    async def test_round_failure_publishes_error_and_cleans_up(self, monkeypatch) -> None:
        async def _broken(room_id, message, from_person, room_manager, supervisor):
            yield _format_sse("speaker_queue", {"speakers": ["a"]})
            raise RuntimeError("boom")

        monkeypatch.setattr(room_routes, "_meeting_stream", _broken)

        round_ = _start_meeting_round("room1", "msg", "human", None, None)
        feed = _round_event_feed(round_, snapshot=False)
        events = [_parse_sse_event(f) async for f in feed]
        names = [e for e, _ in events]
        assert names == ["speaker_queue", "error", "done"]
        assert events[1][1]["code"] == "ROUND_FAILED"
        await asyncio.wait_for(round_.task, timeout=5)
        assert "room1" not in _ACTIVE_ROUNDS

    @pytest.mark.asyncio
    async def test_room_payload_exposes_active_round(self, monkeypatch, tmp_path) -> None:
        from server.room_manager import RoomManager

        manager = RoomManager(tmp_path / "meetings")
        room = manager.create_room(
            participants=["a", "b"],
            chair="a",
            created_by="human",
            title="t",
        )

        gate = asyncio.Event()

        async def _gated(room_id, message, from_person, room_manager, supervisor):
            yield _format_sse("speaker_start", {"speaker": "a", "role": "chair"})
            await gate.wait()
            yield _format_sse("done", {"summary": "ok"})

        monkeypatch.setattr(room_routes, "_meeting_stream", _gated)
        round_ = _start_meeting_round(room.room_id, "msg", "human", None, None)
        for _ in range(50):
            if round_.current_speaker == "a":
                break
            await asyncio.sleep(0.01)

        payload = room_routes._room_payload(room)
        assert payload["active_round"] is not None
        assert payload["active_round"]["current_speaker"] == "a"

        gate.set()
        await asyncio.wait_for(round_.task, timeout=5)
        payload_after = room_routes._room_payload(room)
        assert payload_after["active_round"] is None
