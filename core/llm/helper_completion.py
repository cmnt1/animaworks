from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""One-shot completion helpers that apply a resolved helper-model policy."""

import logging
from pathlib import Path

from core.config.helper_models import ResolvedHelperModel, resolve_helper_model

logger = logging.getLogger(__name__)


def _candidates(
    resolved: ResolvedHelperModel,
    *,
    model_override: str | None = None,
    credential_override: str | None = None,
) -> list[tuple[str, str]]:
    primary_model = model_override or resolved.model
    primary_credential = credential_override
    if primary_credential is None and primary_model == resolved.model:
        primary_credential = resolved.credential

    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for model, credential in [
        (primary_model, primary_credential),
        *((fallback.model, fallback.credential) for fallback in resolved.fallbacks),
    ]:
        normalized_model = str(model or "").strip()
        if not normalized_model:
            continue
        key = (normalized_model, str(credential or ""))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(key)
    return candidates


def _resolved(
    role: str,
    anima_dir: Path | None,
    resolved: ResolvedHelperModel | None,
) -> ResolvedHelperModel:
    return resolved or resolve_helper_model(role, anima_dir)


async def one_shot_helper_completion(
    prompt: str,
    *,
    role: str,
    anima_dir: Path | None = None,
    resolved: ResolvedHelperModel | None = None,
    system_prompt: str = "",
    max_tokens: int = 2048,
    model_override: str | None = None,
    credential_override: str | None = None,
    structured_output: bool = False,
    temperature: float | None = None,
    timeout: float | None = None,  # noqa: ASYNC109 -- forwards one-shot request timeout
    llm_extra: dict[str, object] | None = None,
) -> str | None:
    """Run a helper call through its registry-selected model and explicit fallbacks."""
    helper = _resolved(role, anima_dir, resolved)
    output_tokens = helper.max_output_tokens or max_tokens
    from core.llm.oneshot import one_shot_completion

    for model, credential in _candidates(
        helper,
        model_override=model_override,
        credential_override=credential_override,
    ):
        try:
            result = await one_shot_completion(
                prompt,
                system_prompt=system_prompt,
                model=model,
                credential=credential,
                max_tokens=output_tokens,
                structured_output=structured_output,
                temperature=temperature,
                timeout=timeout,
                llm_extra=llm_extra,
                allow_agent_sdk_fallback=helper.allow_agent_sdk_fallback,
            )
        except Exception as exc:
            logger.debug("Helper one-shot call failed role=%s model=%s error=%s", role, model, type(exc).__name__)
            continue
        if result and result.strip():
            return result
    return None


def one_shot_helper_completion_sync(
    prompt: str,
    *,
    role: str,
    anima_dir: Path | None = None,
    resolved: ResolvedHelperModel | None = None,
    system_prompt: str = "",
    max_tokens: int = 2048,
    model_override: str | None = None,
    credential_override: str | None = None,
    structured_output: bool = False,
    temperature: float | None = None,
    timeout: float | None = None,
    llm_extra: dict[str, object] | None = None,
) -> str | None:
    """Synchronous helper variant for existing synchronous memory pipelines."""
    helper = _resolved(role, anima_dir, resolved)
    output_tokens = helper.max_output_tokens or max_tokens
    from core.llm.oneshot import one_shot_completion_sync

    for model, credential in _candidates(
        helper,
        model_override=model_override,
        credential_override=credential_override,
    ):
        try:
            result = one_shot_completion_sync(
                prompt,
                system_prompt=system_prompt,
                model=model,
                credential=credential,
                max_tokens=output_tokens,
                structured_output=structured_output,
                temperature=temperature,
                timeout=timeout,
                llm_extra=llm_extra,
                allow_agent_sdk_fallback=helper.allow_agent_sdk_fallback,
            )
        except Exception as exc:
            logger.debug("Helper one-shot call failed role=%s model=%s error=%s", role, model, type(exc).__name__)
            continue
        if result and result.strip():
            return result
    return None


__all__ = ["one_shot_helper_completion", "one_shot_helper_completion_sync"]
