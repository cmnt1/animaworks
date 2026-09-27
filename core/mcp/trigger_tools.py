from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Trigger-scoped MCP tool set selection (Mode S).

Every request to the aw MCP server sends the advertised tool schemas to the
model.  Skill-curation tools are almost always used inside ``heartbeat``
regular skill upkeep, so for ordinary interactive triggers (chat / inbox /
cron / task) we omit them and only expose the full set during
``heartbeat`` / ``consolidation`` runs where they are actually invoked.

The selection is intentionally provider-neutral and pure so it can be
reused both by the Agent SDK MCP server launcher (which computes the tool
set from the trigger and passes it to the subprocess via the
``ANIMAWORKS_MCP_TOOLS`` environment variable) and by the MCP server's
own ``list_tools`` handler.
"""

from collections.abc import Set

# Skill-management tools that are only needed during regular upkeep
# (heartbeat / consolidation).  They share no arguments with other tools
# and are additive, so omitting them for interactive triggers is safe.
SKILL_MANAGEMENT_TOOLS: frozenset[str] = frozenset(
    {
        "curate_skills",
        "archive_skill",
        "restore_skill",
        "block_skill",
        "unblock_skill",
        "delete_skill",
        "set_skill_lifecycle",
        "promote_procedure_to_skill",
    }
)


def is_full_tool_trigger(trigger: str) -> bool:
    """Return True when *trigger* should receive the full tool set.

    ``heartbeat`` (and its beat-stamped variants) and ``consolidation``
    perform skill upkeep and thus keep every tool.  An empty/unknown
    trigger keeps everything as a safe default (no behaviour change for
    standalone MCP usage).
    """
    if not trigger:
        return True
    return (
        trigger == "heartbeat"
        or trigger.startswith("heartbeat:")
        or trigger == "consolidation"
        or trigger.startswith("consolidation:")
    )


def scoped_tool_names(
    exposed: Set[str],
    trigger: str,
) -> Set[str]:
    """Return the tool-name subset to advertise for *trigger*.

    ``exposed`` is the full default exposed set (e.g. the MCP server's
    ``_EXPOSED_TOOL_NAMES``).  Non-full triggers drop the skill
    management tools; full triggers return the set unchanged.
    """
    if is_full_tool_trigger(trigger):
        return exposed
    return exposed - SKILL_MANAGEMENT_TOOLS


def scoped_tool_list(exposed: Set[str], trigger: str) -> str:
    """Comma-joined tool names for the ``ANIMAWORKS_MCP_TOOLS`` env var."""
    return ",".join(sorted(scoped_tool_names(exposed, trigger)))


__all__ = [
    "SKILL_MANAGEMENT_TOOLS",
    "is_full_tool_trigger",
    "scoped_tool_list",
    "scoped_tool_names",
]
