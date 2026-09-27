from __future__ import annotations

"""Guard rails for the agent_sdk re-export surface.

After R18-2 removed test-only re-exports from ``agent_sdk.py``, the module
must still expose the names that the production runtime actually imports:
  - ``AgentSDKExecutor`` (imported directly)
  - the ``core.execution.engines.claude.agent_sdk:AgentSDKExecutor`` string
    path referenced by ``executor_factory.ENGINE_ADAPTERS``
"""

from importlib import import_module


def test_agent_sdk_executor_importable() -> None:
    """AgentSDKExecutor is importable from agent_sdk (production surface)."""
    from core.execution.engines.claude.agent_sdk import AgentSDKExecutor

    assert AgentSDKExecutor is not None


def test_executor_factory_string_path_resolves() -> None:
    """executor_factory's string path to AgentSDKExecutor stays valid."""
    from core.agent.executor_factory import ENGINE_ADAPTERS

    path = "core.execution.engines.claude.agent_sdk:AgentSDKExecutor"
    assert any(a.executor_path == path for a in ENGINE_ADAPTERS.values())

    module_name, _, attr = path.partition(":")
    cls = getattr(import_module(module_name), attr)
    assert cls is not None
