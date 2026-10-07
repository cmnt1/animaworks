from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Twilio bidirectional Media Streams adapter for the shared voice session."""

import asyncio
import base64
import itertools
import logging
from typing import Any

from core.voice.audio_codec import wav_to_mulaw_frames
from core.voice.turn_detector import TurnDetector

logger = logging.getLogger(__name__)


class TwilioMediaStreamTransport:
    """Adapt VoiceSession output to Twilio μ-law media, marks, and clear events."""

    def __init__(self, websocket: Any, detector: TurnDetector, stream_sid: str) -> None:
        self._websocket = websocket
        self._detector = detector
        self._stream_sid = stream_sid
        self._send_lock = asyncio.Lock()
        self._pending_marks: set[str] = set()
        self._mark_counter = itertools.count(1)
        self._generation = 0
        self._closed = False

    @property
    def pending_marks(self) -> frozenset[str]:
        """Names of outbound audio marks not yet acknowledged by Twilio."""
        return frozenset(self._pending_marks)

    async def send_event(self, event: dict[str, Any]) -> None:
        """Handle transport-relevant session events; captions are phone-irrelevant."""
        if event.get("type") != "barge_verdict":
            return

        if bool(event.get("interrupt")):
            # Advance before waiting for the send lock so an in-flight segment
            # stops queuing frames as soon as the clear is requested.
            self._generation += 1
            self._pending_marks.clear()
            self._detector.resolve_barge_verdict(True)
            if self._closed:
                return
            async with self._send_lock:
                if not self._closed:
                    await self._websocket.send_json({"event": "clear", "streamSid": self._stream_sid})
            return

        self._detector.resolve_barge_verdict(False)
        if not self._pending_marks:
            # A rejected probe may resolve after the last mark was played.
            self._detector.set_playback_active(False)

    async def send_audio(self, data: bytes) -> None:
        """Convert a WAV segment to 20 ms μ-law frames and mark its playback end."""
        if self._closed:
            return
        frames = wav_to_mulaw_frames(data)
        if not frames:
            return

        generation = self._generation
        mark_name = f"voice-{next(self._mark_counter)}"
        self._pending_marks.add(mark_name)
        self._detector.set_playback_active(True)
        try:
            for frame in frames:
                async with self._send_lock:
                    if self._closed or generation != self._generation:
                        return
                    await self._websocket.send_json(
                        {
                            "event": "media",
                            "streamSid": self._stream_sid,
                            "media": {"payload": base64.b64encode(frame).decode("ascii")},
                        }
                    )

            async with self._send_lock:
                if self._closed or generation != self._generation:
                    return
                await self._websocket.send_json(
                    {
                        "event": "mark",
                        "streamSid": self._stream_sid,
                        "mark": {"name": mark_name},
                    }
                )
        except Exception:
            self._pending_marks.discard(mark_name)
            if not self._pending_marks:
                self._detector.set_playback_active(False)
            logger.debug("Twilio Media Streams audio send failed", exc_info=True)
            raise

    def handle_mark(self, name: str) -> None:
        """Record a Twilio playback acknowledgement and update echo gating."""
        if not name or name not in self._pending_marks:
            return
        self._pending_marks.remove(name)
        if not self._pending_marks:
            self._detector.set_playback_active(False)

    async def close(self) -> None:
        """Stop any in-flight audio sender and reset detector playback state."""
        self._closed = True
        self._generation += 1
        self._pending_marks.clear()
        self._detector.reset()


__all__ = ["TwilioMediaStreamTransport"]
