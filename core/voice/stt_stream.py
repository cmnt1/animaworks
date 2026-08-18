# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Streaming STT — rolling buffer + LocalAgreement-2 prefix commitment.

Implements streaming transcription on top of the existing synchronous
faster-whisper :func:`VoiceSTT.transcribe_buffer`. The decoder stays fully
decoupled: this module only requires a plain callable
``decoder(bytes) -> dict`` whose shape matches ``VoiceSTT.transcribe_buffer``
(keys: ``raw_text``, ``language``, ``duration``, ``segments``). The
LocalAgreement logic is a pure function so this module imports cleanly even
when faster-whisper is not installed.

LocalAgreement-2: a character is only *committed* once it has appeared in
the common prefix of two consecutive decodes of the same (growing) audio
region. The committed text is strictly append-only and is never rewritten.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

PCM16_SAMPLE_RATE = 16_000
PCM16_BYTES_PER_SAMPLE = 2
DEFAULT_MAX_BUFFER_SECONDS = 30.0
DEFAULT_DECODE_MIN_SEC = 0.4
DEFAULT_MIN_AUDIO_SECONDS = 0.35

Decoder = Callable[[bytes], dict[str, Any]]


def common_prefix(left: str, right: str) -> str:
    """Return the longest common prefix of two strings (character-level).

    Japanese is not word-segmented here on purpose; agreement is detected on
    raw characters so it does not rely on a tokenizer.
    """
    count = 0
    for i in range(min(len(left), len(right))):
        if left[i] != right[i]:
            break
        count += 1
    return left[:count]


def local_agreement(previous: str, current: str, committed: str) -> str:
    """LocalAgreement-2 prefix commitment for a pair of consecutive decodes.

    Only the common prefix of ``previous`` and ``current`` that is also an
    extension of ``committed`` survives. The returned value is append-only
    with respect to ``committed`` — it can only grow, never shrink.

    Args:
        previous: Full text of the previous decoded region.
        current: Full text of the current decoded region.
        committed: Text already committed from earlier agreements.

    Returns:
        The new committed text (guaranteed to start with ``committed``; if
        the buffers disagreed before the committed boundary it is returned
        unchanged rather than rewritten).
    """
    if not committed:
        return common_prefix(previous, current)
    if current.startswith(committed) and previous.startswith(committed):
        return common_prefix(previous, current)
    return committed


def _committed_duration_sec(segments: list[dict[str, Any]], committed: str) -> float:
    """Approximate audio duration (seconds) covered by ``committed`` text.

    Walks the segment timestamps and returns the point where the committed
    text ends, scaling linearly inside the first segment that contains the
    boundary. Used to trim committed audio from the rolling buffer.
    """
    if not committed:
        return 0.0
    target = len(committed)
    acc = 0
    for seg in segments:
        seg_text = str(seg.get("text", "") or "")
        try:
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", 0.0))
        except (TypeError, ValueError):
            start = end = 0.0
        next_acc = acc + len(seg_text)
        if next_acc >= target:
            if next_acc == target:
                return end
            if not seg_text:
                return start
            frac = (target - acc) / len(seg_text)
            return start + (end - start) * frac
        acc = next_acc
    return 0.0


def _bytes_trimmed_for_prefix(
    segments: list[dict[str, Any]],
    prefix_text: str,
    *,
    bytes_per_sec: int,
) -> int:
    """PCM byte count matching ``prefix_text`` using committed duration."""
    if not prefix_text:
        return 0
    return int(_committed_duration_sec(segments, prefix_text) * bytes_per_sec)


