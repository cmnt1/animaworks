# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Voice front lane — lightweight speech-first chat path via a local LLM.

The front lane connects directly to a small, fast OpenAI-compatible endpoint
(llama.cpp) that reuses the same Anima persona, and keeps an in-session
user/assistant history so it can carry a conversation without the full
agent loop (large-model TTFT regression).  Tools are not used yet; the
``tools`` argument is accepted so PR-3 (``ask_anima``) can hook in later.
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import litellm

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TOKENS = 2048
_DEFAULT_TEMPERATURE = 0.7
_HEALTH_TIMEOUT = 5.0

# Matches the emotion tag the voice-mode rules require, e.g.
# ``<!-- emotion: {"emotion": "smile"} -->``.
_EMOTION_RE = re.compile(r"<!--\s*emotion:\s*\{.*?\"emotion\"\s*:\s*\"([^\"]+)\"")


def extract_emotion(full_text: str) -> str:
    """Parse the emotion tag from a front response; default to ``neutral``."""
    match = _EMOTION_RE.search(full_text or "")
    if match:
        from core.schemas import VALID_EMOTIONS

        emotion = match.group(1)
        if emotion in VALID_EMOTIONS:
            return emotion
    return "neutral"


class VoiceFrontLane:
    """Direct conversation lane to the fixed, fast front model.

    The system prompt is fixed for the whole session (prefix-cache
    friendly); only the user/assistant message list grows each turn.
    """

    def __init__(
        self,
        *,
        model: str,
        api_base: str,
        system_prompt: str,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
        timeout: float = 120.0,
        num_retries: int = 1,
    ) -> None:
        self._model = model
        self._api_base = (api_base or "").rstrip("/")
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout
        self._num_retries = num_retries
        self._history: list[dict[str, str]] = []
        self._last_full_text = ""

    # ── session control ──────────────────────────────────────────

    def set_history(self, history: list[dict[str, str]]) -> None:
        """Seed the in-session conversation history (optional)."""
        self._history = list(history)

    def reset_turn(self) -> None:
        """Clear the previous turn's accumulator before a new stream."""
        self._last_full_text = ""

    @property
    def last_full_text(self) -> str:
        """Text of the most recent assistant turn (accumulated deltas)."""
        return self._last_full_text

    @property
    def history(self) -> list[dict[str, str]]:
        """Copy of the in-session user/assistant message list."""
        return list(self._history)

    # ── health / reachability ───────────────────────────────────

    async def check_health(self) -> bool:
        """Lightweight reachability check against the OpenAI-compatible API.

        Mirrors the shape of the existing TTS health check: cheap, caches
        nothing (call before every response), and returns ``False`` on any
        failure so the caller can fall back to the full agent loop.
        """
        if not self._api_base:
            return False
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT) as client:
                resp = await client.get(f"{self._api_base}/models")
                return resp.status_code < 500
        except Exception:
            logger.debug("voice front health check failed", exc_info=True)
            return False

    # ── streaming completion ────────────────────────────────────

    async def stream(
        self,
        user_text: str,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Send a user turn through the front lane and yield text deltas.

        The assistant reply is appended to the in-session history so the
        next turn keeps conversational context.
        """
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt}
        ]
        messages.extend(self._history)
        messages.append({"role": "user", "content": user_text})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "timeout": self._timeout,
            "num_retries": self._num_retries,
        }
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if tools:
            kwargs["tools"] = tools

        response = await litellm.acompletion(**kwargs)

        chunks: list[str] = []
        async for chunk in response:
            if chunk is None:
                continue
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None
            if content:
                chunks.append(content)
                yield content

        full_text = "".join(chunks)
        self._history.append({"role": "user", "content": user_text})
        self._history.append({"role": "assistant", "content": full_text})
        self._last_full_text = full_text
