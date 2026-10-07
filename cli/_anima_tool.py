from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI re-exports for the current-anima standalone ToolHandler runner."""

from core.tooling.standalone import (
    current_anima_dir,
    require_anima_dir,
    tool_result_is_error,
)
from core.tooling.standalone import run_tool_for_current_anima as run_anima_tool

__all__ = ["current_anima_dir", "require_anima_dir", "run_anima_tool", "tool_result_is_error"]
