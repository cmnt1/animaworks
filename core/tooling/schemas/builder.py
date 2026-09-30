from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Tool list builder helpers."""

from typing import Any

from core.prompt.tool_content import apply_prompt_descriptions
from core.tooling.schemas.admin import CC_TOOLS
from core.tooling.schemas.channel import _channel_tools
from core.tooling.schemas.memory import KNOWLEDGE_TOOLS, MEMORY_TOOLS, PROCEDURE_TOOLS
from core.tooling.schemas.notification import _notification_tools
from core.tooling.schemas.session_todo import _session_todo_tools
from core.tooling.schemas.skill import _create_skill_schemas, _curator_skill_schemas
from core.tooling.schemas.supervisor import _supervisor_tools
from core.tooling.schemas.task import _submit_tasks_tools, _task_tools
from core.tooling.schemas.workspace import WORKSPACE_TOOLS
from core.tooling.surface import ToolSurfaceContext, resolve_tool_surface


def build_unified_tool_list(
    *,
    include_notification_tools: bool = False,
    include_supervisor_tools: bool = False,
    include_create_skill: bool = True,
    trigger: str = "",
    compact: bool = False,
) -> list[dict[str, Any]]:
    """Build the Mode A/B unified runtime tool list from the shared surface.

    Schema assembly remains provider-neutral; all name-based visibility is
    decided by :func:`resolve_tool_surface`.

    Args:
        include_notification_tools: Include ``call_human`` when notifications are configured.
        include_supervisor_tools: Include subordinate tools when the Anima has subordinates.
        include_create_skill: Include skill authoring and curation tools.
        trigger: Execution trigger (for example ``"consolidation:daily"``).
        compact: Restrict the surface to the small-context communication tools.
    """
    visible_names = set(
        resolve_tool_surface(
            ToolSurfaceContext(
                has_subordinates=include_supervisor_tools,
                include_notification_tools=include_notification_tools,
                include_create_skill=include_create_skill,
                compact=compact,
            ),
            trigger,
            "A",
        )
    )

    candidate_tools: list[dict[str, Any]] = [
        *CC_TOOLS,
        *MEMORY_TOOLS,
        *PROCEDURE_TOOLS,
        *KNOWLEDGE_TOOLS,
        *WORKSPACE_TOOLS,
        *_channel_tools(),
        *_notification_tools(),
        *_supervisor_tools(),
        *_submit_tasks_tools(),
        *_task_tools(),
        *_session_todo_tools(),
    ]
    tools = apply_prompt_descriptions([tool for tool in candidate_tools if tool["name"] in visible_names])

    skill_tools = [*_create_skill_schemas(), *_curator_skill_schemas()]
    tools.extend(tool for tool in skill_tools if tool["name"] in visible_names)
    return tools
