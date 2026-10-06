from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Run an internal tool on behalf of the anima whose tool context we are in.

``animaworks-tool`` subcommands that mirror an internal tool are thin argparse
front-ends: they translate argv into tool arguments and call this module, so the
CLI and the tool share one implementation (validation, permissions, company
boundaries, activity logging) through ``ToolHandler.handle``.
"""

import sys
from functools import cache
from pathlib import Path
from typing import Any

from core.platform.env import anima_dir_env


def current_anima_dir() -> Path | None:
    """Return the calling anima's directory, or ``None`` outside a tool context."""
    value = anima_dir_env() or ""
    if not value:
        return None
    path = Path(value)
    return path if path.is_dir() else None


def require_anima_dir() -> Path:
    """Return the calling anima's directory or exit with a usage error."""
    anima_dir = current_anima_dir()
    if anima_dir is None:
        print(
            "Error: ANIMAWORKS_ANIMA_DIR not set or missing (set automatically inside an anima's tool context)",
            file=sys.stderr,
        )
        sys.exit(1)
    return anima_dir


@cache
def _handler(anima_dir: Path) -> Any:
    from core.tooling.standalone import build_standalone_tool_handler

    return build_standalone_tool_handler(anima_dir, for_mcp=False)


def run_anima_tool(tool_name: str, tool_args: dict[str, Any], *, anima_dir: Path | None = None) -> str:
    """Run *tool_name* through the anima's ``ToolHandler`` and return its result text."""
    return _handler((anima_dir or require_anima_dir()).resolve()).handle(tool_name, tool_args)
