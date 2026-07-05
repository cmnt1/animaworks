# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.execution.error_classifier — classification matrix."""

from __future__ import annotations

import pytest

from core.execution.error_classifier import (
    FailoverReason,
    classify_llm_error,
    guard_key,
    litellm_realm_of,
    provider_family_of,
)


class _ApiError(Exception):
    """Provider-style exception carrying status_code / headers / body."""

    def __init__(
        self,
        message: str = "",
        *,
        status_code: int | None = None,
        headers: dict | None = None,
        body: dict | None = None,
    ) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code
        if headers is not None:
            self.headers = headers
        if body is not None:
            self.body = body


class RateLimitError(Exception):
    """Mimics an SDK RateLimitError with no explicit status_code."""


class ReadTimeout(Exception):
    """Mimics an httpx transport timeout by type name."""


# ── provider family ──────────────────────────────────────────────────────────


class TestProviderFamily:
    def test_anthropic_variants(self) -> None:
        assert provider_family_of("anthropic/claude-sonnet-4-6") == "anthropic"
        assert provider_family_of("bedrock/jp.anthropic.claude-sonnet-4-6") == "anthropic"
        assert provider_family_of("vertex_ai/claude-sonnet-4-6") == "anthropic"
        assert provider_family_of("claude-sonnet-4-6") == "anthropic"

    def test_openai_variants(self) -> None:
        assert provider_family_of("openai/gpt-4.1") == "openai"
        assert provider_family_of("gpt-4.1") == "openai"
        assert provider_family_of("codex/gpt-5.4-mini") == "openai"

    def test_google_variants(self) -> None:
        assert provider_family_of("google/gemini-2.0") == "google"
        assert provider_family_of("gemini/gemini-2.0-flash") == "google"

    def test_other_prefix_and_empty(self) -> None:
        assert provider_family_of("ollama/qwen2.5") == "ollama"
        assert provider_family_of("") == "unknown"


class TestGuardKey:
    def test_family_realm_composition(self) -> None:
        assert guard_key("anthropic", "api") == "anthropic:api"
        assert guard_key("anthropic", "max") == "anthropic:max"
        assert guard_key("openai", "codex") == "openai:codex"

    def test_api_and_mode_s_realms_are_distinct(self) -> None:
        # The whole point of the realm split: same family, different keys.
        assert guard_key("anthropic", "api") != guard_key("anthropic", "max")


class TestLitellmRealm:
    def test_bedrock_prefixes(self) -> None:
        assert litellm_realm_of("bedrock/jp.anthropic.claude-sonnet-4-6") == "bedrock"
        assert litellm_realm_of("bedrock-anthropic.claude-sonnet-4-6") == "bedrock"

    def test_vertex_prefix(self) -> None:
        assert litellm_realm_of("vertex_ai/claude-sonnet-4-6") == "vertex"

    def test_default_api_realm(self) -> None:
        assert litellm_realm_of("anthropic/claude-sonnet-4-6") == "api"
        assert litellm_realm_of("openai/gpt-4.1") == "api"
        assert litellm_realm_of("") == "api"


# ── classification matrix (12 reasons) ──────────────────────────────────────


