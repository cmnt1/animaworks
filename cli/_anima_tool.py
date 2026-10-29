from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Run an internal tool on behalf of the anima whose tool context we are in.

``animaworks-tool`` subcommands that mirror an internal tool are thin argparse
front-ends: they map argv onto tool arguments and call :func:`run_and_print`, so
the CLI and the tool share one implementation through ``ToolHandler.handle``.
"""

import sys
from typing import Any

from core.tooling.standalone import (
    current_anima_dir,
    require_anima_dir,
    tool_result_is_error,
)
from core.tooling.standalone import run_tool_for_current_anima as run_anima_tool


def run_and_print(tool_name: str, tool_args: dict[str, Any]) -> None:
    """Run *tool_name*, print its result, and exit 1 when the tool reports an error."""
    result = run_anima_tool(tool_name, tool_args)
    print(result)
    if tool_result_is_error(result):
        sys.exit(1)


__all__ = ["current_anima_dir", "require_anima_dir", "run_and_print", "run_anima_tool", "tool_result_is_error"]
