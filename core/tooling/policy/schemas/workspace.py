from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Workspace access management tool schemas."""

from typing import Any

WORKSPACE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "grant_workspace_access",
        "description": (
            "Grant explicit write access to a workspace for a top-level Anima or a descendant. "
            "Only allowed for human-origin instructions handled by a top-level Anima. "
            "Updates the global workspace registry and the target Anima's permissions; "
            "optionally sets its default_workspace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "alias": {
                    "type": "string",
                    "description": "Short workspace alias, such as finance-dashboard.",
                },
                "path": {
                    "type": "string",
                    "description": "Existing directory path to grant as writable.",
                },
                "target_anima": {
                    "type": "string",
                    "description": "Target Anima name or alias. Omit = calling top-level Anima.",
                },
                "make_default": {
                    "type": "boolean",
                    "description": "Set target default_workspace to alias#hash. Default: true.",
                },
            },
            "required": ["alias", "path"],
        },
    }
]
