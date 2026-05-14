"""Tests for Claude Agent SDK transport monkey-patch compatibility."""

from __future__ import annotations

import sys
from types import ModuleType

import anyio
import pytest

from core.execution import _sdk_patch


class _FakeLock:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeStream:
    def __init__(self, events: list[str], name: str) -> None:
        self._events = events
        self._name = name

    async def aclose(self) -> None:
        self._events.append(f"{self._name}.aclose")


class _FakeProcess:
    def __init__(self, events: list[str], *, timeout_first_wait: bool = False) -> None:
        self.returncode: int | None = None
        self.wait_calls = 0
        self._events = events
        self._timeout_first_wait = timeout_first_wait

    async def wait(self) -> None:
        self.wait_calls += 1
        self._events.append(f"wait:{self.wait_calls}")
        if self._timeout_first_wait and self.wait_calls == 1:
            await anyio.sleep(1)
        self.returncode = 0

    def terminate(self) -> None:
        self._events.append("terminate")

    def kill(self) -> None:
        self._events.append("kill")
        self.returncode = 0


class _FakeCancelScope:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def cancel(self) -> None:
        self._events.append("task_group.cancel")


class _FakeTaskGroup:
    def __init__(self, events: list[str]) -> None:
        self.cancel_scope = _FakeCancelScope(events)
        self._events = events

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._events.append("task_group.exit")


class _FakeTask:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.cancelled = False
        self.waited = False

    def done(self) -> bool:
        return False

    def cancel(self) -> None:
        self.cancelled = True
        self._events.append("task.cancel")

    async def wait(self) -> None:
        self.waited = True
        self._events.append("task.wait")


class _NativeGracefulTransport:
    async def close(self) -> None:
        with anyio.fail_after(5):
            await self._process.wait()
        self._process.terminate()


class _LegacyTransport:
    async def close(self) -> None:
        self._process.terminate()


_NATIVE_GRACEFUL_CLOSE = _NativeGracefulTransport.close
_LEGACY_CLOSE = _LegacyTransport.close


@pytest.fixture(autouse=True)
def _restore_fake_transport_classes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_NativeGracefulTransport, "close", _NATIVE_GRACEFUL_CLOSE)
    monkeypatch.setattr(_LegacyTransport, "close", _LEGACY_CLOSE)


def _install_fake_sdk_modules(
    monkeypatch: pytest.MonkeyPatch,
    *,
    transport_class: type[object] = _LegacyTransport,
    query_class: type[object] | None = None,
    active_children: set[object] | None = None,
) -> None:
    sdk_module = ModuleType("claude_agent_sdk")
    internal_module = ModuleType("claude_agent_sdk._internal")
    transport_module = ModuleType("claude_agent_sdk._internal.transport")
    subprocess_cli_module = ModuleType("claude_agent_sdk._internal.transport.subprocess_cli")
    query_module = ModuleType("claude_agent_sdk._internal.query")

    subprocess_cli_module.SubprocessCLITransport = transport_class
    if active_children is not None:
        subprocess_cli_module._ACTIVE_CHILDREN = active_children
    if query_class is not None:
        query_module.Query = query_class

    transport_module.subprocess_cli = subprocess_cli_module
    internal_module.transport = transport_module
    internal_module.query = query_module
    sdk_module._internal = internal_module

    for name, module in {
        "claude_agent_sdk": sdk_module,
        "claude_agent_sdk._internal": internal_module,
        "claude_agent_sdk._internal.transport": transport_module,
        "claude_agent_sdk._internal.transport.subprocess_cli": subprocess_cli_module,
        "claude_agent_sdk._internal.query": query_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)


def _make_transport(events: list[str], *, process: _FakeProcess | None = None) -> _LegacyTransport:
    transport = _LegacyTransport()
    transport._process = process if process is not None else _FakeProcess(events)
    transport._ready = True
    transport._write_lock = _FakeLock()
    transport._stdin_stream = _FakeStream(events, "stdin")
    transport._stdout_stream = object()
    transport._stderr_stream = _FakeStream(events, "stderr")
    transport._exit_error = RuntimeError("old error")
    return transport


def test_native_graceful_close_detection() -> None:
    assert _sdk_patch._native_close_has_graceful_wait(_NativeGracefulTransport.close)
    assert not _sdk_patch._native_close_has_graceful_wait(_LegacyTransport.close)


def test_transport_close_patch_skips_native_graceful_close(monkeypatch: pytest.MonkeyPatch) -> None:
    original_close = _NativeGracefulTransport.close
    _install_fake_sdk_modules(monkeypatch, transport_class=_NativeGracefulTransport)

    _sdk_patch._patch_transport_close()

    assert _NativeGracefulTransport.close is original_close


@pytest.mark.asyncio
async def test_legacy_patched_close_does_not_require_stderr_task_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _install_fake_sdk_modules(monkeypatch, transport_class=_LegacyTransport)
    _sdk_patch._patch_transport_close()
    transport = _make_transport(events)
    assert not hasattr(transport, "_stderr_task_group")

    await transport.close()

    assert transport._process is None
    assert "stdin.aclose" in events
    assert "stderr.aclose" in events
    assert "wait:1" in events


@pytest.mark.asyncio
async def test_legacy_patched_close_waits_after_stdin_eof_before_terminate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    process = _FakeProcess(events, timeout_first_wait=True)
    _install_fake_sdk_modules(monkeypatch, transport_class=_LegacyTransport)
    monkeypatch.setattr(_sdk_patch, "_GRACEFUL_EXIT_TIMEOUT_SEC", 0.01)
    _sdk_patch._patch_transport_close()
    transport = _make_transport(events, process=process)

    await transport.close()

    assert events.index("stdin.aclose") < events.index("wait:1")
    assert events.index("wait:1") < events.index("terminate")
    assert "wait:2" in events
    assert "kill" not in events


@pytest.mark.asyncio
async def test_legacy_patched_close_cancels_stderr_task_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _install_fake_sdk_modules(monkeypatch, transport_class=_LegacyTransport)
    _sdk_patch._patch_transport_close()
    transport = _make_transport(events)
    transport._stderr_task_group = _FakeTaskGroup(events)

    await transport.close()

    assert events[:2] == ["task_group.cancel", "task_group.exit"]
    assert transport._stderr_task_group is None


@pytest.mark.asyncio
async def test_legacy_patched_close_cancels_stderr_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _install_fake_sdk_modules(monkeypatch, transport_class=_LegacyTransport)
    _sdk_patch._patch_transport_close()
    transport = _make_transport(events)
    task = _FakeTask(events)
    transport._stderr_task = task

    await transport.close()

    assert task.cancelled
    assert task.waited
    assert transport._stderr_task is None


def test_windows_query_patch_skips_when_method_absent(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class QueryWithoutWait:
        pass

    _install_fake_sdk_modules(monkeypatch, query_class=QueryWithoutWait)

    _sdk_patch._patch_query_stdin_lifecycle()

    assert "has no wait_for_result_and_end_input method" in caplog.text


def test_current_sdk_native_close_is_preserved_when_graceful() -> None:
    pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    original_close = SubprocessCLITransport.close
    if not _sdk_patch._native_close_has_graceful_wait(original_close):
        pytest.skip("installed SDK close is not natively graceful")

    original_patched = _sdk_patch._patched
    try:
        _sdk_patch._patched = False
        _sdk_patch.apply_sdk_transport_patch()
        assert SubprocessCLITransport.close is original_close
    finally:
        SubprocessCLITransport.close = original_close
        _sdk_patch._patched = original_patched
