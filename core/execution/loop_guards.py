# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""In-loop guard mechanisms for the self-hosted execution loops (Mode A/B).

Three mechanisms selectively ported from the Hermes agent loop (behavioral
reference: ``~/vendor/hermes-agent/agent/conversation_loop.py`` /
``tool_guardrails.py``; see ``docs/issues/20260703_hermes-04``):

  - :func:`call_llm_with_retry` — transient-error retry *inside* the loop so
    a single 429/529 at iteration N does not discard all accumulated tool work.
  - :class:`EmptyResponseTracker` — bounded re-prompting when the model
    returns neither content nor tool calls instead of accepting an empty
    final response.
  - :class:`RunawayGuard` — consecutive-identical tool-call detection that
    warns, then forces finalization, before ``max_turns`` is burned.

This module is stdlib-only by design: the error classifier, backoff function,
and rate-guard callbacks from Issue 02 are injected by callers rather than
imported here, so the coupling stays at the single integration point.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

logger = logging.getLogger("animaworks.execution.loop_guards")

# Retry / reprompt / runaway bounds.  Module constants, not config: these are
# conservative Hermes-equivalent defaults and every path is additionally
# bounded by the loop's own ``max_turns``.
MAX_LLM_RETRIES = 3
EMPTY_RESPONSE_REPROMPT_LIMIT = 2
RUNAWAY_WARN_THRESHOLD = 3
RUNAWAY_HALT_THRESHOLD = 5


class LlmCallInterrupted(Exception):
    """Raised when an interrupt arrives while waiting out a retry backoff."""


