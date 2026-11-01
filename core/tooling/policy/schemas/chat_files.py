from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Chat attachment (``attach_file``) tool schema."""

from typing import Any

from core.i18n import t as _t


def _chat_file_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "attach_file",
            "description": _t("schema.attach_file.desc"),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": _t("schema.attach_file.path"),
                    },
                    "name": {
                        "type": "string",
                        "description": _t("schema.attach_file.name"),
                    },
                },
                "required": ["path"],
            },
        },
    ]


CHAT_FILE_TOOLS = _chat_file_tools()

__all__ = ["CHAT_FILE_TOOLS", "_chat_file_tools"]
