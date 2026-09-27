from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.execution.engines.cursor.cursor_agent import CursorAgentExecutor
from core.execution.engines.gemini.gemini_cli import GeminiCLIExecutor
from core.prompt.context import ContextTracker
from core.schemas import ModelConfig


def _fake_process(
    stdout: bytes = b"",
    *,
    returncode: int = 0,
    stderr: bytes = b"",
    read_error: Exception | None = None,
) -> AsyncMock:
    process = AsyncMock()
    process.returncode = returncode
    process.pid = None
    process.wait = AsyncMock()
    process.stdout = AsyncMock()
    lines = iter(stdout.splitlines(keepends=True))
    process.stdout.readline = AsyncMock(side_effect=read_error or (lambda: next(lines, b"")))
    process.stderr = AsyncMock()
    process.stderr.read = AsyncMock(return_value=stderr)
    return process


def _encode_events(*events: dict) -> bytes:
    return b"".join(json.dumps(event).encode() + b"\n" for event in events)


def _process_for(engine: str, scenario: str) -> AsyncMock:
    if engine == "D":
        if scenario == "nonzero":
            return _fake_process(returncode=1, stderr=b"rate limit exceeded")
        if scenario == "exception":
            return _fake_process(returncode=1, read_error=RuntimeError("broken stream"))
        if scenario == "timeout":
            return _fake_process(returncode=1, read_error=TimeoutError("idle"))
        if scenario == "auth":
            return _fake_process(returncode=1, stderr=b"not authenticated; run agent login")
        return _fake_process(_encode_events({"type": "result", "result": "ok"}))

    if scenario == "timeout":
        return _fake_process(returncode=1, read_error=TimeoutError("idle"))
    if scenario == "auth":
        return _fake_process(returncode=1, stderr=b"unauthenticated; run gemini auth login")
    if scenario == "severity_error":
        return _fake_process(_encode_events({"type": "error", "severity": "error", "message": "rate limit exceeded"}))
    if scenario == "result_error":
        return _fake_process(
            _encode_events(
                {
                    "type": "result",
                    "status": "error",
                    "error": {"message": "rate limit exceeded"},
                }
            )
        )
    if scenario == "nonzero":
        return _fake_process(returncode=2, stderr=b"rate limit exceeded")
    return _fake_process(_encode_events({"type": "result", "status": "success"}))


@pytest.fixture
async def engine_setup(tmp_path: Path):
    anima_dir = tmp_path / "animas" / "engine-errors"
    anima_dir.mkdir(parents=True)
    cursor = CursorAgentExecutor(
        ModelConfig(model="cursor/claude-4-sonnet", execution_mode="D", resolved_mode="D"),
        anima_dir,
    )
    gemini = GeminiCLIExecutor(
        ModelConfig(model="gemini/2.5-pro", execution_mode="G", resolved_mode="G"),
        anima_dir,
    )
    return cursor, gemini


@pytest.mark.parametrize(
    ("engine", "scenario", "reason"),
    [
        ("D", "nonzero", "rate_limit"),
        ("D", "exception", "unknown"),
        ("D", "timeout", "timeout"),
        ("D", "auth", "auth"),
        ("G", "result_error", "rate_limit"),
        ("G", "severity_error", "rate_limit"),
        ("G", "nonzero", "rate_limit"),
        ("G", "timeout", "timeout"),
        ("G", "auth", "auth"),
    ],
)
@pytest.mark.asyncio
async def test_cli_errors_are_terminal_stream_events_and_blocking_errors(engine_setup, engine, scenario, reason):
    cursor, gemini = engine_setup
    executor = cursor if engine == "D" else gemini

    def spec_factory():
        return _process_for(engine, scenario)

    rate_guard = SimpleNamespace(
        config=SimpleNamespace(default_block_seconds=60, quota_block_seconds=600),
        report_block=Mock(),
    )
    patches = [
        patch("asyncio.create_subprocess_exec", side_effect=lambda *args, **kwargs: spec_factory()),
        patch("core.execution.engine_base.get_rate_guard", return_value=rate_guard),
    ]
    if engine == "D":
        patches.extend(
            [
                patch.object(cursor, "_find_binary", return_value="/fake/cursor-agent"),
                patch.object(cursor, "_ensure_workspace"),
                patch.object(cursor, "_write_mcp_config"),
                patch.object(cursor, "_write_cursor_rules"),
            ]
        )
    else:
        patches.append(
            patch("core.execution.engines.gemini.gemini_cli._find_gemini_binary", return_value="/fake/gemini")
        )

    with ExitStack() as stack:
        for patcher in patches:
            stack.enter_context(patcher)
        events = [
            event
            async for event in executor.execute_streaming(
                system_prompt="",
                prompt="hello",
                tracker=ContextTracker(model=executor._model_config.model, threshold=0.5),
            )
        ]
        result = await executor.execute(prompt="hello")

    errors = [event for event in events if event.get("type") == "error"]
    done = next(event for event in events if event.get("type") == "done")
    assert len(errors) == 1
    assert errors[0]["terminal"] is True
    assert errors[0]["reason"] == reason
    assert events.index(errors[0]) < events.index(done)
    assert done["error"] is True
    assert done["reason"] == reason
    assert result.error is True
    assert result.reason == reason


@pytest.mark.parametrize("engine", ["D", "G"])
@pytest.mark.asyncio
async def test_successful_cli_stream_has_no_error_event(engine_setup, engine):
    cursor, gemini = engine_setup
    executor = cursor if engine == "D" else gemini
    with (
        patch("asyncio.create_subprocess_exec", side_effect=lambda *args, **kwargs: _process_for(engine, "success")),
        patch.object(cursor, "_find_binary", return_value="/fake/cursor-agent")
        if engine == "D"
        else patch("core.execution.engines.gemini.gemini_cli._find_gemini_binary", return_value="/fake/gemini"),
        patch.object(cursor, "_ensure_workspace"),
        patch.object(cursor, "_write_mcp_config"),
        patch.object(cursor, "_write_cursor_rules"),
    ):
        events = [
            event
            async for event in executor.execute_streaming(
                system_prompt="",
                prompt="hello",
                tracker=ContextTracker(model=executor._model_config.model, threshold=0.5),
            )
        ]

    assert not any(event.get("type") == "error" for event in events)
    assert next(event for event in events if event.get("type") == "done").get("error", False) is False


@pytest.mark.parametrize("engine", ["D", "G"])
@pytest.mark.asyncio
async def test_missing_cli_is_reported_as_terminal_unknown_error(engine_setup, engine):
    cursor, gemini = engine_setup
    executor = cursor if engine == "D" else gemini
    binary_patch = (
        patch.object(cursor, "_find_binary", return_value=None)
        if engine == "D"
        else patch("core.execution.engines.gemini.gemini_cli._find_gemini_binary", return_value=None)
    )

    with binary_patch:
        events = [
            event
            async for event in executor.execute_streaming(
                system_prompt="",
                prompt="hello",
                tracker=ContextTracker(model=executor._model_config.model, threshold=0.5),
            )
        ]
        result = await executor.execute(prompt="hello")

    errors = [event for event in events if event.get("type") == "error"]
    done = next(event for event in events if event.get("type") == "done")
    assert len(errors) == 1
    assert errors[0]["terminal"] is True
    assert errors[0]["reason"] == "unknown"
    assert events.index(errors[0]) < events.index(done)
    assert done["error"] is True
    assert done["reason"] == "unknown"
    assert result.error is True
    assert result.reason == "unknown"
