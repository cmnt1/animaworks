# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the streaming STT transcriber (LocalAgreement-2).

These tests use a fake decoder (scripted results) and never require a real
faster-whisper model, so they run in CI.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.voice.stt_stream import StreamingTranscriber, common_prefix, local_agreement


class _ScriptedDecoder:
    """Fake decoder that returns a scripted sequence of results."""

    def __init__(self, results: list[str]) -> None:
        self.results = list(results)
        self.calls = 0

    def __call__(self, audio: bytes) -> dict:
        self.calls += 1
        text = self.results.pop(0) if self.results else ""
        return {"raw_text": text, "language": "ja", "segments": [], "duration": 0.0}


def _make(fake, **kwargs):
    return StreamingTranscriber(
        fake,
        decode_min_sec=kwargs.get("decode_min_sec", 0.4),
    )


_CHUNK = b"\x00" * 20000  # enough to satisfy the feed interval (0.4s) + min audio


# ── common_prefix ──────────────────────────────────────────────


class TestCommonPrefix:
    def test_empty(self) -> None:
        assert common_prefix("", "") == ""
        assert common_prefix("", "こんにちは") == ""
        assert common_prefix("こんにちは", "") == ""

    def test_full_match(self) -> None:
        assert common_prefix("こんにちは", "こんにちは") == "こんにちは"

    def test_partial_match(self) -> None:
        assert common_prefix("こんにちは", "こんばんは") == "こん"

    def test_no_match(self) -> None:
        assert common_prefix("あ", "い") == ""


# ── local_agreement ───────────────────────────────────────────


class TestLocalAgreement:
    def test_one_observation_does_not_commit(self) -> None:
        # Only one decode seen so far (previous empty) → nothing confirmed.
        assert local_agreement("", "こんにちは", "") == ""

    def test_two_consecutive_matches_commit(self) -> None:
        # Same text twice → confirmed.
        assert local_agreement("こんにちは", "こんにちは", "") == "こんにちは"

    def test_flickering_tail_only_appends(self) -> None:
        # "調べて" then "調べておいて" — tail is unstable, only stable prefix
        # "調べて" is committed, and it is never rewritten.
        assert local_agreement("調べて", "調べておいて", "") == "調べて"
        assert local_agreement("調べておいて", "調べて", "調べて") == "調べて"

    def test_never_rewrites_committed(self) -> None:
        committed = "こんにちは"
        # Agreement extending the committed prefix is allowed.
        assert (
            local_agreement("こんにちは世界", "こんにちは世界です", committed)
            == "こんにちは世界"
        )
        # Disagreement before the committed boundary → keep committed unchanged.
        assert local_agreement("こんにちはX", "こんにちはY", committed) == "こんにちは"


# ── StreamingTranscriber ──────────────────────────────────────


class TestStreamingTranscriber:
    def test_feed_reports_when_decode_due(self) -> None:
        tr = _make(_ScriptedDecoder([]))
        assert tr.feed(_CHUNK) is True

    def test_one_decode_does_not_commit(self) -> None:
        tr = _make(_ScriptedDecoder(["こんにちは"]))
        tr.feed(_CHUNK)
        assert tr.run_decode() is None
        assert tr.committed == ""

    def test_two_consecutive_decodes_commit(self) -> None:
        tr = _make(_ScriptedDecoder(["こんにちは", "こんにちは"]))
        tr.feed(_CHUNK)
        assert tr.run_decode() is None  # 1回のみでは未確定
        tr.feed(_CHUNK)
        assert tr.run_decode() == "こんにちは"  # 2回一致で確定
        assert tr.committed == "こんにちは"

    def test_flicker_only_appends(self) -> None:
        tr = _make(_ScriptedDecoder(["調べて", "調べておいて", "調べておいて"]))
        tr.feed(_CHUNK)
        assert tr.run_decode() is None
        tr.feed(_CHUNK)
        assert tr.run_decode() == "調べて"
        tr.feed(_CHUNK)
        assert tr.run_decode() is None  # unstable tail → no rewrite
        assert tr.committed == "調べて"

    def test_finalize_matches_last_confirmed_decode(self) -> None:
        # First two decodes confirm "こんにちは"; finalize decodes the
        # (already committed) tail and must yield consistent final text.
        dec = _ScriptedDecoder(["こんにちは", "こんにちは", ""])
        tr = _make(dec)
        tr.feed(_CHUNK)
        tr.run_decode()
        tr.feed(_CHUNK)
        tr.run_decode()
        assert tr.committed == "こんにちは"
        final = tr.finalize()
        assert final == "こんにちは"
        # finalize resets state for the next utterance.
        assert tr.committed == ""
        assert not tr.has_content()

    def test_reset_clears_state(self) -> None:
        tr = _make(_ScriptedDecoder(["こんにちは", "こんにちは"]))
        tr.feed(_CHUNK)
        tr.run_decode()
        tr.feed(_CHUNK)
        tr.run_decode()
        assert tr.committed == "こんにちは"
        assert tr.has_content()
        tr.reset()
        assert tr.committed == ""
        assert not tr.has_content()

    def test_feed_not_blocked_during_decode(self) -> None:
        """A slow decode must not freeze feed() (runs on the event-loop thread).

        The decoder is called outside the lock, so a concurrent feed() should
        return almost immediately even while a decode is still in flight.
        """
        started = threading.Event()
        release = threading.Event()

        def slow_decoder(audio: bytes) -> dict:
            started.set()
            release.wait(2.0)  # simulate a slow decode
            return {"raw_text": "こんにちは", "language": "ja", "segments": [], "duration": 0.0}

        tr = StreamingTranscriber(slow_decoder, decode_min_sec=0.2, min_audio_seconds=0.1)
        tr.feed(b"\x00" * 20000)  # make a decode due
        decode_result: list = []

        def run_decode_thread() -> None:
            decode_result.append(tr.run_decode())

        thread = threading.Thread(target=run_decode_thread)
        thread.start()
        assert started.wait(1.0)  # decoder entered its sleep → lock is released
        t0 = time.monotonic()
        tr.feed(b"\x00" * 100)  # feed while the decoder is still running
        elapsed = time.monotonic() - t0
        release.set()
        thread.join(timeout=1.0)
        assert elapsed < 0.5, f"feed() blocked behind decoder: {elapsed:.3f}s"
        assert not thread.is_alive()

    def test_importable_without_faster_whisper(self) -> None:
        # Import succeeds (pure local-agreement separated from decoder) even
        # when faster_whisper is not installed.
        import core.voice.stt_stream as mod

        assert hasattr(mod, "StreamingTranscriber")
        assert hasattr(mod, "local_agreement")


# ── VoiceSession wiring ────────────────────────────────────────


class TestVoiceSessionStreaming:
    @pytest.mark.asyncio
    async def test_audio_chunk_feeds_transcriber(self) -> None:
        """handle_audio_chunk routes audio into the streaming transcriber."""
        from core.voice.session import VoiceSession
        from core.voice.tts_base import TTSConfig

        ws = AsyncMock()
        stt = MagicMock()
        tts = AsyncMock()
        supervisor = MagicMock()
        voice_config = MagicMock(stt_refine_enabled=False)
        session = VoiceSession(
            "test", ws, stt, tts, TTSConfig(provider="voicevox"), supervisor, voice_config
        )
        # Small feed (< decode-min) so no async streaming task starts here;
        # we only assert the audio reached the transcriber.
        await session.handle_audio_chunk(b"\x00" * 100)
        assert session._streamer.has_content() is True
        assert session._streamer.committed == ""
