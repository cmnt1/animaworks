from __future__ import annotations

import importlib.util

from core.platform.subprocess_entries import PYTHON_MODULE_FLAG, SubprocessEntry, module_args


def test_subprocess_modules_are_centralized() -> None:
    assert {entry.value for entry in SubprocessEntry} == {
        "core.mcp.server",
        "core.runtime.runner",
        "core.runtime.task_runner",
        "core.memory.rag.repair.rebuild",
        "cli.codex_command_hook",
    }


def test_module_args_build_python_module_entry() -> None:
    assert module_args(SubprocessEntry.MCP_SERVER) == (PYTHON_MODULE_FLAG, "core.mcp.server")


def test_all_subprocess_entries_resolve_to_importable_modules() -> None:
    for entry in SubprocessEntry:
        assert importlib.util.find_spec(entry.value) is not None, entry.value
