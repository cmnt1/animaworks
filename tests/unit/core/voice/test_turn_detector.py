from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import importlib.util
from unittest.mock import AsyncMock

import pytest

from core.voice.turn_detector import (
    BARGE_MIN_MS,
    ECHO_TAIL_MS,
    FRAME_BYTES,
    REDEMPTION_MS,
    TurnDetector,
    TurnDetectorEvent,
    drive_session,
)


def _frame(value: int) -> bytes:
    return bytes([value]) * FRAME_BYTES


def _pcm(values: list[int]) -> bytes:
    return b"".join(_frame(value) for value in values)


def _detector(probabilities: list[float], *, clock=None) -> TurnDetector:
    remaining = iter(probabilities)
    return TurnDetector(lambda _frame: next(remaining, 0.0), clock=clock or (lambda: 0.0))


def _event_types(events: list[TurnDetectorEvent]) -> list[str]:
    return [event.type for event in events]


def test_normal_speech_emits_start_audio_and_end() -> None:
    detector = _detector([0.0] * 3 + [0.9] * 13 + [0.0] * 44)

    events = detector.feed(_pcm([1] * 60))

    assert _event_types(events) == ["speech_start", "audio", "speech_end"]
    assert events[1].audio == _pcm([1] * 60)


def test_speech_shorter_than_minimum_emits_misfire_for_discard() -> None:
    detector = _detector([0.9] * 2 + [0.0] * 44)

    events = detector.feed(_pcm([1] * 46))

    assert _event_types(events) == ["speech_start", "audio", "misfire"]


def test_custom_redemption_ms_keeps_phone_turn_open_longer() -> None:
    probabilities = iter([0.9] * 13 + [0.0] * 100)
    detector = TurnDetector(lambda _frame: next(probabilities, 0.0), redemption_ms=2000)

    after_1400ms = detector.feed(_pcm([1] * 13 + [0] * 44))
    assert "speech_end" not in _event_types(after_1400ms)

    after_2000ms = detector.feed(_pcm([0] * 19))
    assert "speech_end" in _event_types(after_2000ms)
    assert detector._redemption_ms == 2000
    assert REDEMPTION_MS == 1400
    assert TurnDetector()._redemption_ms == 1400


def test_silence_does_not_emit_turn_events() -> None:
    detector = _detector([0.1] * 100)

    assert detector.feed(_pcm([0] * 100)) == []


def test_playback_probe_waits_for_600ms_of_high_confidence_audio() -> None:
    detector = _detector([0.8] * 18 + [0.8])
    detector.set_playback_active(True)

    before_threshold = detector.feed(_pcm([1] * 18))
    assert "barge_probe" not in _event_types(before_threshold)
    assert not any(event.type == "audio" for event in before_threshold)

    at_threshold = detector.feed(_pcm([1]))
    assert _event_types(at_threshold) == ["barge_probe", "audio"]
    assert at_threshold[-1].audio == _pcm([1] * 19)
    assert BARGE_MIN_MS == 600


def test_playback_confidence_below_point_75_does_not_probe() -> None:
    detector = _detector([0.7] * 25 + [0.0] * 44)
    detector.set_playback_active(True)

    events = detector.feed(_pcm([1] * 69))

    assert "barge_probe" not in _event_types(events)
    assert not any(event.type == "audio" for event in events)


def test_playback_high_confidence_accumulates_like_browser_probe() -> None:
    probabilities = [value for _ in range(19) for value in (0.8, 0.6)]
    detector = _detector(probabilities)
    detector.set_playback_active(True)

    events = detector.feed(_pcm([1] * len(probabilities)))

    assert "barge_probe" in _event_types(events)
    assert events[-1].type == "audio"


def test_echo_tail_suppresses_frames_until_1200ms_has_elapsed() -> None:
    now = [5.0]
    calls = 0

    def probability(_frame: bytes) -> float:
        nonlocal calls
        calls += 1
        return 0.9

    detector = TurnDetector(probability, clock=lambda: now[0])
    detector.set_playback_active(True)
    detector.set_playback_active(False)
    assert detector.playback_ended_at == 5.0

    now[0] += (ECHO_TAIL_MS - 1) / 1000
    assert detector.feed(_frame(1)) == []
    assert calls == 0

    now[0] += 0.01
    events = detector.feed(_frame(2))
    assert _event_types(events) == ["speech_start", "audio"]
    assert calls == 1


