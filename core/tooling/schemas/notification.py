from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Notification (call_human) tool schemas."""

from typing import Any

from core.i18n import t as _t


def _notification_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "call_human",
            "description": _t("schema.call_human.desc"),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": _t("schema.call_human.subject"),
                    },
                    "body": {
                        "type": "string",
                        "description": _t("schema.call_human.body"),
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "normal", "high", "urgent"],
                        "description": _t("schema.call_human.priority"),
                    },
                    "interactive": {
                        "type": "boolean",
                        "default": False,
                        "description": _t("schema.call_human.interactive_desc"),
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["approve", "reject", "comment"],
                        "description": _t("schema.call_human.options_desc"),
                    },
                    "category": {
                        "type": "string",
                        "default": "approval",
                        "description": _t("schema.call_human.category_desc"),
                    },
                    "allowed_users": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": _t("schema.call_human.allowed_users_desc"),
                    },
                },
                "required": ["subject", "body"],
            },
        },
    ]
