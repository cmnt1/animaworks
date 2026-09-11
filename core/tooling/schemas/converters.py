from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Tool-schema format converters."""

from typing import Any


def to_anthropic_format(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert canonical schemas to Anthropic API format (``input_schema``)."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["parameters"],
        }
        for t in tools
    ]


def to_litellm_format(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert canonical schemas to LiteLLM/OpenAI function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in tools
    ]