async def call_llm_with_retry(
    call_factory: Callable[[], Awaitable[Any]],
    *,
    classify: Callable[[Exception], tuple[Any, Any]],
    next_backoff: Callable[[float], float],
    interrupt_check: Callable[[], bool] | None = None,
    on_classified_error: Callable[[Any, Any, Exception, int], None] | None = None,
    max_retries: int = MAX_LLM_RETRIES,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> Any:
    """Call an LLM with in-loop retry on transient failures.

    The call is retried at most ``max_retries`` times when the injected
    classifier reports the error as retryable (``hint.retryable``).  The
    conversation ``messages`` are untouched by a failed call (callers only
    append after a response is received), so re-invoking ``call_factory``
    with the same closure is safe.

    Args:
        call_factory: Zero-arg coroutine factory performing the actual call.
        classify: ``(exc) -> (reason, hint)`` — Issue 02's
            ``classify_llm_error`` pre-bound with the provider family.  The
            hint must expose ``retryable`` and ``backoff_s`` attributes.
        next_backoff: ``(prev_delay) -> delay`` — Issue 02's
            ``decorrelated_jitter``.  Used when the hint carries no
            provider-supplied ``Retry-After``.
        interrupt_check: Returns True when the session was interrupted;
            checked before and after each backoff sleep so a chat collision
            aborts the wait instead of blocking on it.
        on_classified_error: Observability callback invoked once per failed
            attempt (rate-guard reporting, auth logging).  Exceptions from
            the callback are swallowed — reporting must never mask the call
            outcome.
        max_retries: Maximum number of *re*-invocations after the first.
        sleep: Injectable for tests.

    Returns:
        The successful response object.

    Raises:
        LlmCallInterrupted: Interrupt observed during backoff.
        Exception: The original provider exception when the error is not
            retryable or the retry budget is exhausted.
    """
    prev_delay = 0.0
    for attempt in range(max_retries + 1):
        try:
            return await call_factory()
        except Exception as exc:
            reason, hint = classify(exc)
            if on_classified_error is not None:
                try:
                    on_classified_error(reason, hint, exc, attempt)
                except Exception:
                    logger.debug("on_classified_error callback failed", exc_info=True)
            if not getattr(hint, "retryable", False) or attempt >= max_retries:
                raise
            if interrupt_check is not None and interrupt_check():
                raise LlmCallInterrupted() from exc
            backoff_s = getattr(hint, "backoff_s", None)
            delay = float(backoff_s) if backoff_s is not None else float(next_backoff(prev_delay))
            prev_delay = delay
            logger.warning(
                "LLM call failed (%s); in-loop retry %d/%d in %.1fs",
                getattr(reason, "value", reason),
                attempt + 1,
                max_retries,
                delay,
            )
            # Sleep in 1s chunks so an interrupt (chat collision) aborts the
            # wait within a second instead of blocking for the full backoff
            # (up to 120s / Retry-After).
            remaining = delay
            while remaining > 0:
                await sleep(min(1.0, remaining))
                remaining -= 1.0
                if interrupt_check is not None and interrupt_check():
                    raise LlmCallInterrupted() from exc
    # Unreachable: the last loop iteration either returns or raises.
    raise RuntimeError("call_llm_with_retry exited without result")  # pragma: no cover


class EmptyResponseTracker:
    """Bounded re-prompt budget for empty (no content, no tool call) responses."""

    def __init__(self, limit: int = EMPTY_RESPONSE_REPROMPT_LIMIT) -> None:
        self._limit = limit
        self._count = 0

    @staticmethod
    def is_empty(text: str | None, has_tool_calls: bool) -> bool:
        """True when the response carries neither visible text nor tool calls.

        ``text`` must be the *visible* content — callers strip thinking tags
        first so a thinking-only response counts as empty.
        """
        if has_tool_calls:
            return False
        return not (text or "").strip()

    def should_reprompt(self) -> bool:
        """Consume one reprompt slot; False once the budget is exhausted."""
        if self._count >= self._limit:
            return False
        self._count += 1
        return True

    @property
    def reprompts_used(self) -> int:
        return self._count


def tool_call_signature(tool_name: str, args: Mapping[str, Any] | None) -> str:
    """Canonical signature for one tool call: name + sorted-key JSON args hash."""
    try:
        canonical = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        canonical = repr(sorted((args or {}).items(), key=lambda kv: str(kv[0])))
    digest = hashlib.sha256(canonical.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{tool_name}:{digest}"


class RunawayGuard:
    """Detect a model repeating the identical tool-call turn back to back.

    A *turn signature* is the ordered tuple of per-call signatures in one
    assistant turn (Mode B turns carry exactly one call, so this degenerates
    to per-call tracking).  Consecutive identical turns advance a streak:
    at ``warn_threshold`` the caller injects a warning reminder (execution
    continues), at ``halt_threshold`` the caller strips tools and forces the
    grace-turn finalization.  Any differing turn resets the streak, so
    legitimate long tool sessions are unaffected.
    """

    OK = "ok"
    WARN = "warn"
    HALT = "halt"

    def __init__(
        self,
        warn_threshold: int = RUNAWAY_WARN_THRESHOLD,
        halt_threshold: int = RUNAWAY_HALT_THRESHOLD,
    ) -> None:
        self._warn_threshold = warn_threshold
        self._halt_threshold = halt_threshold
        self._last_signature: tuple[str, ...] | None = None
        self._streak = 0

    def observe(self, turn_signature: tuple[str, ...]) -> str:
        """Record one tool-call turn; return ``"ok"`` / ``"warn"`` / ``"halt"``.

        ``"warn"`` fires exactly once per streak (at the warn threshold) so a
        second reminder is not stacked while the model still has a chance to
        change course before the halt threshold.
        """
        if not turn_signature:
            return self.OK
        if turn_signature == self._last_signature:
            self._streak += 1
        else:
            self._last_signature = turn_signature
            self._streak = 1
        if self._streak >= self._halt_threshold:
            return self.HALT
        if self._streak == self._warn_threshold:
            return self.WARN
        return self.OK

    @property
    def streak(self) -> int:
        return self._streak


__all__ = [
    "EMPTY_RESPONSE_REPROMPT_LIMIT",
    "MAX_LLM_RETRIES",
    "RUNAWAY_HALT_THRESHOLD",
    "RUNAWAY_WARN_THRESHOLD",
    "EmptyResponseTracker",
    "LlmCallInterrupted",
    "RunawayGuard",
    "call_llm_with_retry",
    "tool_call_signature",
]
