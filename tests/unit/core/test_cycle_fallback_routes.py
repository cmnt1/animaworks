"""Central run_cycle fallback wiring: preflight + one-shot runtime retry.

These cover the shared helpers every execution route (chat, task_exec,
declaration probe, cron, heartbeat, inbox, consolidation) now goes through.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from core._agent_cycle import CycleMixin
from core.execution.fallback_activity import preflight_fallback_config, runtime_fallback_config
from core.schemas import CycleResult, ModelConfig


def _configs() -> tuple[ModelConfig, ModelConfig]:
    primary = ModelConfig(
        model="codex/gpt-5.6-sol",
        execution_mode="c",
        resolved_mode="C",
        fallback_models=["x:grok/grok-4.5", "s:claude-sonnet-5"],
    )
    fallback = primary.model_copy(
        update={"model": "grok/grok-4.5", "execution_mode": "x", "resolved_mode": "X"},
    )
    return primary, fallback


def _meta() -> dict[str, object]:
    return {
        "primary": "codex/gpt-5.6-sol",
        "fallback": "x:grok/grok-4.5",
        "reason": "rate_guard_blocked:quota_exhausted",
        "remaining": 1799.0,
    }


class _Cycle(CycleMixin):
    """Minimal host exposing only what the fallback helpers touch."""

    def __init__(self, model_config: ModelConfig, anima_dir: Path) -> None:
        self.model_config = model_config
        self.anima_dir = anima_dir


def test_preflight_swaps_blocked_primary(tmp_path: Path) -> None:
    primary, fallback = _configs()
    with (
        patch("core.execution.fallback_activity.resolve_effective_model_config", return_value=fallback),
        patch("core.execution.fallback_activity.fallback_event_meta", return_value=_meta()),
    ):
        assert preflight_fallback_config(tmp_path, primary, channel="task") is fallback


def test_preflight_noop_without_fallback_models(tmp_path: Path) -> None:
    plain = ModelConfig(model="codex/gpt-5.6-sol", execution_mode="c", resolved_mode="C")
    assert preflight_fallback_config(tmp_path, plain, channel="task") is plain


def test_preflight_fails_open(tmp_path: Path) -> None:
    primary, _ = _configs()
    with patch(
        "core.execution.fallback_activity.resolve_effective_model_config",
        side_effect=RuntimeError("guard unreadable"),
    ):
        assert preflight_fallback_config(tmp_path, primary, channel="task") is primary


def test_runtime_fallback_on_quota_error(tmp_path: Path) -> None:
    primary, fallback = _configs()
    with (
        patch("core.execution.fallback_activity.resolve_effective_model_config", return_value=fallback),
        patch("core.execution.fallback_activity.fallback_event_meta", return_value=_meta()),
    ):
        swap = runtime_fallback_config(
            tmp_path,
            primary,
            primary,
            error_text="You've hit your usage limit.",
            reason="quota_exhausted",
            channel="task",
        )
    assert swap is fallback


def test_runtime_fallback_declines_non_fallback_error(tmp_path: Path) -> None:
    primary, fallback = _configs()
    with patch("core.execution.fallback_activity.resolve_effective_model_config", return_value=fallback):
        assert (
            runtime_fallback_config(
                tmp_path,
                primary,
                primary,
                error_text="This request violates our usage policies",
                reason="",
                channel="task",
            )
            is None
        )


def test_runtime_fallback_declines_when_same_config(tmp_path: Path) -> None:
    primary, _ = _configs()
    with patch("core.execution.fallback_activity.resolve_effective_model_config", return_value=primary):
        assert (
            runtime_fallback_config(
                tmp_path,
                primary,
                primary,
                error_text="usage limit exceeded",
                reason="quota_exhausted",
                channel="task",
            )
            is None
        )


def test_cycle_preflight_applies_to_routes_without_override(tmp_path: Path) -> None:
    primary, fallback = _configs()
    cycle = _Cycle(primary, tmp_path)
    with patch("core.execution.fallback_activity.preflight_fallback_config", return_value=fallback):
        base, override = cycle._cycle_preflight_config(None, "task:gh-123")
    assert base is primary
    assert override is fallback  # task_exec must run on the fallback, not the blocked primary


def test_cycle_preflight_keeps_cached_executor_when_unblocked(tmp_path: Path) -> None:
    primary, _ = _configs()
    cycle = _Cycle(primary, tmp_path)
    with patch("core.execution.fallback_activity.preflight_fallback_config", return_value=primary):
        base, override = cycle._cycle_preflight_config(None, "task:gh-123")
    assert base is primary
    assert override is None


def test_cycle_runtime_fallback_from_error_result(tmp_path: Path) -> None:
    primary, fallback = _configs()
    cycle = _Cycle(primary, tmp_path)
    error = CycleResult(
        trigger="task:gh-123",
        action="error",
        summary="You've hit your usage limit.",
        reason="quota_exhausted",
    )
    with patch("core.execution.fallback_activity.runtime_fallback_config", return_value=fallback) as swap:
        assert cycle._cycle_runtime_fallback(error, primary, None, "task:gh-123") is fallback
    assert swap.call_args.kwargs["channel"] == "task"


def test_cycle_runtime_fallback_skips_successful_result(tmp_path: Path) -> None:
    primary, _ = _configs()
    cycle = _Cycle(primary, tmp_path)
    ok = CycleResult(trigger="task:gh-123", action="responded", summary="done")
    assert cycle._cycle_runtime_fallback(ok, primary, None, "task:gh-123") is None
