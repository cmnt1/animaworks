from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Phone speech rendering using each Anima's configured TTS voice."""

import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

from core.voice.tts_factory import create_tts_provider
from core.voice.voice_config import load_per_anima_voice

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]*\)", re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```(?:[^\n`]*)\n?(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_STATIC_AUDIO_CACHE: OrderedDict[tuple[str, str, str, str], bytes] = OrderedDict()
_STATIC_AUDIO_CACHE_LIMIT = 128


def clean_for_speech(text: str, *, max_chars: int = 400) -> str:
    """Remove common Markdown noise, replace URLs, and cap spoken text."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    clean = _CODE_FENCE_RE.sub(r"\1", str(text or ""))
    clean = _MARKDOWN_LINK_RE.sub(lambda match: f"{match.group(1)}、リンク", clean)
    clean = _URL_RE.sub("リンク", clean)
    clean = _INLINE_CODE_RE.sub(r"\1", clean)
    clean = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", clean)
    clean = re.sub(r"(?m)^\s*>\s?", "", clean)
    clean = re.sub(r"(?m)^\s*(?:[-+*]|\d+[.)])\s+", "", clean)
    clean = re.sub(r"\*\*|__|~~", "", clean)
    clean = re.sub(r"(?<!\w)[*_]|[*_](?!\w)", "", clean)
    clean = clean.replace("|", " ")
    clean = re.sub(r"[ \t]*\n[ \t]*", "\n", clean)
    clean = re.sub(r"\n{2,}", "\n", clean).strip()
    if len(clean) > max_chars:
        clean = clean[: max_chars - 1].rstrip() + "…"
    return clean


async def synthesize_speech(
    anima: str,
    text: str,
    *,
    animas_dir: Path | None = None,
    voice_config: Any | None = None,
    cache_key: str | None = None,
    max_chars: int = 400,
) -> bytes:
    """Convert text to WAV with the same per-Anima voice settings as web voice."""
    from core.config import load_config
    from core.paths import get_animas_dir

    cleaned = clean_for_speech(text, max_chars=max_chars)
    if not cleaned:
        raise ValueError("phone speech text is empty")

    if voice_config is None:
        voice_config = load_config().voice
    effective_animas_dir = animas_dir or get_animas_dir()
    tts_config = load_per_anima_voice(effective_animas_dir, anima, voice_config)

    key = None
    if cache_key:
        key = (str(effective_animas_dir), anima, cache_key, f"{tts_config.provider}:{tts_config.voice_id}")
        cached = _STATIC_AUDIO_CACHE.get(key)
        if cached is not None:
            _STATIC_AUDIO_CACHE.move_to_end(key)
            return cached

    provider = create_tts_provider(tts_config.provider, voice_config)
    audio = await provider.synthesize_full(cleaned, tts_config)
    if not audio:
        raise ValueError("TTS returned empty audio")

    if key is not None:
        _STATIC_AUDIO_CACHE[key] = bytes(audio)
        _STATIC_AUDIO_CACHE.move_to_end(key)
        while len(_STATIC_AUDIO_CACHE) > _STATIC_AUDIO_CACHE_LIMIT:
            _STATIC_AUDIO_CACHE.popitem(last=False)
    return bytes(audio)


def clear_static_audio_cache() -> None:
    """Clear the process-local phrase cache (used during tests/shutdown)."""
    _STATIC_AUDIO_CACHE.clear()


__all__ = ["clean_for_speech", "clear_static_audio_cache", "synthesize_speech"]
