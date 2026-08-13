"""Activity-log integration for ephemeral runtime model fallback."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

from core.config.model_config import fallback_event_meta, resolve_effective_model_config
from core.execution.error_classifier import classify_llm_error, classify_llm_error_message
from core.schemas import ModelConfig

if TYPE_CHECKING:
    from core.memory.activity import ActivityLogger

_T = TypeVar("_T")


def log_model_fallback(
    activity: ActivityLogger,
    primary_config: ModelConfig,
    effective_config: ModelConfig,
    *,
    channel: str,
    phase: str,
) -> dict[str, Any] | None:
    """Record a ``model_fallback`` event and return its metadata.

    Callers pass their existing :class:`ActivityLogger`; this helper only
    standardizes the event shape shared by chat and background paths.
    """
    raw_meta = fallback_event_meta(primary_config, effective_config)
    if raw_meta is None:
        return None
    meta: dict[str, Any] = {**raw_meta, "phase": phase}
    activity.log(
        "model_fallback",
        summary=(
            f"Model fallback: {meta.get('primary', primary_config.model)}"
            f" -> {meta.get('fallback', effective_config.model)}"
        ),
        channel=channel,
        meta=meta,
        safe=True,
    )
    return meta


async def run_with_model_fallback(
    run: Callable[[ModelConfig], Awaitable[_T]],
    *,
    activity: ActivityLogger,
    primary_config: ModelConfig,
    active_config: ModelConfig,
    channel: str,
) -> _T:
    """Run once, then re-resolve and retry once after a fallback-safe failure."""
    failure: Exception | None = None
    try:
        result = await run(active_config)
    except Exception as exc:
        failure = exc
        _reason, hint = classify_llm_error(exc)
        if not hint.fallback_ok:
            raise
    else:
        data = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
        if not isinstance(data, dict) or not (data.get("action") == "error" or data.get("reason")):
            return result
        _reason, hint = classify_llm_error_message(str(data.get("summary") or ""))
        if not hint.fallback_ok:
            return result

    retry_config = resolve_effective_model_config(primary_config)
    if all(
        getattr(retry_config, field, None) == getattr(active_config, field, None)
        for field in ("model", "execution_mode", "resolved_mode", "credential")
    ):
        if failure is not None:
            raise failure
        return result

    log_model_fallback(
        activity,
        primary_config,
        retry_config,
        channel=channel,
        phase="runtime_retry",
    )
    return await run(retry_config)


__all__ = ["log_model_fallback", "run_with_model_fallback"]
