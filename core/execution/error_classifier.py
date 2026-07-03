# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Centralized LLM API error classification for coordinated recovery.

Converts provider exceptions (litellm, Anthropic SDK, httpx, generic) into a
structured :class:`FailoverReason` plus a :class:`RecoveryHint` the calling
code consults instead of re-inspecting the exception.  The classifier follows
the "classify once, recover by hint" principle: disambiguation lives here, the
recovery side only reads the hint.

The reason taxonomy is a 12-member subset covering the providers AnimaWorks
actually uses (Anthropic family, OpenAI family, LiteLLM-generic).  Ambiguity
resolution (429 rate-limit vs overloaded, 400 context-overflow vs invalid
request, deterministic 5xx validation errors) mirrors the priority pipeline in
``~/vendor/hermes-agent/agent/error_classifier.py``.
"""

from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("animaworks.execution.error_classifier")


# ── Error taxonomy ──────────────────────────────────────────────────────────


class FailoverReason(enum.Enum):
    """Why an LLM call failed — determines the recovery strategy."""

    AUTH = "auth"                        # 401/403 — credential problem, human action
    BILLING = "billing"                  # 402 / credit exhaustion — human action
    RATE_LIMIT = "rate_limit"            # 429 per-credential throttle — backoff
    OVERLOADED = "overloaded"            # 503/529 / server-busy 429 — backoff
    CONTEXT_OVERFLOW = "context_overflow"  # prompt too large — compress (future)
    PAYLOAD_TOO_LARGE = "payload_too_large"  # 413 — shrink payload
    CONTENT_POLICY = "content_policy"    # safety filter — deterministic, terminal
    TIMEOUT = "timeout"                  # connection/read timeout — retry
    NETWORK = "network"                  # transport failure — retry
    SERVER_ERROR = "server_error"        # 500/502 — retry
    INVALID_REQUEST = "invalid_request"  # malformed request — deterministic, terminal
    UNKNOWN = "unknown"                  # unclassifiable — degrade to current behavior


# ── Recovery hint ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RecoveryHint:
    """Recovery guidance the caller applies without re-classifying.

    Attributes:
        retryable: Whether retrying the *same* backend is worthwhile.
        fallback_ok: Whether trying a *different* backend is worthwhile.
        backoff_s: Provider-supplied wait (``Retry-After``) if present, else
            ``None`` — the caller computes jitter when this is ``None``.
        is_terminal: Whether the request is deterministically rejected on the
            same provider (retrying unchanged reproduces the failure).
    """

    retryable: bool
    fallback_ok: bool
    backoff_s: float | None
    is_terminal: bool


# Per-reason hint templates.  ``backoff_s`` is filled in by the classifier when
# a ``Retry-After`` value is available (rate_limit / overloaded).
_HINTS: dict[FailoverReason, RecoveryHint] = {
    FailoverReason.AUTH: RecoveryHint(retryable=False, fallback_ok=True, backoff_s=None, is_terminal=False),
    FailoverReason.BILLING: RecoveryHint(retryable=False, fallback_ok=True, backoff_s=None, is_terminal=False),
    FailoverReason.RATE_LIMIT: RecoveryHint(retryable=True, fallback_ok=True, backoff_s=None, is_terminal=False),
    FailoverReason.OVERLOADED: RecoveryHint(retryable=True, fallback_ok=True, backoff_s=None, is_terminal=False),
    FailoverReason.CONTEXT_OVERFLOW: RecoveryHint(retryable=False, fallback_ok=True, backoff_s=None, is_terminal=False),
    FailoverReason.PAYLOAD_TOO_LARGE: RecoveryHint(retryable=False, fallback_ok=True, backoff_s=None, is_terminal=False),
    FailoverReason.CONTENT_POLICY: RecoveryHint(retryable=False, fallback_ok=False, backoff_s=None, is_terminal=True),
    FailoverReason.TIMEOUT: RecoveryHint(retryable=True, fallback_ok=True, backoff_s=None, is_terminal=False),
    FailoverReason.NETWORK: RecoveryHint(retryable=True, fallback_ok=True, backoff_s=None, is_terminal=False),
    FailoverReason.SERVER_ERROR: RecoveryHint(retryable=True, fallback_ok=True, backoff_s=None, is_terminal=False),
    FailoverReason.INVALID_REQUEST: RecoveryHint(retryable=False, fallback_ok=True, backoff_s=None, is_terminal=True),
    FailoverReason.UNKNOWN: RecoveryHint(retryable=True, fallback_ok=True, backoff_s=None, is_terminal=False),
}


def _hint_for(reason: FailoverReason, backoff_s: float | None = None) -> RecoveryHint:
    base = _HINTS[reason]
    if backoff_s is None:
        return base
    return RecoveryHint(
        retryable=base.retryable,
        fallback_ok=base.fallback_ok,
        backoff_s=backoff_s,
        is_terminal=base.is_terminal,
    )


# ── Provider-family resolution ──────────────────────────────────────────────

_ANTHROPIC_FAMILY_RE = re.compile(
    r"^(anthropic/|bedrock/|vertex_ai/)?"
    r"([a-z]{2}\.anthropic\.)?"
    r"claude-",
)


def provider_family_of(model: str) -> str:
    """Map a model identifier to its provider family for rate-guard keying.

    Families are coarse on purpose (``anthropic`` / ``openai`` / ``google`` /
    LiteLLM provider prefix): the guard protects a shared credential, so a
    family-level key is sufficient and avoids lock contention.
    """
    m = (model or "").strip().lower()
    if not m:
        return "unknown"
    if _ANTHROPIC_FAMILY_RE.match(m):
        return "anthropic"
    prefix = m.split("/", 1)[0] if "/" in m else ""
    if prefix in {"gemini", "google", "vertex_ai"} or "gemini" in m:
        return "google"
    if prefix == "openai" or "claude" not in m and (
        m.startswith(("gpt", "o1-", "o3-", "o4-", "codex")) or prefix in {"codex", "openai-codex", "azure"}
    ):
        return "openai"
    if "claude" in m:
        return "anthropic"
    if prefix:
        return prefix
    return "unknown"


# ── Pattern tables (narrow, provider-verbatim) ──────────────────────────────

# Safety-filter refusals — deterministic per prompt, must run before status
# classification so a 400 safety block is not downgraded to invalid_request.
_CONTENT_POLICY_PATTERNS = (
    "flagged for possible cybersecurity risk",
    "trusted access for cyber",
    "violates our usage policies",
    "violates openai's usage policies",
    "your request was flagged by",
    "prompt was flagged by our safety",
    "responses cannot be generated due to safety",
    "content_filter",
    "responsibleaipolicyviolation",
)

# Provider-side overload — server busy, back off and retry the same key.  Some
# providers reuse HTTP 429 for this, so it is checked before the rate_limit
# default on the 429 path.
_OVERLOADED_PATTERNS = (
    "overloaded",
    "temporarily overloaded",
    "server is overloaded",
    "service is overloaded",
    "currently overloaded",
    "at capacity",
    "over capacity",
)

_RATE_LIMIT_PATTERNS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "throttled",
    "throttlingexception",
    "requests per minute",
    "tokens per minute",
    "requests per day",
    "resource_exhausted",
    "quota exceeded",
    "please retry after",
    "try again in",
)

_BILLING_PATTERNS = (
    "insufficient credits",
    "insufficient_quota",
    "insufficient balance",
    "credit balance",
    "credits exhausted",
    "payment required",
    "billing hard limit",
    "exceeded your current quota",
    "account is deactivated",
    "out of funds",
    "balance_depleted",
)

_CONTEXT_OVERFLOW_PATTERNS = (
    "context length",
    "context size",
    "maximum context",
    "context window",
    "token limit",
    "too many tokens",
    "reduce the length",
    "prompt is too long",
    "prompt exceeds max length",
    "context_length_exceeded",
    "maximum number of tokens",
    "input is too long",
    "max_model_len",
)

# Deterministic request-validation signals — the request fails identically on
# every retry.  Some gateways return these as 5xx, so they are checked on both
# the 400 and 5xx paths before the generic server_error / invalid_request rule.
_REQUEST_VALIDATION_PATTERNS = (
    "unknown parameter",
    "unsupported parameter",
    "unrecognized request argument",
    "invalid_request_error",
    "unknown_parameter",
    "unsupported_parameter",
)

_AUTH_PATTERNS = (
    "invalid api key",
    "invalid_api_key",
    "authentication",
    "unauthorized",
    "forbidden",
    "invalid token",
    "token expired",
    "token revoked",
    "access denied",
    "permission denied",
)

_TIMEOUT_PATTERNS = (
    "timed out",
    "timeout",
    "deadline exceeded",
)

_NETWORK_PATTERNS = (
    "connection reset",
    "connection refused",
    "connection aborted",
    "connection error",
    "server disconnected",
    "broken pipe",
    "peer closed connection",
    "network is unreachable",
    "name resolution",
    "temporary failure in name resolution",
)

_TRANSPORT_ERROR_TYPES = frozenset({
    "ReadTimeout", "ConnectTimeout", "PoolTimeout", "WriteTimeout",
    "APITimeoutError", "Timeout",
    "ConnectError", "ConnectionError", "RemoteProtocolError", "ReadError",
    "ConnectionResetError", "ConnectionAbortedError", "BrokenPipeError",
    "APIConnectionError",
})


# ── Classification pipeline ─────────────────────────────────────────────────


def classify_llm_error(
    error: Exception,
    *,
    provider_family: str = "",
) -> tuple[FailoverReason, RecoveryHint]:
    """Classify an LLM API exception into a reason and recovery hint.

    Never raises: any failure inside the classifier is swallowed and reported
    as :attr:`FailoverReason.UNKNOWN` so the classifier can never become a new
    source of failure.

    Args:
        error: The exception raised by the provider call.
        provider_family: Coarse provider family (from
            :func:`provider_family_of`), reserved for family-specific
            disambiguation.  Unused today but part of the stable contract.

    Returns:
        ``(reason, hint)`` — the caller applies the hint without re-classifying.
    """
    try:
        return _classify(error, provider_family)
    except Exception:
        logger.debug("error classifier raised; degrading to unknown", exc_info=True)
        return FailoverReason.UNKNOWN, _hint_for(FailoverReason.UNKNOWN)


def _classify(error: Exception, provider_family: str) -> tuple[FailoverReason, RecoveryHint]:
    status_code = _extract_status_code(error)
    error_type = type(error).__name__
    if status_code is None and error_type in {"RateLimitError", "RateLimitException"}:
        status_code = 429
    msg = _build_message(error)
    retry_after = _extract_retry_after(error, msg)

    # 1. Content policy — deterministic safety refusal, before status routing.
    if any(p in msg for p in _CONTENT_POLICY_PATTERNS):
        return FailoverReason.CONTENT_POLICY, _hint_for(FailoverReason.CONTENT_POLICY)

    # 2. HTTP status code.
    if status_code is not None:
        classified = _classify_by_status(status_code, msg, retry_after)
        if classified is not None:
            return classified

    # 3. Message-pattern matching (no usable status code).
    classified = _classify_by_message(msg, retry_after)
    if classified is not None:
        return classified

    # 4. Transport heuristics.
    if error_type in _TRANSPORT_ERROR_TYPES:
        reason = FailoverReason.TIMEOUT if "timeout" in error_type.lower() else FailoverReason.NETWORK
        return reason, _hint_for(reason)
    if isinstance(error, TimeoutError):
        return FailoverReason.TIMEOUT, _hint_for(FailoverReason.TIMEOUT)
    if isinstance(error, (ConnectionError, OSError)):
        return FailoverReason.NETWORK, _hint_for(FailoverReason.NETWORK)

    # 5. Fallback: unknown (degrades to current blind-fallback behavior).
    return FailoverReason.UNKNOWN, _hint_for(FailoverReason.UNKNOWN)


def _classify_by_status(
    status_code: int,
    msg: str,
    retry_after: float | None,
) -> tuple[FailoverReason, RecoveryHint] | None:
    if status_code in {401, 403}:
        if status_code == 403 and any(p in msg for p in _BILLING_PATTERNS):
            return FailoverReason.BILLING, _hint_for(FailoverReason.BILLING)
        return FailoverReason.AUTH, _hint_for(FailoverReason.AUTH)

    if status_code == 402:
        if any(p in msg for p in _RATE_LIMIT_PATTERNS):
            return FailoverReason.RATE_LIMIT, _hint_for(FailoverReason.RATE_LIMIT, retry_after)
        return FailoverReason.BILLING, _hint_for(FailoverReason.BILLING)

    if status_code == 413:
        return FailoverReason.PAYLOAD_TOO_LARGE, _hint_for(FailoverReason.PAYLOAD_TOO_LARGE)

    if status_code == 429:
        if any(p in msg for p in _OVERLOADED_PATTERNS):
            return FailoverReason.OVERLOADED, _hint_for(FailoverReason.OVERLOADED, retry_after)
        if any(p in msg for p in _BILLING_PATTERNS):
            return FailoverReason.BILLING, _hint_for(FailoverReason.BILLING)
        return FailoverReason.RATE_LIMIT, _hint_for(FailoverReason.RATE_LIMIT, retry_after)

    if status_code == 400:
        return _classify_400(msg)

    if status_code in {500, 502}:
        if any(p in msg for p in _REQUEST_VALIDATION_PATTERNS):
            return FailoverReason.INVALID_REQUEST, _hint_for(FailoverReason.INVALID_REQUEST)
        if any(p in msg for p in _CONTEXT_OVERFLOW_PATTERNS):
            return FailoverReason.CONTEXT_OVERFLOW, _hint_for(FailoverReason.CONTEXT_OVERFLOW)
        return FailoverReason.SERVER_ERROR, _hint_for(FailoverReason.SERVER_ERROR)

    if status_code in {503, 529}:
        if any(p in msg for p in _CONTEXT_OVERFLOW_PATTERNS):
            return FailoverReason.CONTEXT_OVERFLOW, _hint_for(FailoverReason.CONTEXT_OVERFLOW)
        return FailoverReason.OVERLOADED, _hint_for(FailoverReason.OVERLOADED, retry_after)

    if 400 <= status_code < 500:
        return FailoverReason.INVALID_REQUEST, _hint_for(FailoverReason.INVALID_REQUEST)
    if 500 <= status_code < 600:
        return FailoverReason.SERVER_ERROR, _hint_for(FailoverReason.SERVER_ERROR)
    return None


def _classify_400(msg: str) -> tuple[FailoverReason, RecoveryHint]:
    """Disambiguate 400 — validation vs context-overflow vs rate/billing.

    Request-validation patterns are checked before context-overflow because a
    model rejecting ``max_tokens`` returns a message containing the literal
    ``max_tokens`` (a context-overflow token), which would otherwise mis-route
    a deterministic client error into the compression path.
    """
    if any(p in msg for p in _REQUEST_VALIDATION_PATTERNS):
        return FailoverReason.INVALID_REQUEST, _hint_for(FailoverReason.INVALID_REQUEST)
    if any(p in msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return FailoverReason.CONTEXT_OVERFLOW, _hint_for(FailoverReason.CONTEXT_OVERFLOW)
    if any(p in msg for p in _RATE_LIMIT_PATTERNS):
        return FailoverReason.RATE_LIMIT, _hint_for(FailoverReason.RATE_LIMIT)
    if any(p in msg for p in _BILLING_PATTERNS):
        return FailoverReason.BILLING, _hint_for(FailoverReason.BILLING)
    return FailoverReason.INVALID_REQUEST, _hint_for(FailoverReason.INVALID_REQUEST)


def _classify_by_message(
    msg: str,
    retry_after: float | None,
) -> tuple[FailoverReason, RecoveryHint] | None:
    # Overloaded before rate_limit/billing so a message-only overload does not
    # fall through to the rate-limit default.
    if any(p in msg for p in _OVERLOADED_PATTERNS):
        return FailoverReason.OVERLOADED, _hint_for(FailoverReason.OVERLOADED, retry_after)
    if any(p in msg for p in _BILLING_PATTERNS):
        return FailoverReason.BILLING, _hint_for(FailoverReason.BILLING)
    if any(p in msg for p in _RATE_LIMIT_PATTERNS):
        return FailoverReason.RATE_LIMIT, _hint_for(FailoverReason.RATE_LIMIT, retry_after)
    if any(p in msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return FailoverReason.CONTEXT_OVERFLOW, _hint_for(FailoverReason.CONTEXT_OVERFLOW)
    if any(p in msg for p in _AUTH_PATTERNS):
        return FailoverReason.AUTH, _hint_for(FailoverReason.AUTH)
    if any(p in msg for p in _TIMEOUT_PATTERNS):
        return FailoverReason.TIMEOUT, _hint_for(FailoverReason.TIMEOUT)
    if any(p in msg for p in _NETWORK_PATTERNS):
        return FailoverReason.NETWORK, _hint_for(FailoverReason.NETWORK)
    return None


# ── Extraction helpers ──────────────────────────────────────────────────────


def _extract_status_code(error: Exception) -> int | None:
    """Walk the error and its cause chain to find an HTTP status code."""
    current: BaseException | None = error
    for _ in range(5):
        if current is None:
            break
        code = getattr(current, "status_code", None)
        if isinstance(code, int) and 100 <= code < 600:
            return code
        code = getattr(current, "status", None)
        if isinstance(code, int) and 100 <= code < 600:
            return code
        nxt = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if nxt is None or nxt is current:
            break
        current = nxt
    return None


def _build_message(error: Exception) -> str:
    """Build a lowercased message string from the exception and its body."""
    parts = [str(error)]
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        err_obj = body.get("error")
        if isinstance(err_obj, dict):
            m = err_obj.get("message")
            if isinstance(m, str):
                parts.append(m)
            code = err_obj.get("code") or err_obj.get("type")
            if isinstance(code, str):
                parts.append(code)
        m = body.get("message")
        if isinstance(m, str):
            parts.append(m)
    return " ".join(p for p in parts if p).lower()


_RETRY_AFTER_TEXT_RE = re.compile(r"(?:try again in|retry after|please retry after)\s+([0-9]+(?:\.[0-9]+)?)\s*(m?s(?:ec)?|s|seconds?|minutes?|m)?")


def _extract_retry_after(error: Exception, msg: str) -> float | None:
    """Return the provider-supplied wait in seconds, or ``None``.

    Only positive, finite values are returned; a negative or unparseable
    ``Retry-After`` yields ``None`` so the caller substitutes its default.
    """
    headers = _extract_headers(error)
    if headers:
        raw = headers.get("retry-after") or headers.get("Retry-After")
        val = _coerce_positive_float(raw)
        if val is not None:
            return val

    match = _RETRY_AFTER_TEXT_RE.search(msg)
    if match:
        val = _coerce_positive_float(match.group(1))
        if val is not None:
            unit = (match.group(2) or "s").strip()
            if unit.startswith("m") and unit != "ms" and not unit.startswith("ms"):
                return val * 60.0
            if unit.startswith("ms"):
                return val / 1000.0
            return val
    return None


def _extract_headers(error: Exception) -> dict | None:
    current: BaseException | None = error
    for _ in range(5):
        if current is None:
            break
        headers = getattr(current, "headers", None)
        if isinstance(headers, dict):
            return {str(k).lower(): v for k, v in headers.items()}
        response = getattr(current, "response", None)
        resp_headers = getattr(response, "headers", None)
        if resp_headers is not None:
            try:
                return {str(k).lower(): v for k, v in dict(resp_headers).items()}
            except (TypeError, ValueError):
                pass
        nxt = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if nxt is None or nxt is current:
            break
        current = nxt
    return None


def _coerce_positive_float(raw: object) -> float | None:
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val <= 0 or val != val or val == float("inf"):
        return None
    return val


__all__ = [
    "FailoverReason",
    "RecoveryHint",
    "classify_llm_error",
    "provider_family_of",
]
