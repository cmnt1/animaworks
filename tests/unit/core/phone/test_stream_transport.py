from __future__ import annotations

import asyncio
import base64
import io
import wave

import numpy as np

from core.phone.stream_transport import TwilioMediaStreamTransport
from core.voice.turn_detector import TurnDetector


def _wav(duration_ms: int = 40, sample_rate: int = 24_000) -> bytes:
    sample_count = sample_rate * duration_ms // 1000
    pcm = np.full(sample_count, 1_000, dtype="<i2").tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()


class _RecordingWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)


class _BlockingFirstMediaWebSocket(_RecordingWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)
        if message.get("event") == "media" and not self.started.is_set():
            self.started.set()
            await self.release.wait()


def test_send_audio_emits_base64_media_frames_then_mark() -> None:
    websocket = _RecordingWebSocket()
    detector = TurnDetector(lambda _frame: 0.0)
    transport = TwilioMediaStreamTransport(websocket, detector, "MZ-1")

    asyncio.run(transport.send_audio(_wav(45)))

    events = [message["event"] for message in websocket.messages]
    assert events == ["media", "media", "media", "mark"]
    assert all(message["streamSid"] == "MZ-1" for message in websocket.messages)
    assert all(len(base64.b64decode(message["media"]["payload"])) == 160 for message in websocket.messages[:3])
    assert websocket.messages[-1]["mark"]["name"] in transport.pending_marks


def test_playback_stays_active_until_all_segment_marks_are_acknowledged() -> None:
    websocket = _RecordingWebSocket()
    detector = TurnDetector(lambda _frame: 0.0)
    transport = TwilioMediaStreamTransport(websocket, detector, "MZ-2")

    asyncio.run(transport.send_audio(_wav(40)))
    mark = websocket.messages[-1]["mark"]["name"]

    assert detector.is_playback_active is True
    transport.handle_mark("unknown")
    assert detector.is_playback_active is True
    transport.handle_mark(mark)
    assert detector.is_playback_active is False
    assert detector.playback_ended_at is not None


def test_barge_interrupt_sends_clear_and_drops_unsent_frames() -> None:
    async def scenario() -> tuple[_BlockingFirstMediaWebSocket, TurnDetector]:
        websocket = _BlockingFirstMediaWebSocket()
        detector = TurnDetector(lambda _frame: 0.0)
        transport = TwilioMediaStreamTransport(websocket, detector, "MZ-3")
        sender = asyncio.create_task(transport.send_audio(_wav(200)))
        await websocket.started.wait()
        clear = asyncio.create_task(transport.send_event({"type": "barge_verdict", "interrupt": True}))
        await asyncio.sleep(0)
        websocket.release.set()
        await asyncio.gather(sender, clear)
        return websocket, detector

    websocket, detector = asyncio.run(scenario())

    assert [message["event"] for message in websocket.messages] == ["media", "clear"]
    assert detector.is_playback_active is False


def test_rejected_barge_probe_keeps_active_playback_until_mark() -> None:
    websocket = _RecordingWebSocket()
    detector = TurnDetector(lambda _frame: 0.0)
    transport = TwilioMediaStreamTransport(websocket, detector, "MZ-4")

    async def scenario() -> None:
        await transport.send_audio(_wav(20))
        await transport.send_event({"type": "barge_verdict", "interrupt": False})

    asyncio.run(scenario())
    mark = websocket.messages[-1]["mark"]["name"]

    assert detector.is_playback_active is True
    transport.handle_mark(mark)
    assert detector.is_playback_active is False


def test_close_clears_pending_playback_state() -> None:
    websocket = _RecordingWebSocket()
    detector = TurnDetector(lambda _frame: 0.0)
    transport = TwilioMediaStreamTransport(websocket, detector, "MZ-5")

    async def scenario() -> None:
        await transport.send_audio(_wav())
        await transport.close()

    asyncio.run(scenario())

    assert detector.is_playback_active is False
    assert transport.pending_marks == frozenset()
