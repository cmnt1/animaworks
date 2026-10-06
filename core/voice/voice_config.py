from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for resolving per-Anima voice settings."""

import json
from pathlib import Path
from typing import Any

from core.voice.tts_base import TTSConfig


def load_per_anima_voice(animas_dir: Path, name: str, voice_config: Any) -> TTSConfig:
    """Load the TTS settings from ``status.json``, falling back to global defaults.

    The WebSocket voice route and the phone channel use the same resolution
    logic so an Anima keeps its configured voice across both channels.
    """
    status_path = animas_dir / name / "status.json"
    if not status_path.is_file():
        return TTSConfig(
            provider=voice_config.default_tts_provider,
            voice_id="",
            speed=1.0,
            pitch=0.0,
        )
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return TTSConfig(
            provider=voice_config.default_tts_provider,
            voice_id="",
            speed=1.0,
            pitch=0.0,
        )
    voice_section = data.get("voice") or {}
    if not isinstance(voice_section, dict):
        voice_section = {}
    return TTSConfig(
        provider=voice_section.get("tts_provider", voice_config.default_tts_provider),
        voice_id=voice_section.get("voice_id", ""),
        speed=float(voice_section.get("speed", 1.0)),
        pitch=float(voice_section.get("pitch", 0.0)),
        extra=voice_section.get("extra", {}),
    )


__all__ = ["load_per_anima_voice"]
