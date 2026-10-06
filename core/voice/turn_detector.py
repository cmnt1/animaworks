from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Server-side Silero VAD and browser-compatible turn detection."""

import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from core.voice.session import VoiceSession

SAMPLE_RATE = 16_000
SAMPLES_PER_FRAME = 512
BYTES_PER_SAMPLE = 2
FRAME_BYTES = SAMPLES_PER_FRAME * BYTES_PER_SAMPLE
FRAME_MS = SAMPLES_PER_FRAME * 1000 // SAMPLE_RATE

POSITIVE_SPEECH_THRESHOLD = 0.5
NEGATIVE_SPEECH_THRESHOLD = 0.35
MIN_SPEECH_MS = 400
REDEMPTION_MS = 1400
PRE_SPEECH_PAD_MS = 800
BARGE_PROB_THRESHOLD = 0.75
BARGE_MIN_MS = 600
ECHO_TAIL_MS = 1200

_PRE_SPEECH_PAD_FRAMES = (PRE_SPEECH_PAD_MS + FRAME_MS - 1) // FRAME_MS

TurnEventType = Literal["speech_start", "audio", "speech_end", "misfire", "barge_probe"]


@dataclass(frozen=True, slots=True)
class TurnDetectorEvent:
    """One detector output; ``audio`` is populated only for audio events."""

    type: TurnEventType
    audio: bytes | None = None


class TurnDetector:
    """Detect speech turns from little-endian 16 kHz mono PCM16 input.

    ``probability_fn`` is an optional test seam that receives each complete
    32 ms PCM frame and returns its Silero-style speech probability. Without
    it, ``faster_whisper.vad.get_vad_model`` is loaded lazily on first audio.
    """

    def __init__(
        self,
        probability_fn: Callable[[bytes], float] | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._probability_fn = probability_fn
        self._clock = clock
        self._pcm_buffer = bytearray()
        self._pre_speech_frames: deque[bytes] = deque(maxlen=_PRE_SPEECH_PAD_FRAMES)
        self._speech_active = False
        self._playback_candidate = False
        self._barge_probe_sent = False
        self._held_audio = bytearray()
        self._voiced_ms = 0
        self._silence_ms = 0
        self._barge_candidate_ms = 0
        self._playback_active = False
        self.playback_ended_at: float | None = None

        self._vad_model: Any | None = None
        self._vad_numpy: Any | None = None
        self._vad_api: str | None = None
        self._vad_state: Any | None = None
        self._vad_session: Any | None = None
        self._vad_context_size = 0
        self._vad_context: Any | None = None
        self._vad_h: Any | None = None
        self._vad_c: Any | None = None

    @property
    def is_playback_active(self) -> bool:
        """Whether the transport currently reports active audio playback."""
        return self._playback_active

    def set_playback_active(self, active: bool) -> None:
        """Update playback state and start the 1200 ms echo-tail window."""
        active = bool(active)
        if active == self._playback_active:
            return
        if active:
            if self._speech_active and not self._barge_probe_sent:
                self._reset_segment()
                self._pre_speech_frames.clear()
            self._playback_active = True
            self.playback_ended_at = None
            return

        self._playback_active = False
        self.playback_ended_at = self._clock()
        if self._speech_active and self._playback_candidate and not self._barge_probe_sent:
            self._reset_segment()
            self._pre_speech_frames.clear()
        elif self._barge_probe_sent:
            # A probe has been handed to STT. Continue forwarding its audio even
            # if the player reports paused/stopped before a verdict arrives.
            self._playback_candidate = False

    def resolve_barge_verdict(self, interrupt: bool) -> None:
        """Apply the session's verdict to playback gating.

        A rejected probe clears held state and keeps playback gated while the
        transport resumes TTS. A confirmed interruption opens the microphone;
        its current speech segment remains intact for ``speech_end``.
        """
        if interrupt:
            self._playback_active = False
            self.playback_ended_at = self._clock()
            self._playback_candidate = False
            return

        self._playback_active = True
        self.playback_ended_at = None
        self._reset_segment()
        self._pre_speech_frames.clear()

    def reset(self) -> None:
        """Clear detector and playback state between calls/sessions."""
        self._pcm_buffer.clear()
        self._pre_speech_frames.clear()
        self._reset_segment()
        self._playback_active = False
        self.playback_ended_at = None

    def feed(self, pcm: bytes) -> list[TurnDetectorEvent]:
        """Consume arbitrary PCM chunks and return turn events for full frames."""
        if not isinstance(pcm, (bytes, bytearray, memoryview)):
            raise TypeError("pcm must be bytes-like PCM16 data")
        self._pcm_buffer.extend(pcm)
        frame_count = len(self._pcm_buffer) // FRAME_BYTES
        if frame_count == 0:
            return []

        complete = bytes(self._pcm_buffer[: frame_count * FRAME_BYTES])
        del self._pcm_buffer[: frame_count * FRAME_BYTES]
        events: list[TurnDetectorEvent] = []
        pending_audio = bytearray()

        def flush_audio() -> None:
            if pending_audio:
                events.append(TurnDetectorEvent("audio", bytes(pending_audio)))
                pending_audio.clear()

        def emit(event_type: TurnEventType) -> None:
            flush_audio()
            events.append(TurnDetectorEvent(event_type))

        for index in range(frame_count):
            frame = complete[index * FRAME_BYTES : (index + 1) * FRAME_BYTES]
            now = self._clock()
            in_echo_tail = (
                self.playback_ended_at is not None
                and now - self.playback_ended_at < ECHO_TAIL_MS / 1000
                and not (self._speech_active and self._barge_probe_sent)
            )
            if in_echo_tail:
                self._pre_speech_frames.clear()
                if self._speech_active and self._playback_candidate and not self._barge_probe_sent:
                    self._reset_segment()
                continue

            probability = self._get_probability(frame)
            if not self._speech_active:
                if probability >= POSITIVE_SPEECH_THRESHOLD:
                    self._start_segment(frame, events, pending_audio)
                    if probability >= NEGATIVE_SPEECH_THRESHOLD:
                        self._voiced_ms += FRAME_MS
                    self._accumulate_barge_probability(probability, pending_audio, emit)
                else:
                    self._pre_speech_frames.append(frame)
                continue

            self._advance_segment(frame, probability, pending_audio, emit)

        flush_audio()
        return events

    def _start_segment(
        self,
        frame: bytes,
        events: list[TurnDetectorEvent],
        pending_audio: bytearray,
    ) -> None:
        self._speech_active = True
        self._playback_candidate = self._playback_active
        self._barge_probe_sent = False
        self._held_audio.clear()
        self._voiced_ms = 0
        self._silence_ms = 0
        self._barge_candidate_ms = 0
        prefix = b"".join(self._pre_speech_frames)
        events.append(TurnDetectorEvent("speech_start"))
        if self._playback_candidate:
            self._held_audio.extend(prefix)
            self._held_audio.extend(frame)
        else:
            pending_audio.extend(prefix)
            pending_audio.extend(frame)
        self._pre_speech_frames.append(frame)

    def _advance_segment(
        self,
        frame: bytes,
        probability: float,
        pending_audio: bytearray,
        emit: Callable[[TurnEventType], None],
    ) -> None:
        if probability < NEGATIVE_SPEECH_THRESHOLD:
            self._silence_ms += FRAME_MS
        else:
            self._silence_ms = 0
            self._voiced_ms += FRAME_MS

        if self._playback_candidate and not self._barge_probe_sent:
            self._held_audio.extend(frame)
            self._accumulate_barge_probability(probability, pending_audio, emit)
        else:
            pending_audio.extend(frame)

        self._pre_speech_frames.append(frame)
        if self._silence_ms < REDEMPTION_MS:
            return

        if self._playback_candidate and not self._barge_probe_sent:
            if self._voiced_ms < MIN_SPEECH_MS:
                emit("misfire")
        elif self._voiced_ms < MIN_SPEECH_MS:
            emit("misfire")
        else:
            emit("speech_end")
        self._reset_segment()

    def _accumulate_barge_probability(
        self,
        probability: float,
        pending_audio: bytearray,
        emit: Callable[[TurnEventType], None],
    ) -> None:
        if not self._playback_candidate or self._barge_probe_sent:
            return
        if probability >= BARGE_PROB_THRESHOLD:
            self._barge_candidate_ms += FRAME_MS
        if self._barge_candidate_ms < BARGE_MIN_MS:
            return

        emit("barge_probe")
        self._barge_probe_sent = True
        pending_audio.extend(self._held_audio)
        self._held_audio.clear()

    def _reset_segment(self) -> None:
        self._speech_active = False
        self._playback_candidate = False
        self._barge_probe_sent = False
        self._held_audio.clear()
        self._voiced_ms = 0
        self._silence_ms = 0
        self._barge_candidate_ms = 0

    def _get_probability(self, frame: bytes) -> float:
        if self._probability_fn is not None:
            return max(0.0, min(1.0, float(self._probability_fn(frame))))
        self._load_vad_model()
        assert self._vad_numpy is not None
        samples = self._vad_numpy.frombuffer(frame, dtype="<i2").astype(self._vad_numpy.float32) / 32768.0

        if self._vad_api == "legacy_stateful":
            output, self._vad_state = self._vad_model(samples.reshape(1, -1), self._vad_state, SAMPLE_RATE)
        elif self._vad_api == "streaming_onnx":
            assert self._vad_session is not None
            assert self._vad_context is not None
            assert self._vad_h is not None and self._vad_c is not None
            if self._vad_context_size:
                model_input = self._vad_numpy.concatenate((self._vad_context.reshape(-1), samples)).reshape(1, -1)
                self._vad_context = samples[-self._vad_context_size :].reshape(1, -1).copy()
            else:
                model_input = samples.reshape(1, -1)
            output, self._vad_h, self._vad_c = self._vad_session.run(
                None,
                {"input": model_input, "h": self._vad_h, "c": self._vad_c},
            )
        else:
            output = self._vad_model(samples, num_samples=SAMPLES_PER_FRAME)

        probability = float(self._vad_numpy.asarray(output).reshape(-1)[-1])
        return max(0.0, min(1.0, probability))

    def _load_vad_model(self) -> None:
        if self._vad_model is not None:
            return
        try:
            import numpy as np
            from faster_whisper.vad import get_vad_model
        except ImportError as exc:
            raise RuntimeError("TurnDetector requires the faster-whisper 'transcribe' extra") from exc

        model = get_vad_model()
        self._vad_numpy = np
        self._vad_model = model
        if callable(getattr(model, "get_initial_state", None)):
            self._vad_api = "legacy_stateful"
            self._vad_state = model.get_initial_state(1)
            return

        session = getattr(model, "session", None)
        if session is not None and callable(getattr(session, "run", None)):
            input_specs = {spec.name: spec for spec in session.get_inputs()}
            if {"input", "h", "c"}.issubset(input_specs):
                input_shape = input_specs["input"].shape
                self._vad_context_size = 64
                if input_shape and isinstance(input_shape[-1], int):
                    self._vad_context_size = max(0, int(input_shape[-1]) - SAMPLES_PER_FRAME)
                self._vad_context = np.zeros((1, self._vad_context_size), dtype=np.float32)
                self._vad_h = self._zero_state(np, input_specs["h"].shape)
                self._vad_c = self._zero_state(np, input_specs["c"].shape)
                self._vad_session = session
                self._vad_api = "streaming_onnx"
                return

        self._vad_api = "callable"

    @staticmethod
    def _zero_state(np: Any, shape: list[Any] | tuple[Any, ...]) -> Any:
        dimensions = [int(dim) if isinstance(dim, int) and dim > 0 else 1 for dim in shape]
        return np.zeros(dimensions, dtype=np.float32)


async def drive_session(events: Iterable[TurnDetectorEvent], session: VoiceSession) -> None:
    """Forward detector output to the existing VoiceSession input handlers."""
    for event in events:
        if event.type == "audio":
            await session.handle_audio_chunk(event.audio or b"")
        elif event.type == "speech_end":
            await session.handle_speech_end()
        elif event.type == "misfire":
            await session.handle_discard_audio()
        elif event.type == "barge_probe":
            await session.handle_barge_probe()
        # speech_start is informational; VoiceSession starts on its first audio.


__all__ = [
    "BARGE_MIN_MS",
    "BARGE_PROB_THRESHOLD",
    "ECHO_TAIL_MS",
    "FRAME_BYTES",
    "FRAME_MS",
    "MIN_SPEECH_MS",
    "NEGATIVE_SPEECH_THRESHOLD",
    "POSITIVE_SPEECH_THRESHOLD",
    "PRE_SPEECH_PAD_MS",
    "REDEMPTION_MS",
    "SAMPLE_RATE",
    "SAMPLES_PER_FRAME",
    "TurnDetector",
    "TurnDetectorEvent",
    "TurnEventType",
    "drive_session",
]
