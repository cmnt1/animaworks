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
"""

# AgentSDKExecutor requires claude_agent_sdk which may not be installed.
# Import it lazily so the rest of the package works regardless.
try:
    from core.execution.engines.claude.agent_sdk import AgentSDKExecutor
except ImportError:  # pragma: no cover
    AgentSDKExecutor = None  # type: ignore[assignment,misc]

# CodexSDKExecutor requires openai_codex (optional dependency).
try:
    from core.execution.engines.codex.codex_sdk import CodexSDKExecutor
except ImportError:  # pragma: no cover
    CodexSDKExecutor = None  # type: ignore[assignment,misc]

# CursorAgentExecutor requires cursor-agent CLI (optional).
try:
    from core.execution.engines.cursor.cursor_agent import CursorAgentExecutor
except ImportError:  # pragma: no cover
    CursorAgentExecutor = None  # type: ignore[assignment,misc]

# GeminiCLIExecutor requires gemini CLI (optional).
try:
    from core.execution.engines.gemini.gemini_cli import GeminiCLIExecutor
except ImportError:  # pragma: no cover
    GeminiCLIExecutor = None  # type: ignore[assignment,misc]

# GrokCLIExecutor requires grok CLI (optional).
try:
    from core.execution.engines.grok.grok_cli import GrokCLIExecutor
except ImportError:  # pragma: no cover
    GrokCLIExecutor = None  # type: ignore[assignment,misc]

from core.execution.base import BaseExecutor, ExecutionResult
from core.execution.engines.litellm.litellm_loop import LiteLLMExecutor

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
