"""Shared emotion-tag extraction for LLM responses.

The LLM appends a trailing metadata tag of the form
``<!-- emotion: {"emotion": "smile"} -->`` to some responses.  Multiple
consumers (chat API, messaging, voice front) previously each had their own
(regex-incompatible) implementation.  This module unifies them into one
lenient parser so every path returns the same result for the same input.

Parse behaviour is intentionally permissive (the "most lenient" of the
former implementations):

* a missing closing ``-->`` is tolerated,
* newlines / arbitrary whitespace inside the JSON object are allowed,
* if the JSON object cannot be decoded, a best-effort regex extracts the
  ``"emotion": "value"`` pair.

``parse_emotion_value`` returns only the emotion name (used by voice);
``extract_emotion`` also returns the tag-stripped clean text.
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re

from core.schemas import VALID_EMOTIONS

_NEUTRAL = "neutral"

# Lenient tag pattern: optional closing ``-->``, DOTALL so newlines within
# the JSON object are captured.
_EMOTION_PATTERN = re.compile(
    r"<!--\s*emotion:\s*(\{.*?\})\s*(?:-->)?",
    re.DOTALL,
)

# Best-effort fallback for undecodable JSON (mirrors the former voice-front
# behaviour of keying on ``"emotion": "value"`` alone).
_FALLBACK_EMOTION_RE = re.compile(r'"emotion"\s*:\s*"([^"]+)"')


def _parse_emotion(raw: str) -> str:
    emotion = ""
    try:
        meta = json.loads(raw)
        if isinstance(meta, dict):
            emotion = meta.get("emotion", "")
    except (json.JSONDecodeError, AttributeError, TypeError):
        emotion = ""
    if not emotion:
        fallback = _FALLBACK_EMOTION_RE.search(raw)
        if fallback:
            emotion = fallback.group(1)
    if emotion not in VALID_EMOTIONS:
        return _NEUTRAL
    return emotion


def parse_emotion_value(response_text: str) -> str:
    """Extract only the emotion name; falls back to ``"neutral"``."""
    if not response_text:
        return _NEUTRAL
    match = _EMOTION_PATTERN.search(response_text)
    if not match:
        return _NEUTRAL
    return _parse_emotion(match.group(1))


def extract_emotion(response_text: str) -> tuple[str, str]:
    """Extract emotion metadata, returning ``(clean_text, emotion)``.

    The tag is stripped from *response_text* and the emotion name
    returned (``"neutral"`` when missing or invalid).
    """
    if not response_text:
        return response_text or "", _NEUTRAL
    match = _EMOTION_PATTERN.search(response_text)
    if not match:
        return response_text, _NEUTRAL
    clean_text = _EMOTION_PATTERN.sub("", response_text).rstrip()
    return clean_text, _parse_emotion(match.group(1))
