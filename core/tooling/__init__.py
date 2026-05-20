# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from core.tooling.dispatch import ExternalToolDispatcher
from core.tooling.guide import build_tools_guide, load_tool_schemas
from core.tooling.schemas import (
    FILE_TOOLS,
    MEMORY_TOOLS,
    build_tool_list,
    load_all_tool_schemas,
    load_external_schemas,
    load_personal_tool_schemas,
    to_anthropic_format,
    to_litellm_format,
)


def __getattr__(name: str) -> Any:
    if name in {"OnMessageSentFn", "ToolHandler"}:
        from core.tooling.handler import OnMessageSentFn, ToolHandler

        return {
            "OnMessageSentFn": OnMessageSentFn,
            "ToolHandler": ToolHandler,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ExternalToolDispatcher",
    "FILE_TOOLS",
    "MEMORY_TOOLS",
    "OnMessageSentFn",
    "ToolHandler",
    "build_tool_list",
    "build_tools_guide",
    "load_all_tool_schemas",
    "load_external_schemas",
    "load_personal_tool_schemas",
    "load_tool_schemas",
    "to_anthropic_format",
    "to_litellm_format",
]
