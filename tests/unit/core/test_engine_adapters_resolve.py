"""Every engine adapter path in the executor factory must import.

The factory imports executors by string and treats ImportError as "engine
unavailable", silently falling back to another model. A stale path after a
module move would therefore never fail loudly, so pin every target here.
"""

from __future__ import annotations

import pytest

from core.agent.executor_factory import ENGINE_ADAPTERS, _resolve


_EXPECTED_ENGINE_MODES = {"s", "c", "d", "g", "x", "a"}


def test_all_engine_adapters_are_registered() -> None:
    assert set(ENGINE_ADAPTERS) == _EXPECTED_ENGINE_MODES


@pytest.mark.parametrize("mode", sorted(ENGINE_ADAPTERS))
def test_engine_adapter_paths_resolve(mode: str) -> None:
    adapter = ENGINE_ADAPTERS[mode]
    if mode == "s":
        pytest.importorskip("claude_agent_sdk")
    assert isinstance(_resolve(adapter.executor_path), type)
    if adapter.availability_path:
        assert callable(_resolve(adapter.availability_path))
    if adapter.availability_attr:
        assert adapter.availability_attr == "_sdk_available"


def test_mode_a_resolves_via_concrete_engine_module() -> None:
    adapter = ENGINE_ADAPTERS["a"]
    assert adapter.executor_path == "core.execution.engines.litellm.executor:LiteLLMExecutor"
    assert isinstance(_resolve(adapter.executor_path), type)


def test_execution_facade_propagates_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.execution as execution

    def fail_import(module_name: str) -> object:
        raise ImportError(f"missing optional dependency for {module_name}")

    monkeypatch.setattr(execution, "import_module", fail_import)
    with pytest.raises(ImportError, match="missing optional dependency"):
        execution.__getattr__("LiteLLMExecutor")
