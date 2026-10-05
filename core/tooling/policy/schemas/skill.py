from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Skill and use_tool schemas."""

from typing import Any

from core.i18n import t as _t


def _create_skill_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": "create_skill",
            "description": _t("schema.create_skill.desc"),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": _t("schema.create_skill.skill_name"),
                    },
                    "description": {
                        "type": "string",
                        "description": _t("schema.create_skill.description"),
                    },
                    "body": {
                        "type": "string",
                        "description": _t("schema.create_skill.body"),
                    },
                    "location": {
                        "type": "string",
                        "enum": ["personal", "common"],
                        "description": _t("schema.create_skill.location"),
                    },
                    "references": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["filename", "content"],
                        },
                        "description": _t("schema.create_skill.references"),
                    },
                    "templates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["filename", "content"],
                        },
                        "description": _t("schema.create_skill.templates"),
                    },
                    "allowed_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": _t("schema.create_skill.allowed_tools"),
                    },
                    "trust_level": {
                        "type": "string",
                        "enum": ["builtin", "official", "trusted", "community", "untrusted"],
                        "description": "Trust level (default: trusted).",
                    },
                    "source_type": {
                        "type": "string",
                        "enum": ["local", "anima", "hub", "url"],
                        "description": "Where the skill came from (default: anima).",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category tag for classification.",
                    },
                    "source_origin": {
                        "type": "string",
                        "description": "Provenance origin (manual / auto_created).",
                    },
                    "promotion_status": {
                        "type": "string",
                        "description": "Promotion status (probation / trusted).",
                    },
                    "skill_policy": {
                        "type": "object",
                        "description": "Prompt policy (use_mode, injection fields).",
                    },
                    "use_when": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Positive routing use cases.",
                    },
                    "trigger_phrases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Phrases that activate this skill.",
                    },
                    "negative_phrases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Phrases that suppress this skill.",
                    },
                    "domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Routing domains.",
                    },
                    "routing_examples": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Example requests for routing evaluation.",
                    },
                },
                "required": ["skill_name", "description", "body"],
            },
        },
        {
            "name": "trust_skill",
            "description": "Promote an existing safe skill to trusted operating guidance after explicit human instruction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {
                        "type": "string",
                        "description": "Skill name or pointer such as skills/<name>/SKILL.md.",
                    },
                    "trust_reason": {
                        "type": "string",
                        "description": "Reason for promotion, default human_instruction.",
                    },
                },
                "required": ["ref"],
            },
        },
        {
            "name": "promote_procedure_to_skill",
            "description": (
                "Generate a skill draft from a successful procedure, or approve a quarantine draft. "
                "action='draft' writes skills/quarantine/<skill_name>/SKILL.md; action='approve' "
                "activates a reviewed draft (requires explicit human approval)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["draft", "approve"],
                        "description": "draft creates a quarantine SKILL.md; approve activates a reviewed draft.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Procedure path under procedures/ for action=draft.",
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "Optional draft name for draft; required quarantine name for approve.",
                    },
                    "approved_by": {
                        "type": "string",
                        "description": "Deprecated. Approval actor is read from the resolved interactive approval.",
                    },
                    "approval_callback_id": {
                        "type": "string",
                        "description": "Interactive approval callback_id, required for action=approve.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional replacement skill description for action=draft.",
                    },
                    "use_when": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Routing use-when phrases for the generated skill.",
                    },
                    "trigger_phrases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Trigger phrases for the generated skill.",
                    },
                    "negative_phrases": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Phrases that should suppress routing.",
                    },
                    "domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required routing domains for the generated skill.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags for the generated skill.",
                    },
                    "risk": {
                        "type": "object",
                        "description": (
                            "Optional risk metadata. external_send, destructive, or open_world "
                            "keep requires_human_approval=true after activation."
                        ),
                    },
                },
            },
        },
    ]


def _curator_skill_schemas() -> list[dict[str, Any]]:
    lifecycle_states = ["active", "review", "stale", "archived", "blocked", "deleted"]
    return [
        {
            "name": "curate_skills",
            "description": "Generate a deterministic Skill Curator report: lifecycle suggestions, metadata gaps, and duplicates.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "archive_skill",
            "description": "Append an archived lifecycle event for a skill and generate a reference rewrite proposal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "reason": {"type": "string"},
                    "absorbed_into": {
                        "type": "string",
                        "description": "Optional replacement skill when this archive is part of a merge.",
                    },
                },
                "required": ["skill_name", "reason"],
            },
        },
        {
            "name": "restore_skill",
            "description": "Append an active lifecycle event for a previously stale/archived skill when policy allows it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["skill_name", "reason"],
            },
        },
        {
            "name": "block_skill",
            "description": "Append a blocked lifecycle event for a skill and generate a reference rewrite proposal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["skill_name", "reason"],
            },
        },
        {
            "name": "unblock_skill",
            "description": "Append an active lifecycle event for a Curator-blocked skill when trust/security policy allows it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["skill_name", "reason"],
            },
        },
        {
            "name": "delete_skill",
            "description": "Append a deleted tombstone lifecycle event and generate a reference rewrite proposal; does not delete files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["skill_name", "reason"],
            },
        },
        {
            "name": "set_skill_lifecycle",
            "description": "Append a specific Skill Curator lifecycle transition.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string"},
                    "state": {"type": "string", "enum": lifecycle_states},
                    "reason": {"type": "string"},
                    "absorbed_into": {"type": "string"},
                },
                "required": ["skill_name", "state", "reason"],
            },
        },
    ]