def test_speech_audio_includes_pre_speech_pad() -> None:
    frames = [_frame(value) for value in range(1, 7)]
    probabilities = [0.1] * 5 + [0.9]
    detector = _detector(probabilities)

    events = detector.feed(b"".join(frames))

    assert _event_types(events) == ["speech_start", "audio"]
    assert events[-1].audio == b"".join(frames)


def test_feed_buffers_incomplete_pcm_frames() -> None:
    detector = _detector([0.9])
    frame = _frame(7)

    assert detector.feed(frame[:300]) == []
    events = detector.feed(frame[300:])

    assert _event_types(events) == ["speech_start", "audio"]
    assert events[-1].audio == frame


def test_short_playback_candidate_is_dropped_when_playback_ends() -> None:
    now = [10.0]
    detector = _detector([0.9] * 3 + [0.9], clock=lambda: now[0])
    detector.set_playback_active(True)

    started = detector.feed(_pcm([1] * 3))
    assert _event_types(started) == ["speech_start"]
    detector.set_playback_active(False)
    now[0] += 0.5
    assert detector.feed(_frame(2)) == []

    now[0] += 0.8
    assert _event_types(detector.feed(_frame(3))) == ["speech_start", "audio"]


def test_false_barge_verdict_clears_probe_and_keeps_playback_gated() -> None:
    detector = _detector([0.9] * 38)
    detector.set_playback_active(True)
    assert "barge_probe" in _event_types(detector.feed(_pcm([1] * 19)))

    detector.resolve_barge_verdict(False)

    assert detector.is_playback_active is True
    assert detector.playback_ended_at is None
    assert detector.feed(_pcm([2] * 19)).count(TurnDetectorEvent("barge_probe")) == 1


def test_true_barge_verdict_opens_playback_gate_and_preserves_user_segment() -> None:
    now = [20.0]
    detector = _detector([0.9] * 20, clock=lambda: now[0])
    detector.set_playback_active(True)
    detector.feed(_pcm([1] * 19))

    detector.resolve_barge_verdict(True)
    continued = detector.feed(_frame(2))

    assert detector.is_playback_active is False
    assert detector.playback_ended_at == 20.0
    assert _event_types(continued) == ["audio"]
    assert continued[0].audio == _frame(2)


def test_detector_reset_clears_partial_frame_and_playback_state() -> None:
    calls = 0

    def probability(_frame: bytes) -> float:
        nonlocal calls
        calls += 1
        return 0.1

    detector = TurnDetector(probability)
    detector.set_playback_active(True)
    assert detector.feed(_frame(1)[:100]) == []
    assert calls == 0

    detector.reset()

    assert detector.is_playback_active is False
    assert detector.playback_ended_at is None
    assert detector.feed(_frame(2)) == []
    assert calls == 1


@pytest.mark.asyncio
async def test_drive_session_routes_detector_events_to_existing_handlers() -> None:
    session = type(
        "SessionStub",
        (),
        {
            "handle_audio_chunk": AsyncMock(),
            "handle_speech_end": AsyncMock(),
            "handle_barge_probe": AsyncMock(),
            "handle_discard_audio": AsyncMock(),
        },
    )()
    events = [
        TurnDetectorEvent("speech_start"),
        TurnDetectorEvent("barge_probe"),
        TurnDetectorEvent("audio", b"audio"),
        TurnDetectorEvent("speech_end"),
        TurnDetectorEvent("misfire"),
    ]

    await drive_session(events, session)

    session.handle_barge_probe.assert_awaited_once_with()
    session.handle_audio_chunk.assert_awaited_once_with(b"audio")
    session.handle_speech_end.assert_awaited_once_with()
    session.handle_discard_audio.assert_awaited_once_with()


def test_real_faster_whisper_vad_model_can_be_loaded_when_installed() -> None:
    if importlib.util.find_spec("faster_whisper") is None:
        pytest.skip("faster-whisper is an optional transcribe extra")

    detector = TurnDetector()
    detector._load_vad_model()

    assert detector._vad_model is not None


@pytest.mark.parametrize("provider_probability", [0.35, 0.5, 0.75])
def test_probability_threshold_boundaries_are_accepted(provider_probability: float) -> None:
    detector = _detector([provider_probability])

    events = detector.feed(_frame(1))

    if provider_probability >= 0.5:
        assert "speech_start" in _event_types(events)
    else:
        assert events == []
