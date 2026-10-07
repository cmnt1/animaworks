from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared construction path for Web and phone VoiceSession instances."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.voice.emotion_style import VoiceChannel, emotion_style_for
from core.voice.session import VoiceSession
from core.voice.stt import VoiceSTT
from core.voice.transport import VoiceTransport
from core.voice.tts_factory import create_tts_provider
from core.voice.voice_config import load_per_anima_voice, load_per_anima_voice_front


def build_voice_session(
    *,
    anima_name: str,
    transport: VoiceTransport,
    stt: VoiceSTT,
    supervisor: Any,
    animas_dir: Path,
    voice_config: Any,
    channel: VoiceChannel = "web",
    from_person: str = "human",
    thread_id: str | None = None,
    proactive_enabled: bool | None = None,
    human_notification_config: Any | None = None,
    report_delegations_on_close: bool | None = None,
    delegation_report_wait_sec: float = 30 * 60,
    tts_factory: Callable[..., Any] = create_tts_provider,
    tts_config_loader: Callable[..., Any] = load_per_anima_voice,
    front_settings_loader: Callable[..., Any] = load_per_anima_voice_front,
) -> VoiceSession:
    """Resolve per-Anima TTS/front settings and construct the common session."""
    tts_config = tts_config_loader(animas_dir, anima_name, voice_config)
    tts = tts_factory(tts_config.provider, voice_config)
    front_model, front_api_base = front_settings_loader(animas_dir, anima_name, voice_config)
    return VoiceSession(
        anima_name=anima_name,
        transport=transport,
        stt=stt,
        tts=tts,
        tts_config=tts_config,
        supervisor=supervisor,
        voice_config=voice_config,
        front_model=front_model,
        front_api_base=front_api_base,
        channel=channel,
        emotion_style=emotion_style_for(tts_config.provider),
        from_person=from_person,
        thread_id=thread_id,
        animas_dir=animas_dir,
        proactive_enabled=proactive_enabled,
        human_notification_config=human_notification_config,
        report_delegations_on_close=report_delegations_on_close,
        delegation_report_wait_sec=delegation_report_wait_sec,
    )


__all__ = ["build_voice_session"]
