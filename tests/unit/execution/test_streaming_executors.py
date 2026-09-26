"""Tests for BaseExecutor and LiteLLM streaming behavior.

Covers StreamDisconnectedError shared behavior, BaseExecutor default
then LiteLLMExecutor (Mode A2) token-level and iteration-level streaming.
All LLM calls are mocked — no real API calls are made.
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.execution.base import (
    BaseExecutor,
    ExecutionResult,
    StreamDisconnectedError,
)
from core.execution.reminder import msg_tool_loop_warning
from core.memory.conversation.shortterm import ShortTermMemory
from core.prompt.context import ContextTracker
from core.schemas import ModelConfig

# ── Helpers ──────────────────────────────────────────────────


class ConcreteExecutor(BaseExecutor):
    """Minimal concrete subclass for testing BaseExecutor streaming defaults."""

    async def execute(
        self,
        prompt: str,
        system_prompt: str = "",
        tracker: ContextTracker | None = None,
        shortterm: ShortTermMemory | None = None,
        trigger: str = "",
        images: list[dict[str, Any]] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        thread_id: str = "default",
    ) -> ExecutionResult:
        return ExecutionResult(text=f"response: {prompt}")


async def _collect_events(async_gen) -> list[dict[str, Any]]:
    """Collect all events from an async generator into a list."""
    events = []
    async for event in async_gen:
        events.append(event)
    return events


# ── StreamDisconnectedError ───────────────────────────────────


class TestStreamDisconnectedErrorAttributes:
    """StreamDisconnectedError has partial_text attribute."""

    def test_carries_partial_text(self) -> None:
        err = StreamDisconnectedError(
            "stream lost",
            partial_text="accumulated output",
        )
        assert err.partial_text == "accumulated output"
        assert str(err) == "stream lost"

    def test_is_exception(self) -> None:
        err = StreamDisconnectedError("test")
        assert isinstance(err, Exception)


class TestStreamDisconnectedErrorDefaultPartial:
    """Default partial_text is an empty string."""

    def test_default_empty_partial_text(self) -> None:
        err = StreamDisconnectedError("disconnected")
        assert err.partial_text == ""

    def test_default_message(self) -> None:
        err = StreamDisconnectedError()
        assert str(err) == "Stream disconnected"
        assert err.partial_text == ""


class TestStreamDisconnectedBackwardCompatImport:
    """Importing StreamDisconnectedError from agent_sdk still works."""

    def test_import_from_agent_sdk(self) -> None:
        from core.execution.engines.claude.agent_sdk import StreamDisconnectedError as SDE

        assert SDE is StreamDisconnectedError

    def test_in_agent_sdk_all(self) -> None:
        from core.execution.engines.claude import agent_sdk

        assert "StreamDisconnectedError" in agent_sdk.__all__


# ── BaseExecutor streaming defaults ───────────────────────────


class TestBaseSupportsStreamingDefaultTrue:
    """BaseExecutor.supports_streaming returns True now."""

    def test_supports_streaming_is_true(self, tmp_path: Path) -> None:
        config = ModelConfig(model="test-model")
        executor = ConcreteExecutor(model_config=config, anima_dir=tmp_path)
        assert executor.supports_streaming is True


class TestBaseDefaultStreamingYieldsTextAndDone:
    """Default execute_streaming yields text_delta + done from execute() result."""

    @pytest.mark.asyncio
    async def test_default_streaming_events(self, tmp_path: Path) -> None:
        config = ModelConfig(model="test-model")
        executor = ConcreteExecutor(model_config=config, anima_dir=tmp_path)
        tracker = MagicMock(spec=ContextTracker)

        events = await _collect_events(
            executor.execute_streaming(
                system_prompt="sys",
                prompt="hello",
                tracker=tracker,
            )
        )

        assert len(events) == 2

        # First event: text_delta with the full response
        assert events[0]["type"] == "text_delta"
        assert events[0]["text"] == "response: hello"

        # Second event: done with full_text and result_message
        assert events[1]["type"] == "done"
        assert events[1]["full_text"] == "response: hello"
        assert events[1]["result_message"] is None


# ── A2 LiteLLMExecutor streaming ─────────────────────────────


class FakeStreamChunk:
    """Simulate a single streaming chunk from litellm.acompletion(stream=True)."""

    def __init__(
        self,
        text: str | None = None,
        tool_calls: list[Any] | None = None,
        finish_reason: str | None = None,
        usage: Any | None = None,
    ) -> None:
        delta = MagicMock()
        delta.content = text
        delta.tool_calls = tool_calls
        delta.reasoning_content = None

        choice = MagicMock()
        choice.delta = delta
        choice.finish_reason = finish_reason

        self.choices = [choice]
        self.usage = usage


class FakeUsage:
    """Simulate a usage object from litellm streaming."""

    def __init__(
        self,
        prompt_tokens: int = 100,
        completion_tokens: int = 50,
    ) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class FakeDelta:
    """Simulate a tool_call delta fragment."""

    def __init__(
        self,
        index: int,
        id: str | None = None,
        name: str | None = None,
        arguments: str = "",
    ) -> None:
        self.index = index
        self.id = id
        func = MagicMock()
        func.name = name
        func.arguments = arguments
        self.function = func


async def _fake_async_stream(chunks: list[Any]):
    """Create an async iterator from a list of chunks."""
    for chunk in chunks:
        yield chunk


def _make_litellm_a2_response(
    content: str = "hello",
    tool_calls: list[Any] | None = None,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> MagicMock:
    """Build a mock litellm.acompletion response (non-streaming)."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    msg.model_dump.return_value = {
        "role": "assistant",
        "content": content,
        "tool_calls": (
            [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
            if tool_calls
            else None
        ),
    }

    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return resp


