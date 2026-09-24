# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Gemini TTS provider — Gemini API Interactions endpoint (SSE streaming).

Supports prebuilt voices (e.g. ``Leda``) and Voice design personas
(``voice_...`` IDs created via ``POST /v1beta/voices``). Audio arrives as raw
L16 PCM deltas; they are re-packed into ~``chunk_seconds`` WAV segments so the
browser playback queue (which decodes each binary frame independently) can
start speaking before the whole sentence is synthesized.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import wave
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.voice.tts_base import BaseTTSProvider, TTSConfig, TTSSynthesisError

logger = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.8-flash-tts"
DEFAULT_SAMPLE_RATE = 24000
HTTP_TIMEOUT = 60.0

_RATE_RE = re.compile(r"rate=(\d+)")


def _cfg(voice_config: Any, key: str, default: Any) -> Any:
    gem = getattr(voice_config, "gemini", None) or {}
    val = gem.get(key) if isinstance(gem, dict) else getattr(gem, key, None)
    return default if val in (None, "") else val


def pcm_to_wav(pcm: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes:
    """Wrap mono 16-bit little-endian PCM in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def parse_sse_audio(line: str) -> tuple[bytes, int] | None:
    """Extract (pcm, sample_rate) from one SSE ``data:`` line, if it carries audio."""
    if not line.startswith("data:"):
        return None
    try:
        payload = json.loads(line[5:].strip())
    except json.JSONDecodeError:
        return None
    delta = payload.get("delta") if isinstance(payload, dict) else None
    if not isinstance(delta, dict):
        return None
    mime = str(delta.get("mime_type") or "")
    data = delta.get("data")
    if not data or not mime.startswith("audio/"):
        return None
    raw = base64.b64decode(data)
    if mime.startswith("audio/wav") or raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw), "rb") as w:
            return w.readframes(w.getnframes()), w.getframerate()
    m = _RATE_RE.search(mime)
    return raw, int(m.group(1)) if m else DEFAULT_SAMPLE_RATE


# ── GeminiTTS ──────────────────────────────────────────────────


class GeminiTTS(BaseTTSProvider):
    """Gemini API TTS provider (streaming via Interactions API)."""

    def __init__(self, voice_config: Any) -> None:
        self._model = _cfg(voice_config, "model", DEFAULT_MODEL)
        self._api_key_env = _cfg(voice_config, "api_key_env", "GEMINI_API_KEY")
        self._vault_key = _cfg(voice_config, "vault_key", "GEMINI_API_KEY")
        self._chunk_seconds = float(_cfg(voice_config, "chunk_seconds", 1.0))

    def _get_api_key(self) -> str | None:
        key = os.environ.get(self._api_key_env)
        if key:
            return key
        try:
            from core.config.vault import get_vault_manager

            return get_vault_manager().get("shared", self._vault_key)
        except Exception:
            return None

    def _body(self, text: str, config: TTSConfig) -> dict[str, Any]:
        content: dict[str, Any] = {"type": "text", "text": text}
        style = (config.extra or {}).get("style") if isinstance(config.extra, dict) else None
        if style:
            content["annotations"] = [{"type": "speech_metadata", "speaker": "speaker", "style": str(style)}]
        body: dict[str, Any] = {
            "model": (config.extra or {}).get("model", self._model) if isinstance(config.extra, dict) else self._model,
            "stream": True,
            "input": [{"type": "user_input", "content": [content]}],
            "response_format": {"type": "audio"},
        }
        voice = (config.voice_id or "").strip()
        if voice:
            body["generation_config"] = {"speech_config": [{"voice": voice}]}
        return body

    async def synthesize(self, text: str, config: TTSConfig) -> AsyncIterator[bytes]:
        """Stream ~chunk_seconds WAV segments as audio deltas arrive."""
        api_key = self._get_api_key()
        if not api_key:
            raise TTSSynthesisError(f"Gemini TTS: API key not configured (env/vault: {self._api_key_env})")
        headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
        buf = bytearray()
        rate = DEFAULT_SAMPLE_RATE
        sent = False
        try:
            async with (
                httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client,
                client.stream(
                    "POST", f"{API_BASE}/interactions?alt=sse", headers=headers, json=self._body(text, config)
                ) as r,
            ):
                if r.status_code >= 400:
                    detail = (await r.aread())[:300]
                    raise TTSSynthesisError(f"Gemini TTS HTTP {r.status_code}: {detail!r}")
                async for line in r.aiter_lines():
                    got = parse_sse_audio(line)
                    if got is None:
                        continue
                    pcm, rate = got
                    buf.extend(pcm)
                    if len(buf) >= int(rate * 2 * self._chunk_seconds):
                        yield pcm_to_wav(bytes(buf), rate)
                        buf.clear()
                        sent = True
        except httpx.HTTPError as e:
            logger.warning("Gemini TTS synthesis failed: %s", e)
            raise TTSSynthesisError(f"Gemini TTS synthesis failed: {e}") from e
        if buf:
            yield pcm_to_wav(bytes(buf), rate)
            sent = True
        if not sent:
            raise TTSSynthesisError("Gemini TTS: empty audio response")

    async def synthesize_full(self, text: str, config: TTSConfig) -> bytes:
        """Generate one complete WAV for given text."""
        pcm = bytearray()
        rate = DEFAULT_SAMPLE_RATE
        async for seg in self.synthesize(text, config):
            with wave.open(io.BytesIO(seg), "rb") as w:
                rate = w.getframerate()
                pcm.extend(w.readframes(w.getnframes()))
        return pcm_to_wav(bytes(pcm), rate)

    async def list_voices(self) -> list[dict]:
        """List Voice design personas stored in the project."""
        api_key = self._get_api_key()
        if not api_key:
            return []
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                r = await client.get(f"{API_BASE}/voices", headers={"x-goog-api-key": api_key})
                r.raise_for_status()
                voices = r.json().get("voices", [])
                return [{"id": v.get("id", ""), "name": v.get("display_name", v.get("id", ""))} for v in voices]
            except Exception:
                return []

    async def health_check(self) -> bool:
        """Healthy when an API key is available (no network probe — avoids cost)."""
        return bool(self._get_api_key())
