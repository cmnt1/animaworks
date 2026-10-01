from __future__ import annotations

"""Python module entry points launched by AnimaWorks subprocesses."""

from enum import StrEnum


class SubprocessEntry(StrEnum):
    """Canonical ``python -m`` entry points used by runtime launchers."""

    MCP_SERVER = "core.mcp.server"
    SUPERVISOR_RUNNER = "core.runtime.runner"
    TASK_RUNNER = "core.runtime.task_runner"
    RAG_REPAIR_REBUILD = "core.memory.rag.repair.rebuild"
    CODEX_COMMAND_HOOK = "cli.codex_command_hook"


PYTHON_MODULE_FLAG = "-m"


def module_args(entry: SubprocessEntry) -> tuple[str, str]:
    """Return arguments for launching *entry* with the active Python."""
    return PYTHON_MODULE_FLAG, entry.value
