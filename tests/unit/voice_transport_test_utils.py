from __future__ import annotations

from typing import Any


class MockVoiceTransport:
    """Bridge voice-session protocol calls to a mock WebSocket for assertions."""

    def __init__(self, websocket: Any) -> None:
        self.websocket = websocket

    async def send_event(self, event: dict[str, Any]) -> None:
        await self.websocket.send_json(event)

    async def send_audio(self, data: bytes) -> None:
        await self.websocket.send_bytes(data)
