# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Canonical tool schema definitions and format converters.

All tool schemas are defined once in a provider-neutral format and converted
to Anthropic or LiteLLM/OpenAI formats on demand.
"""

from __future__ import annotations

from core.tooling.policy.schemas.admin import ADMIN_TOOLS, CC_TOOLS
from core.tooling.policy.schemas.builder import build_unified_tool_list
from core.tooling.policy.schemas.channel import _channel_tools
from core.tooling.policy.schemas.converters import to_litellm_format
from core.tooling.policy.schemas.loader import (
    _normalise_schema,
    load_all_tool_schemas,
    load_external_schemas,
    load_external_schemas_by_category,
    load_personal_tool_schemas,
)
from core.tooling.policy.schemas.memory import (
    FILE_TOOLS,
    KNOWLEDGE_TOOLS,
    MEMORY_TOOLS,
    PROCEDURE_TOOLS,
    SEARCH_TOOLS,
)
from core.tooling.policy.schemas.notification import _notification_tools
from core.tooling.policy.schemas.skill import (
    _create_skill_schemas,
    _curator_skill_schemas,
)
from core.tooling.policy.schemas.supervisor import (
    _background_task_tools,
    _check_permissions_tools,
    _supervisor_tools,
    _vault_tools,
)
from core.tooling.policy.schemas.task import SUBMIT_TASKS_TOOLS, _submit_tasks_tools, _task_tools
from core.tooling.policy.schemas.workspace import WORKSPACE_TOOLS
from core.tooling.policy.tool_content import apply_prompt_descriptions

__all__ = [
    "ADMIN_TOOLS",
    "CC_TOOLS",
    "KNOWLEDGE_TOOLS",
    "MEMORY_TOOLS",
    "FILE_TOOLS",
    "SEARCH_TOOLS",
    "PROCEDURE_TOOLS",
    "SUBMIT_TASKS_TOOLS",
    "_submit_tasks_tools",
    "WORKSPACE_TOOLS",
    "_background_task_tools",
    "_channel_tools",
    "_check_permissions_tools",
    "_notification_tools",
    "_normalise_schema",
    "_create_skill_schemas",
    "_curator_skill_schemas",
    "_supervisor_tools",
    "_task_tools",
    "_vault_tools",
    "apply_prompt_descriptions",
    "build_unified_tool_list",
    "load_all_tool_schemas",
    "load_external_schemas",
    "load_external_schemas_by_category",
    "load_personal_tool_schemas",
    "to_litellm_format",
]
