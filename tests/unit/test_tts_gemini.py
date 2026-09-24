"""Unit tests for the Gemini TTS provider (no network)."""

from __future__ import annotations

import base64
import io
import json
import wave

import pytest

from core.config.schemas import VoiceConfig
from core.voice.tts_base import TTSConfig
from core.voice.tts_factory import create_tts_provider
from core.voice.tts_gemini import GeminiTTS, parse_sse_audio, pcm_to_wav


def _line(data: bytes, mime: str = "audio/l16") -> str:
    return "data: " + json.dumps({"index": 0, "delta": {"mime_type": mime, "data": base64.b64encode(data).decode()}})


def test_factory_returns_gemini() -> None:
    assert isinstance(create_tts_provider("gemini", VoiceConfig()), GeminiTTS)


def test_parse_sse_audio_l16_default_rate() -> None:
    assert parse_sse_audio(_line(b"\x01\x00\x02\x00")) == (b"\x01\x00\x02\x00", 24000)


def test_parse_sse_audio_rate_param_and_wav() -> None:
    assert parse_sse_audio(_line(b"\x00\x00", "audio/l16;rate=16000"))[1] == 16000
    pcm, rate = parse_sse_audio(_line(pcm_to_wav(b"\x05\x00" * 10, 22050), "audio/wav"))
    assert pcm == b"\x05\x00" * 10 and rate == 22050


@pytest.mark.parametrize("line", ["event: step.start", 'data: {"index":0,"step":{}}', "data: not-json", ""])
def test_parse_sse_audio_ignores_non_audio(line: str) -> None:
    assert parse_sse_audio(line) is None


def test_pcm_to_wav_roundtrip() -> None:
    with wave.open(io.BytesIO(pcm_to_wav(b"\x00\x01" * 24000)), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 24000, 24000)


def test_body_uses_voice_id_and_style() -> None:
    tts = GeminiTTS(VoiceConfig())
    body = tts._body("こんにちは", TTSConfig(provider="gemini", voice_id="voice_abc", extra={"style": "明るく"}))
    assert body["model"] == "gemini-3.8-flash-tts" and body["stream"] is True
    assert body["generation_config"]["speech_config"][0]["voice"] == "voice_abc"
    assert body["input"][0]["content"][0]["annotations"][0]["style"] == "明るく"
    assert "generation_config" not in tts._body("x", TTSConfig(provider="gemini"))
