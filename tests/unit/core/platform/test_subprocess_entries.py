from __future__ import annotations

from core.platform.subprocess_entries import PYTHON_MODULE_FLAG, SubprocessEntry, module_args


def test_subprocess_modules_are_centralized() -> None:
    assert {entry.value for entry in SubprocessEntry} == {
        "core.mcp.server",
        "core.supervisor.runner",
        "core.supervisor.task_runner",
        "core.memory.rag.repair.rebuild",
        "core.tooling.codex_command_hook",
    }


def test_module_args_build_python_module_entry() -> None:
    assert module_args(SubprocessEntry.MCP_SERVER) == (PYTHON_MODULE_FLAG, "core.mcp.server")
