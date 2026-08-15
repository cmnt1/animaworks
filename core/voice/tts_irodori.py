# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Irodori-TTS provider — HTTP API."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.voice.tts_base import BaseTTSProvider, TTSConfig, TTSSynthesisError

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://xserverng2:7861"
HTTP_TIMEOUT = 60.0


# ── IrodoriTTS ───────────────────────────────────────────────────


class IrodoriTTS(BaseTTSProvider):
    """Irodori-TTS HTTP API provider."""

    def __init__(self, voice_config: Any) -> None:
        """Initialize with voice config.

        Args:
            voice_config: Config with irodori.base_url.
        """
        irodori = getattr(voice_config, "irodori", None) or {}
        base = irodori.get("base_url") if isinstance(irodori, dict) else getattr(irodori, "base_url", None)
        self._base_url = (base or DEFAULT_BASE_URL).rstrip("/")

    async def synthesize(self, text: str, config: TTSConfig) -> AsyncIterator[bytes]:
        """Stream TTS audio chunks. Irodori returns full WAV; yield as single chunk."""
        audio = await self.synthesize_full(text, config)
        yield audio

    async def synthesize_full(self, text: str, config: TTSConfig) -> bytes:
        """Generate complete WAV audio for given text."""
        voice_id = (config.voice_id or "").strip() or None
        speed: float | None = config.speed if config.speed else None
        payload: dict[str, Any] = {
            "text": text,
            "voice_id": voice_id,
            "speed": speed,
        }

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            try:
                r = await client.post(
                    f"{self._base_url}/voice",
                    json=payload,
                )
                r.raise_for_status()
                if not r.content:
                    raise TTSSynthesisError("Irodori-TTS: empty audio response")
                return r.content
            except httpx.HTTPError as e:
                logger.warning("Irodori-TTS synthesis failed: %s", e)
                raise TTSSynthesisError(f"Irodori-TTS synthesis failed: {e}") from e

    async def list_voices(self) -> list[dict]:
        """List available voices. Irodori may not expose a list endpoint."""
        return [{"id": "default", "name": "default"}]

    async def health_check(self) -> bool:
        """Check if Irodori-TTS API is available via GET /health."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                r = await client.get(f"{self._base_url}/health")
                return r.status_code == 200
            except Exception:
                return False
