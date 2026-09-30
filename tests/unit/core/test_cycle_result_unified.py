"""Common blocking result handling and session handoff across execution engines."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.execution.base import BaseExecutor, ExecutionResult
from core.memory.conversation.shortterm import SessionState
from core.prompt.builder import BuildResult
from core.schemas import ModelConfig
from tests.unit.core.test_agent import _make_agent


class StubExecutor(BaseExecutor):
    """Small executor stub exposing the shared cycle contract."""

    def __init__(
        self,
        anima_dir: Path,
        mode: str,
        *,
        result: ExecutionResult | None = None,
        engine: str | None = None,
        force_threshold: bool = False,
        saves_threshold_shortterm: bool = False,
    ) -> None:
        self._anima_dir = anima_dir
        self._model_config = ModelConfig(model="test-model", resolved_mode=mode.upper())
        self.session_engine = engine
        self.saves_threshold_shortterm = saves_threshold_shortterm
        self.result = result or ExecutionResult(text="ok")
        self.force_threshold_on_execute = force_threshold
        self.execute_kwargs: dict = {}
        self.stream_chunk: dict | None = None

    def _load_hb_soft_timeout(self) -> int:
        return 300

    async def execute(self, **kwargs) -> ExecutionResult:
        self.execute_kwargs = kwargs
        tracker = kwargs["tracker"]
        if self.force_threshold_on_execute:
            tracker.force_threshold()
        shortterm = kwargs.get("shortterm")
        if self.saves_threshold_shortterm and shortterm is not None:
            shortterm.save(
                SessionState(
                    trigger=kwargs["trigger"],
                    original_prompt=kwargs["prompt"],
                    accumulated_response="saved by executor",
                )
            )
        return self.result

    async def execute_streaming(self, *args, **kwargs):
        assert self.stream_chunk is not None
        yield self.stream_chunk


@pytest.fixture
def cycle_agent(tmp_path: Path, monkeypatch):
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    agent = _make_agent(anima_dir, model="test-model", resolved_mode="D")
    agent._run_priming = AsyncMock(return_value=("", ""))
    agent._preflight_size_check = AsyncMock(return_value=("system", "prompt"))
    agent._load_context_window_overrides = lambda: {}
    agent._load_stream_retry_config = lambda: {
        "checkpoint_enabled": False,
        "retry_max": 0,
        "retry_delay_s": 0,
    }
    agent._fit_prompt_to_context_window = lambda system_prompt, prompt, *_args, **_kwargs: system_prompt
    monkeypatch.setattr(
        "core.agent.priming.build_system_prompt", lambda *args, **kwargs: BuildResult(system_prompt="system")
    )
    monkeypatch.setattr("core.agent.cycle._save_prompt_log", MagicMock())
    monkeypatch.setattr("core.agent.cycle._save_prompt_log_end", MagicMock())
    monkeypatch.setattr("core.agent.cycle._log_session_token_usage", MagicMock())
    monkeypatch.setattr("core.memory.conversation.memory.ConversationMemory", lambda *args, **kwargs: None)
    return agent, anima_dir


@pytest.mark.parametrize("mode", ["d", "g", "a", "x", "c", "s"])
async def test_blocking_errors_are_normalized_for_every_engine(cycle_agent, mode):
    agent, anima_dir = cycle_agent
    executor = StubExecutor(
        anima_dir,
        mode,
        result=ExecutionResult(text="provider failed", error=True, reason="rate_limit"),
    )
    agent._executor = executor
    agent.model_config.resolved_mode = mode.upper()

    result = await agent._run_cycle_inner_scoped("prompt", "heartbeat")

    assert result.action == "error"
    assert result.stop_kind == "stream_error"
    assert result.reason == result.error_category == "rate_limit"


@pytest.mark.parametrize("mode", ["d", "g", "a", "x", "c", "s"])
async def test_success_result_and_preflight_are_common_to_every_engine(cycle_agent, mode):
    agent, anima_dir = cycle_agent
    executor = StubExecutor(anima_dir, mode, result=ExecutionResult(text="ok"))
    agent._executor = executor
    agent.model_config.resolved_mode = mode.upper()

    result = await agent._run_cycle_inner_scoped("prompt", "heartbeat")

    assert result.action == "responded"
    assert result.reason == ""
    agent._preflight_size_check.assert_awaited_once()


async def test_error_category_falls_back_to_message_classification(cycle_agent):
    from core.llm.guard.error_classifier import classify_llm_error_message

    agent, anima_dir = cycle_agent
    text = "[Cursor Agent Error: 429 Too Many Requests]"
    executor = StubExecutor(
        anima_dir,
        "d",
        result=ExecutionResult(text=text, error=True, reason=""),
    )
    agent._executor = executor
    agent.model_config.resolved_mode = "D"

    result = await agent._run_cycle_inner_scoped("prompt", "heartbeat")
    expected, _hint = classify_llm_error_message(text)

    assert result.error_category == expected.value
    assert result.reason == expected.value


async def test_blocking_x_threshold_saves_handoff_and_removes_grok_session(cycle_agent):
    from core.execution.session.session_store import SessionStore

    agent, anima_dir = cycle_agent
    executor = StubExecutor(anima_dir, "x", engine="grok", force_threshold=True)
    agent._executor = executor
    agent.model_config.resolved_mode = "X"
    session_path = SessionStore.path_for("grok", anima_dir, "chat")
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text("old-session", encoding="utf-8")

    await agent._run_cycle_inner_scoped("prompt", "chat")

    assert not session_path.exists()
    handoff_path = anima_dir / "shortterm" / "chat" / "session_state.json"
    assert json.loads(handoff_path.read_text(encoding="utf-8"))["original_prompt"] == "prompt"


@pytest.mark.parametrize(("mode", "engine"), [("d", "cursor"), ("x", "grok")])
@pytest.mark.parametrize("streaming", [False, True])
async def test_rotation_pending_saves_handoff_without_clearing_engine_session(
    cycle_agent,
    mode,
    engine,
    streaming,
):
    from core.execution.session.session_store import SessionStore

    agent, anima_dir = cycle_agent
    result_message = SimpleNamespace(session_id="current-session", num_turns=4)
    executor = StubExecutor(
        anima_dir,
        mode,
        engine=engine,
        result=ExecutionResult(
            text="response body",
            result_message=result_message,
            session_rotation_pending=True,
        ),
    )
    agent._executor = executor
    agent.model_config.resolved_mode = mode.upper()
    session_path = SessionStore.path_for(engine, anima_dir, "chat")
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text("preserve-session", encoding="utf-8")

    if streaming:
        executor.stream_chunk = {
            "type": "done",
            "full_text": "response body",
            "result_message": result_message,
            "tool_call_records": [],
            "session_rotation_pending": True,
        }
        chunks = [chunk async for chunk in agent._run_cycle_streaming_inner("prompt", trigger="chat")]
        assert chunks[-1]["cycle_result"]["action"] == "responded"
    else:
        await agent._run_cycle_inner_scoped("prompt", "chat")

    assert session_path.read_text(encoding="utf-8") == "preserve-session"
    state = json.loads((anima_dir / "shortterm" / "chat" / "session_state.json").read_text(encoding="utf-8"))
    assert state["accumulated_response"] == "response body"
    assert state["session_id"] == "current-session"
    assert state["turn_count"] == 4


async def test_litellm_owned_threshold_handoff_is_not_cleared_or_overwritten(cycle_agent):
    agent, anima_dir = cycle_agent
    executor = StubExecutor(
        anima_dir,
        "a",
        force_threshold=True,
        saves_threshold_shortterm=True,
    )
    agent._executor = executor
    agent.model_config.resolved_mode = "A"

    await agent._run_cycle_inner_scoped("prompt", "chat")

    assert executor.execute_kwargs["shortterm"] is not None
    state_path = anima_dir / "shortterm" / "chat" / "session_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["accumulated_response"] == "saved by executor"