class TestClassificationMatrix:
    def test_auth_401(self) -> None:
        reason, hint = classify_llm_error(_ApiError("nope", status_code=401))
        assert reason is FailoverReason.AUTH
        assert hint.retryable is False

    def test_auth_403(self) -> None:
        reason, _ = classify_llm_error(_ApiError("forbidden", status_code=403))
        assert reason is FailoverReason.AUTH

    def test_billing_402(self) -> None:
        reason, hint = classify_llm_error(_ApiError("payment required", status_code=402))
        assert reason is FailoverReason.BILLING
        assert hint.retryable is False

    def test_billing_message(self) -> None:
        reason, _ = classify_llm_error(_ApiError("Your credit balance is too low"))
        assert reason is FailoverReason.BILLING

    def test_billing_403_with_billing_body(self) -> None:
        reason, _ = classify_llm_error(_ApiError("insufficient credits", status_code=403))
        assert reason is FailoverReason.BILLING

    def test_rate_limit_429(self) -> None:
        reason, _ = classify_llm_error(_ApiError("Too Many Requests", status_code=429))
        assert reason is FailoverReason.RATE_LIMIT

    def test_rate_limit_error_type_without_status(self) -> None:
        reason, _ = classify_llm_error(RateLimitError("rate limited"))
        assert reason is FailoverReason.RATE_LIMIT

    def test_overloaded_529(self) -> None:
        reason, _ = classify_llm_error(_ApiError("overloaded", status_code=529))
        assert reason is FailoverReason.OVERLOADED

    def test_overloaded_503(self) -> None:
        reason, _ = classify_llm_error(_ApiError("service unavailable", status_code=503))
        assert reason is FailoverReason.OVERLOADED

    def test_context_overflow_400(self) -> None:
        reason, _ = classify_llm_error(_ApiError("prompt is too long: 250000 tokens", status_code=400))
        assert reason is FailoverReason.CONTEXT_OVERFLOW

    def test_payload_too_large_413(self) -> None:
        reason, _ = classify_llm_error(_ApiError("entity too large", status_code=413))
        assert reason is FailoverReason.PAYLOAD_TOO_LARGE

    def test_content_policy_message_no_status(self) -> None:
        reason, hint = classify_llm_error(_ApiError("This request violates our usage policies"))
        assert reason is FailoverReason.CONTENT_POLICY
        assert hint.is_terminal is True
        assert hint.fallback_ok is False

    def test_content_policy_beats_400_status(self) -> None:
        reason, _ = classify_llm_error(_ApiError("prompt was flagged by our safety system", status_code=400))
        assert reason is FailoverReason.CONTENT_POLICY

    def test_timeout_type(self) -> None:
        reason, _ = classify_llm_error(ReadTimeout("read timed out"))
        assert reason is FailoverReason.TIMEOUT

    def test_timeout_builtin(self) -> None:
        reason, _ = classify_llm_error(TimeoutError("timed out"))
        assert reason is FailoverReason.TIMEOUT

    def test_network_connection_error(self) -> None:
        reason, _ = classify_llm_error(ConnectionError("connection reset by peer"))
        assert reason is FailoverReason.NETWORK

    def test_server_error_500(self) -> None:
        reason, hint = classify_llm_error(_ApiError("internal error", status_code=500))
        assert reason is FailoverReason.SERVER_ERROR
        assert hint.retryable is True

    def test_server_error_502(self) -> None:
        reason, _ = classify_llm_error(_ApiError("bad gateway", status_code=502))
        assert reason is FailoverReason.SERVER_ERROR

    def test_invalid_request_generic_400(self) -> None:
        reason, hint = classify_llm_error(_ApiError("bad request", status_code=400))
        assert reason is FailoverReason.INVALID_REQUEST
        assert hint.is_terminal is True
        assert hint.fallback_ok is True

    def test_invalid_request_404(self) -> None:
        reason, _ = classify_llm_error(_ApiError("not found", status_code=404))
        assert reason is FailoverReason.INVALID_REQUEST

    def test_unknown_degrades_to_current_behavior(self) -> None:
        reason, hint = classify_llm_error(ValueError("something weird"))
        assert reason is FailoverReason.UNKNOWN
        assert hint.retryable is True
        assert hint.fallback_ok is True
        assert hint.is_terminal is False


# ── disambiguation rules ─────────────────────────────────────────────────────


class TestDisambiguation:
    def test_429_rate_vs_overloaded(self) -> None:
        rate, _ = classify_llm_error(_ApiError("rate limit exceeded", status_code=429))
        overloaded, _ = classify_llm_error(_ApiError("server is temporarily overloaded", status_code=429))
        assert rate is FailoverReason.RATE_LIMIT
        assert overloaded is FailoverReason.OVERLOADED

    def test_400_context_vs_invalid_max_tokens(self) -> None:
        # A 400 that rejects max_tokens contains the literal "max_tokens" (a
        # context-overflow token) but must classify as invalid_request.
        invalid, _ = classify_llm_error(
            _ApiError(
                "Unsupported parameter: 'max_tokens' is not supported with this model.",
                status_code=400,
            )
        )
        context, _ = classify_llm_error(_ApiError("context length exceeded", status_code=400))
        assert invalid is FailoverReason.INVALID_REQUEST
        assert context is FailoverReason.CONTEXT_OVERFLOW

    def test_5xx_request_validation_is_invalid_request(self) -> None:
        reason, hint = classify_llm_error(_ApiError("unknown parameter: foo", status_code=502))
        assert reason is FailoverReason.INVALID_REQUEST
        assert hint.retryable is False


# ── Retry-After extraction and clamp ─────────────────────────────────────────


class TestRetryAfter:
    def test_header_retry_after(self) -> None:
        _, hint = classify_llm_error(_ApiError("rate", status_code=429, headers={"retry-after": "30"}))
        assert hint.backoff_s == 30.0

    def test_negative_retry_after_is_none(self) -> None:
        _, hint = classify_llm_error(_ApiError("rate", status_code=429, headers={"retry-after": "-5"}))
        assert hint.backoff_s is None

    def test_text_retry_after_seconds(self) -> None:
        _, hint = classify_llm_error(_ApiError("Rate limited. Please retry after 12 seconds"))
        assert hint.backoff_s == 12.0

    def test_text_retry_after_minutes(self) -> None:
        _, hint = classify_llm_error(_ApiError("rate limit; try again in 2 minutes"))
        assert hint.backoff_s == 120.0


# ── classifier never raises ──────────────────────────────────────────────────


class _Explosive(Exception):
    @property
    def status_code(self):  # noqa: ANN201
        raise RuntimeError("boom")


def test_classifier_swallows_internal_errors() -> None:
    reason, hint = classify_llm_error(_Explosive("kaboom"))
    assert reason is FailoverReason.UNKNOWN
    assert hint.retryable is True


@pytest.mark.parametrize("reason", list(FailoverReason))
def test_every_reason_has_hint(reason: FailoverReason) -> None:
    # Every enum member must be reachable via a hint template (guards the
    # 12-member contract).
    from core.execution.error_classifier import _HINTS

    assert reason in _HINTS
