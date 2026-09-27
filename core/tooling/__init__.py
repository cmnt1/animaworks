# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from core.tooling.dispatch import ExternalToolDispatcher
from core.tooling.schemas import (
    MEMORY_TOOLS,
    load_all_tool_schemas,
    load_external_schemas,
    load_personal_tool_schemas,
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
    "MEMORY_TOOLS",
    "OnMessageSentFn",
    "ToolHandler",
    "load_all_tool_schemas",
    "load_external_schemas",
    "load_personal_tool_schemas",
    "to_litellm_format",
]
