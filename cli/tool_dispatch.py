from __future__ import annotations

"""CLI-facing dispatcher for tools and main CLI command aliases."""

import os
import sys
from pathlib import Path

MAIN_CLI_COMMANDS: frozenset[str] = frozenset(
    {
        "init",
        "start",
        "serve",
        "stop",
        "restart",
        "reset",
        "chat",
        "heartbeat",
        "send",
        "status",
        "logs",
        "board",
        "anima",
        "config",
        "task",
        "internal",
        "supervisor",
        "vault",
        "models",
        "cost",
        "optimize-assets",
        "remake",
        "profile",
    }
)

ANIMA_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "list",
        "info",
        "status",
        "restart",
        "create",
        "delete",
        "enable",
        "disable",
        "set-model",
        "set-background-model",
        "reload",
        "set-role",
        "rename",
        "audit",
    }
)


def cli_dispatch() -> None:
    """Dispatch external tools, forwarding main CLI aliases on the CLI layer."""
    from core.integrations import (
        TOOL_MODULES,
        discover_common_tools,
        discover_personal_tools,
    )
    from core.integrations import (
        cli_dispatch as integrations_cli_dispatch,
    )

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        integrations_cli_dispatch()
        return

    tool_name = sys.argv[1]
    anima_dir = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
    common_tools = discover_common_tools()
    personal_tools = discover_personal_tools(Path(anima_dir)) if anima_dir else {}
    if tool_name in TOOL_MODULES or tool_name in common_tools or tool_name in personal_tools or tool_name == "submit":
        integrations_cli_dispatch()
        return

    if tool_name in MAIN_CLI_COMMANDS:
        sys.argv = ["animaworks", *sys.argv[1:]]
    elif tool_name in ANIMA_SUBCOMMANDS:
        sys.argv = ["animaworks", "anima", *sys.argv[1:]]
    else:
        integrations_cli_dispatch()
        return

    from cli import cli_main

    cli_main()
