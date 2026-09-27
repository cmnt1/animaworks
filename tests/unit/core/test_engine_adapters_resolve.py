"""Every engine adapter path in the executor factory must import.

The factory imports executors by string and treats ImportError as "engine
unavailable", silently falling back to another model. A stale path after a
module move would therefore never fail loudly, so pin every target here.
"""

from __future__ import annotations

import pytest

from core.agent.executor_factory import ENGINE_ADAPTERS, _resolve


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
