from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.execution.base import BaseExecutor, StreamDisconnectedError
from core.execution.session_store import SessionRecord, SessionStore
from core.prompt.builder import BuildResult
from core.schemas import ModelConfig


def _make_agent(anima_dir: Path):
    config = ModelConfig(
        model="claude-sonnet-4-6",
        api_key="test-key",
        max_chains=2,
        context_threshold=0.5,
    )
    memory = MagicMock()
    memory.read_permissions.return_value = ""
    memory.anima_dir = anima_dir
    with (
        patch("core.agent.agent_core.ToolHandler"),
        patch("core.agent.agent_core.AgentCore._check_sdk", return_value=False),
        patch("core.agent.agent_core.AgentCore._init_tool_registry", return_value=[]),
        patch("core.agent.agent_core.AgentCore._discover_personal_tools", return_value={}),
        patch("core.agent.agent_core.AgentCore._create_executor") as create_executor,
    ):
        create_executor.return_value = MagicMock()
        from core.agent.agent_core import AgentCore

        agent = AgentCore(anima_dir, memory, config, MagicMock())
    return agent


def _build_result() -> MagicMock:
    result = MagicMock(spec=BuildResult)
    result.system_prompt = "system prompt"
    result.priming_section = ""
    return result


def _configure_stream(agent, mode: str, execute_streaming) -> None:
    executor = agent._executor
    executor.session_engine = {"s": "agent_sdk", "c": "codex", "d": "cursor", "x": "grok"}.get(mode)
    executor._anima_dir = agent.anima_dir
    executor.clear_session = BaseExecutor.clear_session.__get__(executor, type(executor))
    executor.execute_streaming = execute_streaming
    executor.supports_streaming = True


def _common_patches(mode: str):
    return (
        patch("core.agent.cycle.build_system_prompt", return_value=_build_result()),
        patch("core.agent.cycle.inject_shortterm", side_effect=lambda prompt, _shortterm: prompt),
        patch("core.agent.agent_core.AgentCore._resolve_execution_mode", return_value=mode),
        patch("core.agent.agent_core.AgentCore._preflight_size_check", return_value=("system prompt", "prompt")),
        patch(
            "core.agent.agent_core.AgentCore._load_stream_retry_config",
            return_value={"checkpoint_enabled": False, "retry_max": 2, "retry_delay_s": 0.0},
        ),
        patch("core.agent.cycle._save_prompt_log"),
        patch("core.agent.agent_core.AgentCore._run_priming", new_callable=AsyncMock, return_value=("", "")),
    )


@contextmanager
def _cycle_patches(mode: str, *extra):
    with ExitStack() as stack:
        for context in (*_common_patches(mode), *extra):
            stack.enter_context(context)
        yield


async def _done_stream(*args, **kwargs):
    yield {
        "type": "done",
        "full_text": "response",
        "result_message": None,
        "replied_to_from_transcript": set(),
        "tool_call_records": [],
        "force_chain": False,
    }


@pytest.mark.asyncio
async def test_stream_threshold_clears_grok_session(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    path = SessionStore.path_for("grok", tmp_path, "chat")
    SessionStore(path).write_text_record(SessionRecord("grok-session", 3), with_turn_count=True)
    _configure_stream(agent, "x", _done_stream)
    tracker = MagicMock(
        threshold_exceeded=True,
        usage_ratio=0.9,
        context_window=1000,
        threshold=0.8,
        _input_tokens=100,
    )

    with _cycle_patches("x", patch("core.agent.cycle.ContextTracker", return_value=tracker)):
        async for _event in agent.run_cycle_streaming("prompt", trigger="message:owner"):
            pass

    assert not path.exists()


@pytest.mark.asyncio
async def test_retry_first_attempt_clears_cursor_session(tmp_path: Path) -> None:
    agent = _make_agent(tmp_path)
    path = SessionStore.path_for("cursor", tmp_path, "chat")
    SessionStore(path).write_text_record(SessionRecord("cursor-session", 2), with_turn_count=True)
    attempts = 0

    async def fail_then_succeed(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise StreamDisconnectedError("stream disconnected", partial_text="")
        async for event in _done_stream(*args, **kwargs):
            yield event

    _configure_stream(agent, "d", fail_then_succeed)

    with _cycle_patches("d"):
        async for _event in agent.run_cycle_streaming("prompt", trigger="message:owner"):
            pass

    assert attempts == 2
    assert not path.exists()


@pytest.mark.parametrize("mode", ["g", "a"])
@pytest.mark.asyncio
async def test_retry_does_not_clear_grok_session_for_non_session_engines(tmp_path: Path, mode: str) -> None:
    agent = _make_agent(tmp_path)
    path = SessionStore.path_for("grok", tmp_path, "chat")
    SessionStore(path).write_text_record(SessionRecord("grok-session", 1), with_turn_count=True)
    attempts = 0

    async def fail_then_succeed(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise StreamDisconnectedError("stream disconnected", partial_text="")
        async for event in _done_stream(*args, **kwargs):
            yield event

    _configure_stream(agent, mode, fail_then_succeed)

    with _cycle_patches(mode):
        async for _event in agent.run_cycle_streaming("prompt", trigger="message:owner"):
            pass

    assert attempts == 2
    assert path.exists()
