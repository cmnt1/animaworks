from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Execution engines for AgentCore.

Each engine implements one execution mode:
  - ``AgentSDKExecutor``  (S): Claude Agent SDK -- full tool access via subprocess
  - ``CodexSDKExecutor``  (C): Codex SDK -- Codex CLI wrapper for OpenAI models
  - ``CursorAgentExecutor`` (D): Cursor Agent CLI -- cursor-agent subprocess
  - ``GeminiCLIExecutor`` (G): Gemini CLI -- gemini subprocess with stream-json
  - ``GrokCLIExecutor`` (X): Grok Build CLI -- ACP subprocess over stdio
  - ``LiteLLMExecutor``   (A): LiteLLM + tool_use loop -- any model with tool support

Engine classes are resolved on first access so importing shared execution
utilities does not load every optional engine and its dependencies.
"""

from importlib import import_module
from typing import Any

from core.execution.base import BaseExecutor, ExecutionResult

_LAZY = {
    "AgentSDKExecutor": "core.execution.engines.claude.executor",
    "CodexSDKExecutor": "core.execution.engines.codex.executor",
    "CursorAgentExecutor": "core.execution.engines.cursor.executor",
    "GeminiCLIExecutor": "core.execution.engines.gemini.executor",
    "GrokCLIExecutor": "core.execution.engines.grok.executor",
    "LiteLLMExecutor": "core.execution.engines.litellm.executor",
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


__all__ = [
    "AgentSDKExecutor",
    "BaseExecutor",
    "CodexSDKExecutor",
    "CursorAgentExecutor",
    "ExecutionResult",
    "GeminiCLIExecutor",
    "GrokCLIExecutor",
    "LiteLLMExecutor",
]