def _make_mock_tool_call(
    name: str,
    arguments: dict[str, Any],
    call_id: str = "call_001",
) -> MagicMock:
    """Create a mock tool_call object matching LiteLLM format."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


@pytest.fixture
def litellm_executor(tmp_path: Path):
    """Build a LiteLLMExecutor with mocked dependencies."""
    from core.execution.engines.litellm.litellm_loop import LiteLLMExecutor

    config = ModelConfig(
        model="openai/gpt-4o",
        api_key="sk-test",
        max_tokens=1024,
    )
    tool_handler = MagicMock()
    tool_handler._human_notifier = None
    memory = MagicMock()

    # Create minimal anima dir structure
    anima_dir = tmp_path / "animas" / "test"
    anima_dir.mkdir(parents=True)
    (anima_dir / "permissions.md").write_text("", encoding="utf-8")
    for sub in ["skills", "state"]:
        (anima_dir / sub).mkdir(exist_ok=True)

    executor = LiteLLMExecutor(
        model_config=config,
        anima_dir=anima_dir,
        tool_handler=tool_handler,
        tool_registry=[],
        memory=memory,
    )
    return executor


@pytest.fixture
def ollama_executor(tmp_path: Path):
    """Build a LiteLLMExecutor configured for Ollama (iteration-level)."""
    from core.execution.engines.litellm.litellm_loop import LiteLLMExecutor

    config = ModelConfig(
        model="ollama/llama3.2",
        max_tokens=2048,
    )
    tool_handler = MagicMock()
    tool_handler._human_notifier = None
    memory = MagicMock()

    anima_dir = tmp_path / "animas" / "test-ollama"
    anima_dir.mkdir(parents=True)
    (anima_dir / "permissions.md").write_text("", encoding="utf-8")
    for sub in ["skills", "state"]:
        (anima_dir / sub).mkdir(exist_ok=True)

    executor = LiteLLMExecutor(
        model_config=config,
        anima_dir=anima_dir,
        tool_handler=tool_handler,
        tool_registry=[],
        memory=memory,
    )
    return executor


class TestIsOllamaModelDetection:
    """_is_ollama_model returns True for ollama/ and ollama_chat/ prefixes."""

    def test_ollama_prefix(self, tmp_path: Path) -> None:
        from core.execution.engines.litellm.litellm_loop import LiteLLMExecutor

        config = ModelConfig(model="ollama/llama3.2")
        th = MagicMock()
        th._human_notifier = None
        anima_dir = tmp_path / "test"
        anima_dir.mkdir()
        (anima_dir / "permissions.md").write_text("")
        (anima_dir / "skills").mkdir()
        ex = LiteLLMExecutor(
            model_config=config,
            anima_dir=anima_dir,
            tool_handler=th,
            tool_registry=[],
            memory=MagicMock(),
        )
        assert ex._is_ollama_model is True

    def test_ollama_chat_prefix(self, tmp_path: Path) -> None:
        from core.execution.engines.litellm.litellm_loop import LiteLLMExecutor

        config = ModelConfig(model="ollama_chat/glm-4")
        th = MagicMock()
        th._human_notifier = None
        anima_dir = tmp_path / "test"
        anima_dir.mkdir()
        (anima_dir / "permissions.md").write_text("")
        (anima_dir / "skills").mkdir()
        ex = LiteLLMExecutor(
            model_config=config,
            anima_dir=anima_dir,
            tool_handler=th,
            tool_registry=[],
            memory=MagicMock(),
        )
        assert ex._is_ollama_model is True

    def test_openai_prefix_is_not_ollama(self, litellm_executor) -> None:
        assert litellm_executor._is_ollama_model is False

    def test_anthropic_prefix_is_not_ollama(self, tmp_path: Path) -> None:
        from core.execution.engines.litellm.litellm_loop import LiteLLMExecutor

        config = ModelConfig(model="anthropic/claude-sonnet-4-6")
        th = MagicMock()
        th._human_notifier = None
        anima_dir = tmp_path / "test"
        anima_dir.mkdir()
        (anima_dir / "permissions.md").write_text("")
        (anima_dir / "skills").mkdir()
        ex = LiteLLMExecutor(
            model_config=config,
            anima_dir=anima_dir,
            tool_handler=th,
            tool_registry=[],
            memory=MagicMock(),
        )
        assert ex._is_ollama_model is False


class TestA2TokenLevelTextOnly:
    """Token-level streaming with text-only response (no tool calls)."""

    async def test_yields_text_deltas_and_done(self, litellm_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)

        # Create streaming chunks: two text deltas + finish_reason=stop
        chunks = [
            FakeStreamChunk(text="Hello "),
            FakeStreamChunk(text="world!"),
            FakeStreamChunk(
                finish_reason="stop",
                usage=FakeUsage(prompt_tokens=50, completion_tokens=10),
            ),
        ]

        mock_acompletion = AsyncMock(return_value=_fake_async_stream(chunks))

        with (
            patch("litellm.acompletion", mock_acompletion),
            patch.object(litellm_executor, "_preflight_clamp", return_value={}),
        ):
            events = await _collect_events(
                litellm_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="Hi",
                    tracker=tracker,
                )
            )

        types = [e["type"] for e in events]
        assert "text_delta" in types
        assert "done" in types

        # Verify text deltas
        text_events = [e for e in events if e["type"] == "text_delta"]
        assert len(text_events) == 2
        assert text_events[0]["text"] == "Hello "
        assert text_events[1]["text"] == "world!"

        # Verify done event
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1
        assert done[0]["full_text"] == "Hello world!"
        assert done[0]["result_message"] is None

    async def test_interrupt_sets_stop_kind(self, litellm_executor) -> None:
        interrupt_event = asyncio.Event()
        interrupt_event.set()
        litellm_executor._interrupt_event = interrupt_event

        events = await _collect_events(
            litellm_executor.execute_streaming(
                system_prompt="sys",
                prompt="Hi",
                tracker=MagicMock(spec=ContextTracker),
            )
        )

        done = next(event for event in events if event["type"] == "done")
        assert done["stop_kind"] == "interrupted"


class TestA2TokenLevelWithToolCall:
    """Token-level streaming with tool call deltas."""

    async def test_yields_tool_start_and_tool_end(self, litellm_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)

        # First LLM call: yields text + tool_call chunks
        iter1_chunks = [
            FakeStreamChunk(text="Let me search."),
            FakeStreamChunk(
                tool_calls=[FakeDelta(index=0, id="call_1", name="search_memory")],
            ),
            FakeStreamChunk(
                tool_calls=[FakeDelta(index=0, arguments='{"query":')],
            ),
            FakeStreamChunk(
                tool_calls=[FakeDelta(index=0, arguments=' "test"}')],
            ),
            FakeStreamChunk(finish_reason="tool_calls"),
        ]

        # Second LLM call: final text only
        iter2_chunks = [
            FakeStreamChunk(text="Found it!"),
            FakeStreamChunk(finish_reason="stop"),
        ]

        call_count = 0

        async def mock_acompletion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _fake_async_stream(iter1_chunks)
            return _fake_async_stream(iter2_chunks)

        async def mock_process_tool_calls(parsed_calls, messages, tools, active_categories, **kwargs):
            """Mock _process_streaming_tool_calls as an async generator yielding tool_end events."""
            for tc in parsed_calls:
                yield {
                    "type": "tool_end",
                    "tool_id": tc["id"],
                    "tool_name": tc["name"],
                }

        with (
            patch("litellm.acompletion", side_effect=mock_acompletion),
            patch.object(litellm_executor, "_preflight_clamp", return_value={}),
            patch.object(
                litellm_executor,
                "_process_streaming_tool_calls",
                mock_process_tool_calls,
            ),
        ):
            events = await _collect_events(
                litellm_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="Search for something",
                    tracker=tracker,
                )
            )

        types = [e["type"] for e in events]
        assert "tool_start" in types
        assert "tool_end" in types
        assert "done" in types

        # Verify tool_start
        tool_starts = [e for e in events if e["type"] == "tool_start"]
        assert len(tool_starts) == 1
        assert tool_starts[0]["tool_name"] == "search_memory"
        assert tool_starts[0]["tool_id"] == "call_1"

        # Verify tool_end
        tool_ends = [e for e in events if e["type"] == "tool_end"]
        assert len(tool_ends) == 1
        assert tool_ends[0]["tool_name"] == "search_memory"
        assert tool_ends[0]["tool_id"] == "call_1"

        # Verify done
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1
        assert "Found it!" in done[0]["full_text"]


class TestA2StreamingRunawayGuard:
    @staticmethod
    def _tool_chunks(query: str, call_id: str) -> list[FakeStreamChunk]:
        return [
            FakeStreamChunk(
                tool_calls=[
                    FakeDelta(
                        index=0,
                        id=call_id,
                        name="search_memory",
                        arguments=json.dumps({"query": query}),
                    )
                ]
            ),
            FakeStreamChunk(finish_reason="tool_calls"),
        ]

    async def test_consecutive_calls_halt_then_return_answer(self, litellm_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)
        streams = [self._tool_chunks("same", f"call_{i}") for i in range(5)]
        streams.append([FakeStreamChunk(text="Final answer"), FakeStreamChunk(finish_reason="stop")])
        process_count = 0
        calls: list[dict[str, Any]] = []

        async def mock_acompletion(**kwargs):
            calls.append(kwargs)
            return _fake_async_stream(streams[len(calls) - 1])

        async def mock_process(parsed_calls, messages, tools, active_categories, **kwargs):
            nonlocal process_count
            process_count += 1
            if False:
                yield {}

        with (
            patch("litellm.acompletion", side_effect=mock_acompletion),
            patch.object(litellm_executor, "_preflight_clamp", return_value={}),
            patch.object(litellm_executor, "_process_streaming_tool_calls", mock_process),
        ):
            events = await _collect_events(
                litellm_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="search",
                    tracker=tracker,
                )
            )

        done = next(event for event in events if event["type"] == "done")
        assert done["full_text"] == "Final answer"
        assert done["truncated"] is True
        assert len(calls) == 6
        assert process_count == 4
        assert "tools" not in calls[-1]
        activity_entries = [
            json.loads(line)
            for path in (litellm_executor._anima_dir / "activity_log").glob("*.jsonl")
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        assert any(entry["type"] == "warning" and entry["meta"]["level"] == "WARNING" for entry in activity_entries)
        assert any(entry["type"] == "error" and entry["meta"]["level"] == "ERROR" for entry in activity_entries)

    async def test_warn_continues_execution(self, litellm_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)
        streams = [self._tool_chunks("same", f"call_{i}") for i in range(3)]
        streams.append([FakeStreamChunk(text="Done"), FakeStreamChunk(finish_reason="stop")])
        calls: list[dict[str, Any]] = []
        process_count = 0

        async def mock_acompletion(**kwargs):
            calls.append(kwargs)
            return _fake_async_stream(streams[len(calls) - 1])

        async def mock_process(parsed_calls, messages, tools, active_categories, **kwargs):
            nonlocal process_count
            process_count += 1
            if False:
                yield {}

        with (
            patch("litellm.acompletion", side_effect=mock_acompletion),
            patch.object(litellm_executor, "_preflight_clamp", return_value={}),
            patch.object(litellm_executor, "_process_streaming_tool_calls", mock_process),
        ):
            events = await _collect_events(
                litellm_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="search",
                    tracker=tracker,
                )
            )

        done = next(event for event in events if event["type"] == "done")
        assert done["full_text"] == "Done"
        assert process_count == 3
        warning = msg_tool_loop_warning(tool_names="search_memory", count=3)
        assert any(warning in str(message.get("content", "")) for message in calls[-1]["messages"])

    async def test_interleaved_cycle_halts_via_window(self, ollama_executor) -> None:
        from core.execution.loop_guards import RunawayGuard

        class SmallWindowGuard(RunawayGuard):
            def __init__(self) -> None:
                super().__init__(
                    warn_threshold=100,
                    halt_threshold=100,
                    window_size=8,
                    window_warn_threshold=2,
                    window_halt_threshold=3,
                )

        tracker = MagicMock(spec=ContextTracker)
        tool_responses = [
            _make_litellm_a2_response(
                content="",
                tool_calls=[_make_mock_tool_call("search_memory", {"query": "a" if i % 2 == 0 else "b"}, f"c{i}")],
            )
            for i in range(5)
        ]
        final = _make_litellm_a2_response(content="Cycle summary", tool_calls=None)
        mock_acompletion = AsyncMock(side_effect=[*tool_responses, final])
        process_count = 0

        async def mock_process(parsed_calls, messages, tools, active_categories, **kwargs):
            nonlocal process_count
            process_count += 1
            if False:
                yield {}

        with (
            patch("litellm.acompletion", mock_acompletion),
            patch.object(ollama_executor, "_preflight_clamp", return_value={}),
            patch.object(ollama_executor, "_process_streaming_tool_calls", mock_process),
            patch("core.execution.engines.litellm._litellm_streaming.RunawayGuard", SmallWindowGuard),
        ):
            events = await _collect_events(
                ollama_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="search",
                    tracker=tracker,
                )
            )

        done = next(event for event in events if event["type"] == "done")
        assert done["full_text"] == "Cycle summary"
        assert mock_acompletion.call_count == 6
        assert process_count == 4
        assert "tools" not in mock_acompletion.call_args_list[-1].kwargs

    async def test_more_than_two_hundred_unique_calls_are_not_halted(self, ollama_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)
        tool_responses = [
            _make_litellm_a2_response(
                content="",
                tool_calls=[_make_mock_tool_call("search_memory", {"query": f"q{i}"}, f"c{i}")],
            )
            for i in range(201)
        ]
        final = _make_litellm_a2_response(content="Long session complete", tool_calls=None)
        mock_acompletion = AsyncMock(side_effect=[*tool_responses, final])
        process_count = 0

        async def mock_process(parsed_calls, messages, tools, active_categories, **kwargs):
            nonlocal process_count
            process_count += 1
            if False:
                yield {}

        with (
            patch("litellm.acompletion", mock_acompletion),
            patch.object(ollama_executor, "_preflight_clamp", return_value={}),
            patch.object(ollama_executor, "_process_streaming_tool_calls", mock_process),
        ):
            events = await _collect_events(
                ollama_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="search",
                    tracker=tracker,
                )
            )

        done = next(event for event in events if event["type"] == "done")
        assert done["full_text"] == "Long session complete"
        assert done["truncated"] is False
        assert mock_acompletion.call_count == 202
        assert process_count == 201

    async def test_runaway_grace_answer_returns_final(self, ollama_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)
        repeated = _make_litellm_a2_response(
            content="",
            tool_calls=[_make_mock_tool_call("search_memory", {"query": "same"}, "c")],
        )
        final = _make_litellm_a2_response(content="Grace answer", tool_calls=None)
        mock_acompletion = AsyncMock(side_effect=[repeated] * 5 + [final])
        with (
            patch("litellm.acompletion", mock_acompletion),
            patch.object(ollama_executor, "_preflight_clamp", return_value={}),
        ):
            events = await _collect_events(
                ollama_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="answer",
                    tracker=tracker,
                    trigger="message:test",
                )
            )
        done = next(event for event in events if event["type"] == "done")
        assert done["full_text"] == "Grace answer"
        assert done["truncated"] is True
        assert mock_acompletion.call_count == 6
        assert "tools" not in mock_acompletion.call_args_list[-1].kwargs

    async def test_empty_final_response_returns_explicit_error(self, ollama_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)
        response = _make_litellm_a2_response(content="", tool_calls=None)
        mock_acompletion = AsyncMock(return_value=response)
        with (
            patch("litellm.acompletion", mock_acompletion),
            patch.object(ollama_executor, "_preflight_clamp", return_value={}),
        ):
            events = await _collect_events(
                ollama_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="answer",
                    tracker=tracker,
                )
            )
        done = next(event for event in events if event["type"] == "done")
        assert done["full_text"] == "Unable to generate a final response. Please try again."
        assert done["truncated"] is True


class TestA2TokenLevelErrorRaisesStreamDisconnected:
    """API error during token-level streaming raises StreamDisconnectedError."""

    async def test_error_raises_stream_disconnected(
        self,
        litellm_executor,
    ) -> None:
        tracker = MagicMock(spec=ContextTracker)

        mock_acompletion = AsyncMock(
            side_effect=RuntimeError("Connection refused"),
        )

        with (
            pytest.raises(StreamDisconnectedError) as exc_info,
            patch("litellm.acompletion", mock_acompletion),
            patch("core.execution.engines.litellm._litellm_streaming.decorrelated_jitter", return_value=0.0),
            patch.object(litellm_executor, "_preflight_clamp", return_value={}),
        ):
            await _collect_events(
                litellm_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="Hi",
                    tracker=tracker,
                )
            )

        err = exc_info.value
        assert err.partial_text == ""
        assert "stream error" in str(err).lower()
        assert "Connection refused" in str(err)


class TestA2IterationLevelTextOnly:
    """Iteration-level streaming (Ollama) with text-only response."""

    async def test_yields_text_delta_and_done(self, ollama_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)

        resp = _make_litellm_a2_response(
            content="Ollama says hello!",
            tool_calls=None,
            prompt_tokens=50,
            completion_tokens=20,
        )

        mock_acompletion = AsyncMock(return_value=resp)

        with (
            patch("litellm.acompletion", mock_acompletion),
            patch.object(ollama_executor, "_preflight_clamp", return_value={}),
        ):
            events = await _collect_events(
                ollama_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="Hello",
                    tracker=tracker,
                )
            )

        types = [e["type"] for e in events]
        assert "text_delta" in types
        assert "done" in types

        text_events = [e for e in events if e["type"] == "text_delta"]
        assert len(text_events) == 1
        assert text_events[0]["text"] == "Ollama says hello!"

        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1
        assert done[0]["full_text"] == "Ollama says hello!"


class TestA2IterationLevelWithToolCall:
    """Iteration-level streaming (Ollama) with tool calls."""

    async def test_yields_tool_events(self, ollama_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)

        # First response: tool call
        tc = _make_mock_tool_call(
            "search_memory",
            {"query": "test"},
            "call_olm_1",
        )
        resp_tool = _make_litellm_a2_response(
            content="Searching...",
            tool_calls=[tc],
        )

        # Second response: final text
        resp_final = _make_litellm_a2_response(
            content="Found it!",
            tool_calls=None,
        )

        mock_acompletion = AsyncMock(
            side_effect=[resp_tool, resp_final],
        )

        # Mock tool execution
        async def mock_execute_tool_call(tc, fn_args):
            return {"role": "tool", "tool_call_id": tc.id, "content": "result"}

        with (
            patch("litellm.acompletion", mock_acompletion),
            patch.object(ollama_executor, "_preflight_clamp", return_value={}),
            patch.object(
                ollama_executor,
                "_execute_tool_call",
                side_effect=mock_execute_tool_call,
            ),
        ):
            events = await _collect_events(
                ollama_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="Search for data",
                    tracker=tracker,
                )
            )

        types = [e["type"] for e in events]
        assert "tool_start" in types
        assert "tool_end" in types
        assert "done" in types

        # Verify tool events
        tool_starts = [e for e in events if e["type"] == "tool_start"]
        assert len(tool_starts) == 1
        assert tool_starts[0]["tool_name"] == "search_memory"

        tool_ends = [e for e in events if e["type"] == "tool_end"]
        assert len(tool_ends) == 1
        assert tool_ends[0]["tool_name"] == "search_memory"

        # Verify done
        done = [e for e in events if e["type"] == "done"]
        assert done[0]["full_text"] == "Searching...\n\nFound it!"

    async def test_parses_text_tool_call_with_preamble(self, ollama_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)

        resp_tool = _make_litellm_a2_response(
            content=('了解しました。以下の方法で回答します。\n\n{"name":"search_memory","arguments":{"query":"test"}}'),
            tool_calls=None,
        )
        resp_final = _make_litellm_a2_response(
            content="Found it!",
            tool_calls=None,
        )

        mock_acompletion = AsyncMock(side_effect=[resp_tool, resp_final])

        async def mock_execute_tool_call(tc, fn_args):
            return {"role": "tool", "tool_call_id": tc.id, "content": "result"}

        with (
            patch("litellm.acompletion", mock_acompletion),
            patch.object(ollama_executor, "_preflight_clamp", return_value={}),
            patch.object(
                ollama_executor,
                "_execute_tool_call",
                side_effect=mock_execute_tool_call,
            ),
        ):
            events = await _collect_events(
                ollama_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="Search for data",
                    tracker=tracker,
                )
            )

        types = [e["type"] for e in events]
        assert "tool_start" in types
        assert "tool_end" in types
        done = [e for e in events if e["type"] == "done"]
        assert done[0]["full_text"] == "Found it!"


class TestA2DispatchToTokenLevel:
    """Non-Ollama model routes to token-level streaming."""

    async def test_non_ollama_uses_token_level(self, litellm_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)

        # Spy on _stream_token_level
        token_called = False
        original_token = litellm_executor._stream_token_level

        async def spy_token(*args, **kwargs):
            nonlocal token_called
            token_called = True
            async for event in original_token(*args, **kwargs):
                yield event

        chunks = [
            FakeStreamChunk(text="test"),
            FakeStreamChunk(finish_reason="stop"),
        ]

        with (
            patch("litellm.acompletion", AsyncMock(return_value=_fake_async_stream(chunks))),
            patch.object(litellm_executor, "_preflight_clamp", return_value={}),
            patch.object(litellm_executor, "_stream_token_level", spy_token),
        ):
            await _collect_events(
                litellm_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="test",
                    tracker=tracker,
                )
            )

        assert token_called is True


class TestA2DispatchToIterationLevel:
    """Ollama model routes to iteration-level streaming."""

    async def test_ollama_uses_iteration_level(self, ollama_executor) -> None:
        tracker = MagicMock(spec=ContextTracker)

        iteration_called = False
        original_iter = ollama_executor._stream_iteration_level

        async def spy_iter(*args, **kwargs):
            nonlocal iteration_called
            iteration_called = True
            async for event in original_iter(*args, **kwargs):
                yield event

        resp = _make_litellm_a2_response(content="ok", tool_calls=None)

        with (
            patch("litellm.acompletion", AsyncMock(return_value=resp)),
            patch.object(ollama_executor, "_preflight_clamp", return_value={}),
            patch.object(ollama_executor, "_stream_iteration_level", spy_iter),
        ):
            await _collect_events(
                ollama_executor.execute_streaming(
                    system_prompt="sys",
                    prompt="test",
                    tracker=tracker,
                )
            )

        assert iteration_called is True
