from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import json
import re

from core.schemas import VALID_EMOTIONS

_EMOTION_PATTERN = re.compile(
    r"<!--\s*emotion:\s*(\{.*?\})\s*-->",
    re.DOTALL,
)


def extract_emotion(response_text: str) -> tuple[str, str]:
    """Extract emotion metadata from LLM response text.

    The LLM appends ``<!-- emotion: {"emotion": "smile"} -->`` to its
    response.  This function strips the tag and returns the clean text
    plus the emotion name.

    Returns:
        (clean_text, emotion) where *emotion* falls back to ``"neutral"``
        when missing or invalid.
    """
    match = _EMOTION_PATTERN.search(response_text)
    if not match:
        return response_text, "neutral"

    clean_text = _EMOTION_PATTERN.sub("", response_text).rstrip()

    try:
        meta = json.loads(match.group(1))
        emotion = meta.get("emotion", "neutral")
        if emotion not in VALID_EMOTIONS:
            emotion = "neutral"
        return clean_text, emotion
    except (json.JSONDecodeError, AttributeError):
        return clean_text, "neutral"
