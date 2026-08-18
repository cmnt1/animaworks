# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Streaming STT — rolling buffer + LocalAgreement-2 prefix commitment.

Implements streaming transcription on top of the existing synchronous
faster-whisper :func:`VoiceSTT.transcribe_buffer`. The decoder stays fully
decoupled: this module only requires a plain callable
``decoder(bytes, initial_prompt) -> dict`` whose shape matches
``VoiceSTT.transcribe_buffer`` (keys: ``raw_text``, ``language``,
``duration``, ``segments``). The LocalAgreement logic is a pure function so
this module imports cleanly even when faster-whisper is not installed.

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
# Context fed to faster-whisper as ``initial_prompt`` when re-decoding after a
# trim, so the model knows what was transcribed before the current buffer.
MAX_INITIAL_PROMPT_CHARS = 200
# Max chars of suffix-prefix overlap to collapse between committed text and a
# freshly decoded tail (removes "確定確定" style re-recognition doubles).
MAX_SUFFIX_PREFIX_OVERLAP = 200

Decoder = Callable[[bytes, str], dict[str, Any]]


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


def _bytes_trimmed_for_prefix(
    segments: list[dict[str, Any]],
    prefix_text: str,
    *,
    bytes_per_sec: int,
) -> int:
    """PCM byte count of audio fully covered by ``prefix_text``.

    Trims only up to the end of the last segment that is *fully contained*
    in ``prefix_text``. A segment only partially covered (the committed
    boundary falls mid-word) is NOT trimmed, so the next decode starts at a
    real word boundary instead of a cut-off fragment. Mid-word cuts caused
    e.g. '文字起こし' → 'お腹おこし' in the real-audio E2E.
    """
    if not prefix_text:
        return 0
    acc = 0
    end = 0.0
    for seg in segments:
        seg_text = str(seg.get("text", "") or "")
        next_acc = acc + len(seg_text)
        if next_acc > len(prefix_text):
            break  # this segment is only partially covered → stop before it
        try:
            seg_end = float(seg.get("end", 0.0))
        except (TypeError, ValueError):
            seg_end = 0.0
        end = seg_end
        acc = next_acc
    raw = int(end * bytes_per_sec)
    # Align to the PCM16 sample boundary; an odd trim would leave the buffer
    # misaligned and break np.frombuffer(dtype=int16) on the next decode.
    return raw - (raw % PCM16_BYTES_PER_SAMPLE)


def _remove_suffix_prefix_overlap(
    left: str,
    right: str,
    max_overlap: int = MAX_SUFFIX_PREFIX_OVERLAP,
) -> str:
    """Return ``left + right`` with the longest suffix-prefix overlap removed.

    After a segment-boundary trim the next decode can begin by repeating the
    tail of the committed text (re-recognition of already committed audio).
    Collapsing that overlap ensures ``committed + new_tail`` does not contain
    doubles (e.g. '確定確定').
    """
    limit = min(len(left), len(right), max_overlap)
    for k in range(limit, 0, -1):
        if left[-k:] == right[:k]:
            return left + right[k:]
    return left + right


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
            return self._bytes_since_feed >= self._decode_min_bytes and len(self._buffer) >= self._min_audio_bytes

    def has_content(self) -> bool:
        """Whether any uncommitted audio remains buffered."""
        with self._lock:
            return bool(self._buffer)

    @property
    def committed(self) -> str:
        with self._lock:
            return self._committed

    @staticmethod
    def _initial_prompt(committed: str) -> str:
        """Committed tail used as decoder context after a trim."""
        return committed[-MAX_INITIAL_PROMPT_CHARS:] if committed else ""

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
        # feed() can acquire the lock and keep flowing during decode. The
        # committed tail is passed as context for the post-trim re-decode.
        initial_prompt = self._initial_prompt(base_committed)
        result = self._decoder(snapshot, initial_prompt) or {}
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
        is from the front at segment boundaries, so any audio appended by
        ``feed()`` while the decoder was running (at the tail) is preserved.
        """
        segments = result.get("segments") or []
        new_full = str(result.get("raw_text", "") or "").strip()
        lang = result.get("language")
        if lang:
            self.last_language = str(lang)
        # Reconstruct the aligned *full* transcript (committed prefix + tail).
        # Collapse any suffix-prefix overlap so the committed boundary is not
        # reproduced twice on re-decode.
        candidate_total = _remove_suffix_prefix_overlap(base_committed, new_full)
        new_committed = local_agreement(base_previous, candidate_total, base_committed)
        added = new_committed[len(base_committed) :]
        if added:
            trim = _bytes_trimmed_for_prefix(segments, added, bytes_per_sec=self._bytes_per_sec)
            if trim > 0 and trim <= len(self._buffer):
                del self._buffer[:trim]
        # Keep the reference aligned with the current full transcript.
        self._previous = candidate_total
        return new_committed

    def finalize(self) -> str:
        """Decode the remainder and return the complete final text.

        The final transcript is ``committed + tail``: prefixes already shown
        live via ``transcript_partial`` are appended to whatever remains in
        the buffer (with any boundary overlap removed). The decoder runs
        outside the lock; state is then reset.
        """
        with self._lock:
            snapshot = bytes(self._buffer)
            committed = self._committed
        tail = ""
        lang = None
        if snapshot:
            initial_prompt = self._initial_prompt(committed)
            result = self._decoder(snapshot, initial_prompt) or {}
            tail = str(result.get("raw_text", "") or "").strip()
            lang = result.get("language")
        with self._lock:
            if lang:
                self.last_language = str(lang)
            self._buffer.clear()
            self._committed = ""
            self._previous = ""
            self._bytes_since_feed = 0
        return _remove_suffix_prefix_overlap(committed, tail).strip()

    def reset(self) -> None:
        """Drop buffered audio and state (used on barge-in / interrupt)."""
        with self._lock:
            self._buffer.clear()
            self._bytes_since_feed = 0
            self._committed = ""
            self._previous = ""
