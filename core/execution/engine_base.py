from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared low-level helpers for CLI-backed execution engines."""

import logging
from typing import Any

from core.execution.events import stream_event
from core.llm.guard.error_classifier import (
    FailoverReason,
    classify_llm_error_message,
    guard_key,
    litellm_realm_of,
    provider_family_of,
)
from core.llm.guard.rate_guard import get_rate_guard

logger = logging.getLogger(__name__)

ENGINE_REALMS: dict[str, str] = {"C": "codex", "D": "cursor", "G": "gemini", "X": "grok"}
ENGINE_FAMILIES: dict[str, str] = {"S": "anthropic", "C": "openai", "G": "google", "X": "grok"}
GRACEFUL_KILL_WAIT_SECONDS: float = 3.0


def engine_guard_key(mode: str, model: str, *, mode_s_auth: str | None = None) -> str:
    """Return the shared rate-guard key for a resolved execution mode."""
    realm = ENGINE_REALMS.get(mode)
    if mode == "S":
        realm = mode_s_auth or "max"
    if realm is None:
        realm = litellm_realm_of(model)
    family = ENGINE_FAMILIES.get(mode) or provider_family_of(model)
    return guard_key(family, realm)


def engine_error_metadata(
    message: str,
    *,
    mode: str,
    model: str,
    always_terminal: bool,
) -> dict[str, Any]:
    """Classify engine errors, report quota blocks, and return event metadata."""
    reason, hint = classify_llm_error_message(message)
    if reason in {
        FailoverReason.RATE_LIMIT,
        FailoverReason.OVERLOADED,
        FailoverReason.QUOTA_EXHAUSTED,
    }:
        try:
            guard = get_rate_guard()
            config = guard.config
            block_seconds = (
                config.quota_block_seconds if reason is FailoverReason.QUOTA_EXHAUSTED else config.default_block_seconds
            )
            guard.report_block(
                engine_guard_key(mode, model),
                block_seconds,
                reason.value,
                reset_in_s=hint.reset_in_s,
            )
        except Exception:
            logger.debug("Failed to report engine error to rate guard", exc_info=True)

    if always_terminal or hint.is_terminal or not hint.retryable:
        return {"terminal": True, "reason": reason.value}
    return {}


def engine_error_event(message: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Build the normalized terminal error event emitted by CLI engines."""
    return stream_event("error", message=message, **metadata)
