from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Output handling shared by CLI adapters for internal ToolHandler tools."""

import json

_ERROR_PREFIXES = (
    "error:",
    "error ",
    "エラー:",
    "エラー：",
    "오류:",
    "오류：",
    "错误:",
    "错误：",
    "錯誤:",
    "錯誤：",
)
_ERROR_HINTS = (
    "cannot send to '",
    "宛先 '",
    "会議中は",
    "not available during meetings",
    "dm send failed:",
    "dm送信失敗:",
)


def is_tool_error_result(result: str) -> bool:
    """Recognize structured and plain-text errors returned by ToolHandler."""
    text = result.lstrip()
    if text.startswith("{"):
        try:
            payload, _ = json.JSONDecoder().raw_decode(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and str(payload.get("status", "")).casefold() == "error":
            return True

    first_line = text.splitlines()[0] if text else ""
    normalized = first_line.casefold()
    return normalized.startswith(_ERROR_PREFIXES) or any(hint in normalized for hint in _ERROR_HINTS)


def print_tool_result(result: str) -> None:
    """Print a ToolHandler result and exit non-zero when it reports an error."""
    print(result)
    if is_tool_error_result(result):
        raise SystemExit(1)