class StreamingTranscriber:
    """Rolling-audio streaming transcriber with LocalAgreement-2 committing.

    The decoder is injected as a synchronous callable so this class can be
    unit-tested with fake decoders and imported without faster-whisper. All
    public methods are safe to call from a thread executor; internal state is
    guarded by a re-entrant lock.
    """

    def __init__(
        self,
        decoder: Decoder,
        *,
        sample_rate: int = PCM16_SAMPLE_RATE,
        max_buffer_seconds: float = DEFAULT_MAX_BUFFER_SECONDS,
        decode_min_sec: float = DEFAULT_DECODE_MIN_SEC,
        min_audio_seconds: float = DEFAULT_MIN_AUDIO_SECONDS,
    ) -> None:
        self._decoder = decoder
        self._bytes_per_sec = sample_rate * PCM16_BYTES_PER_SAMPLE
        self._max_bytes = int(max_buffer_seconds * self._bytes_per_sec)
        self._decode_min_bytes = int(decode_min_sec * self._bytes_per_sec)
        self._min_audio_bytes = int(min_audio_seconds * self._bytes_per_sec)
        self._buffer = bytearray()
        self._bytes_since_feed = 0
        self._committed = ""
        self._previous = ""
        self.last_language: str | None = None
        self._lock = threading.RLock()

    # ── buffer management ─────────────────────────────────────

    def feed(self, audio: bytes) -> bool:
        """Append PCM16 audio to the rolling buffer.

        Returns True once enough audio has accumulated since the last decode
        to warrant a re-decode (i.e. the transcriber is ``ready``).
        """
        if not audio:
            return False
        with self._lock:
            self._buffer.extend(audio)
            self._bytes_since_feed += len(audio)
            if len(self._buffer) > self._max_bytes:
                del self._buffer[: len(self._buffer) - self._max_bytes]
            return self.ready()

    def ready(self) -> bool:
        """Whether enough audio has accumulated to run a decode now."""
        with self._lock:
            return (
                self._bytes_since_feed >= self._decode_min_bytes
                and len(self._buffer) >= self._min_audio_bytes
            )

    def has_content(self) -> bool:
        """Whether any uncommitted audio remains buffered."""
        with self._lock:
            return bool(self._buffer)

    @property
    def committed(self) -> str:
        with self._lock:
            return self._committed

    # ── decode cycle ──────────────────────────────────────────

    def run_decode(self) -> str | None:
        """Run one decode step if due; return newly committed text (or None).

        ``None`` means nothing new was committed (or no decode was due).
        Suitable for running in a thread executor (no event-loop reliance).

        The (slow) decoder is invoked *outside* the lock so that a concurrent
        ``feed()`` from the event-loop thread is never blocked behind it.
        """
        with self._lock:
            if not self.ready():
                return None
            self._bytes_since_feed = 0
            snapshot = bytes(self._buffer)
            base_committed = self._committed
            base_previous = self._previous
        # Decoder runs without holding the lock: an event-loop thread calling
        # feed() can acquire the lock and keep flowing during decode.
        result = self._decoder(snapshot) or {}
        with self._lock:
            new_committed = self._merge_decode_result(
                result,
                base_committed=base_committed,
                base_previous=base_previous,
            )
            if new_committed == self._committed:
                return None
            self._committed = new_committed
            return new_committed

    def _merge_decode_result(
        self,
        result: dict[str, Any],
        *,
        base_committed: str,
        base_previous: str,
    ) -> str:
        """Merge a decode result into state; must be called with the lock held.

        Commits the agreed stable prefix, trims the corresponding audio from
        the front of the buffer, and updates the comparison reference. Trimming
        is from the front, so any audio appended by ``feed()`` while the
        decoder was running (at the tail) is preserved.
        """
        segments = result.get("segments") or []
        new_full = str(result.get("raw_text", "") or "").strip()
        lang = result.get("language")
        if lang:
            self.last_language = str(lang)
        # Reconstruct the aligned *full* transcript (committed prefix + tail)
        # so LocalAgreement stays meaningful even after committed audio has
        # been trimmed from the buffer.
        candidate_total = base_committed + new_full
        new_committed = local_agreement(base_previous, candidate_total, base_committed)
        added = new_committed[len(base_committed):]
        if added:
            trim = _bytes_trimmed_for_prefix(
                segments, added, bytes_per_sec=self._bytes_per_sec
            )
            if trim > 0 and trim <= len(self._buffer):
                del self._buffer[:trim]
        # Keep the reference aligned with the current full transcript.
        self._previous = candidate_total
        return new_committed

    def finalize(self) -> str:
        """Decode the remainder and return the complete final text.

        The final transcript is ``committed + tail``: prefixes already shown
        live via ``transcript_partial`` are appended to whatever remains in
        the buffer. The decoder runs outside the lock; state is then reset.
        """
        with self._lock:
            snapshot = bytes(self._buffer)
            committed = self._committed
        tail = ""
        lang = None
        if snapshot:
            result = self._decoder(snapshot) or {}
            tail = str(result.get("raw_text", "") or "").strip()
            lang = result.get("language")
        with self._lock:
            if lang:
                self.last_language = str(lang)
            self._buffer.clear()
            self._committed = ""
            self._previous = ""
            self._bytes_since_feed = 0
        return (committed + tail).strip()

    def reset(self) -> None:
        """Drop buffered audio and state (used on barge-in / interrupt)."""
        with self._lock:
            self._buffer.clear()
            self._bytes_since_feed = 0
            self._committed = ""
            self._previous = ""
