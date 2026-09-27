"""Blocking cycle failures route through configured model fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.execution.base import BaseExecutor, ExecutionResult
from core.prompt.builder import BuildResult
from core.schemas import ModelConfig
from tests.unit.core.test_agent import _make_agent


class _SequenceExecutor(BaseExecutor):
    def __init__(self, anima_dir: Path, config: ModelConfig, result: ExecutionResult) -> None:
        self._anima_dir = anima_dir
        self._model_config = config
        self.result = result

    def _load_hb_soft_timeout(self) -> int:
        return 300

    async def execute(self, **kwargs) -> ExecutionResult:
        return self.result


async def test_blocking_error_runs_fallback_model(tmp_path: Path):
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    primary_config = ModelConfig(
        model="cursor/primary",
        resolved_mode="D",
        fallback_models=["a:openai/fallback"],
    )
    agent = _make_agent(anima_dir, model=primary_config.model, resolved_mode="D")
    agent.model_config = primary_config
    agent._run_priming = AsyncMock(return_value=("", ""))
    agent._preflight_size_check = AsyncMock(return_value=("system", "prompt"))
    agent._load_context_window_overrides = lambda: {}
    agent._fit_prompt_to_context_window = lambda system_prompt, prompt, *_args, **_kwargs: system_prompt
    agent._executor = _SequenceExecutor(
        anima_dir,
        primary_config,
        ExecutionResult(text="rate limited", error=True, reason="rate_limit"),
    )

    fallback_config = ModelConfig(model="openai/fallback", resolved_mode="A")
    fallback_executor = _SequenceExecutor(anima_dir, fallback_config, ExecutionResult(text="fallback worked"))
    agent._create_executor = MagicMock(return_value=fallback_executor)

    with (
        patch("core.agent.cycle.build_system_prompt", return_value=BuildResult(system_prompt="system")),
        patch("core.agent.cycle._save_prompt_log"),
        patch("core.agent.cycle._save_prompt_log_end"),
        patch("core.agent.cycle._log_session_token_usage"),
        patch("core.execution.fallback_activity.preflight_fallback_config", return_value=primary_config),
        patch("core.execution.fallback_activity.runtime_fallback_config", return_value=fallback_config) as runtime,
    ):
        result = await agent.run_cycle("prompt", trigger="heartbeat")

    assert result.action == "responded"
    assert result.summary == "fallback worked"
    runtime.assert_called_once()
    assert runtime.call_args.kwargs["reason"] == "rate_limit"
    agent._create_executor.assert_called_once_with(fallback_config)
