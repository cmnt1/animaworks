"""Activity-log integration for ephemeral runtime model fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.config.model_config import fallback_event_meta

if TYPE_CHECKING:
    from core.memory.activity import ActivityLogger
    from core.schemas import ModelConfig


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


__all__ = ["log_model_fallback"]
