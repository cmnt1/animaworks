# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Voice STT — in-memory PCM transcription via faster-whisper."""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)

# ── Whisper singleton ──────────────────────────────────────────

_whisper_model: Any | None = None


def _load_whisper_model_class():
    """Import the optional STT dependency only when transcription is requested."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ImportError(
            "Voice STT requires 'faster-whisper'. Install with: pip install animaworks[transcribe]"
        ) from exc
    return WhisperModel


# ── VoiceSTT ───────────────────────────────────────────────────


class VoiceSTT:
    """In-memory speech-to-text using faster-whisper core."""

    def __init__(
        self,
        model_name: str = "large-v3-turbo",
        device: str = "auto",
        compute_type: str = "default",
        language: str | None = None,
    ) -> None:
        """Initialize STT engine.

        Args:
            model_name: Whisper model name.
            device: Device ("auto", "cuda", "cpu").
            compute_type: Compute type ("default", "float16", "int8", etc.).
            language: Preferred language code, or None to auto-detect.
        """
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._model: Any | None = None

    def _ensure_model(self) -> Any:
        """Lazy-load WhisperModel singleton."""
        global _whisper_model
        if _whisper_model is None:
            whisper_model_class = _load_whisper_model_class()
            device = self._device
            if device == "auto":
                device = "cuda" if shutil.which("nvidia-smi") else "cpu"
            compute = self._compute_type
            if compute == "default":
                compute = "float16" if device == "cuda" else "int8"
            _whisper_model = whisper_model_class(self._model_name, device=device, compute_type=compute)
        return _whisper_model

    def transcribe_buffer(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        language: str | None = None,
        vad_filter: bool = True,
        initial_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Transcribe in-memory PCM audio buffer.

        Args:
            audio_data: Raw PCM 16-bit mono audio bytes.
            sample_rate: Sample rate (default 16kHz).
            language: Language code or None for auto-detect.
            vad_filter: Apply VAD filtering.
            initial_prompt: Optional context text (e.g. committed tail) to help
                streaming re-decodes after audio has been trimmed.

        Returns:
            Dict with raw_text, language, duration, segments.
        """
        import numpy as np

        model = self._ensure_model()
        audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
        transcribe_options: dict[str, Any] = {
            "beam_size": 1,
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.6,
            "temperature": 0.0,
            "vad_filter": vad_filter,
            "initial_prompt": initial_prompt,
        }
        selected_language = language if language is not None else self._language
        if selected_language is not None:
            transcribe_options["language"] = selected_language
        segments, info = model.transcribe(audio_np, **transcribe_options)
        segments_list = list(segments)
        raw_text = " ".join(seg.text.strip() for seg in segments_list)
        return {
            "raw_text": raw_text,
            "language": info.language,
            "duration": info.duration,
            "segments": [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments_list],
        }

    async def transcribe_buffer_async(
        self,
        audio_data: bytes,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Async wrapper running transcribe in thread pool.

        Args:
            audio_data: Raw PCM 16-bit mono audio bytes.
            **kwargs: Passed to transcribe_buffer.

        Returns:
            Dict with raw_text, language, duration, segments.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.transcribe_buffer(audio_data, **kwargs),
        )
