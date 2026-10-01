from __future__ import annotations

import pytest

from server.routes.voice import FastAPIWebSocketVoiceTransport


class _RecordingWebSocket:
    def __init__(self) -> None:
        self.frames: list[tuple[str, object]] = []

    async def send_json(self, event: dict[str, object]) -> None:
        self.frames.append(("event", event))

    async def send_bytes(self, data: bytes) -> None:
        self.frames.append(("audio", data))


@pytest.mark.asyncio
async def test_fastapi_adapter_preserves_event_and_audio_frame_order() -> None:
    websocket = _RecordingWebSocket()
    transport = FastAPIWebSocketVoiceTransport(websocket)  # type: ignore[arg-type]

    await transport.send_event({"type": "tts_start", "text": "hello"})
    await transport.send_audio(b"\x00\x01")
    await transport.send_event({"type": "tts_done"})

    assert websocket.frames == [
        ("event", {"type": "tts_start", "text": "hello"}),
        ("audio", b"\x00\x01"),
        ("event", {"type": "tts_done"}),
    ]
