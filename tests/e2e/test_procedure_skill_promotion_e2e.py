from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for procedure-to-skill promotion."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from core.memory.frontmatter import parse_frontmatter
from core.skills.index import SkillIndex
from core.skills.promotion import ProcedureToSkillConverter
from core.time_utils import now_iso
from core.tooling.handler import ToolHandler
from core.tooling.schemas import build_tool_list


def _write_procedure(anima_dir: Path) -> None:
    procedures = anima_dir / "procedures"
    procedures.mkdir(parents=True, exist_ok=True)
    (procedures / "incident-summary.md").write_text(
        "---\n"
        "name: incident-summary\n"
        "description: Summarize an incident safely\n"
        "success_count: 4\n"
        "failure_count: 0\n"
        "confidence: 0.9\n"
        f"last_used: {now_iso()}\n"
        "domains: [operations]\n"
        "trigger_phrases: [incident summary]\n"
        "---\n\n"
        "# Incident Summary\n\n"
        "1. Read the incident notes.\n"
        "2. Summarize impact and next actions.\n",
        encoding="utf-8",
    )


def test_promotion_flow_activates_only_after_approval(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    common_skills = tmp_path / "common_skills"
    common_skills.mkdir(parents=True)
    (anima_dir / "skills").mkdir(parents=True)
    _write_procedure(anima_dir)

    converter = ProcedureToSkillConverter(anima_dir)
    draft = converter.create_quarantine_skill("procedures/incident-summary.md")
    assert draft.status == "review"

    index = SkillIndex(anima_dir / "skills", common_skills, anima_dir / "procedures", anima_dir=anima_dir)
    assert "incident-summary" not in {skill.name for skill in index.all_skills if not skill.is_procedure}

    approved = converter.approve_skill("incident-summary", approved_by="ops-lead")
    assert approved.status == "active"

    index.invalidate()
    names = {skill.name for skill in index.all_skills if not skill.is_procedure}
    assert "incident-summary" in names

    meta, _body = parse_frontmatter((anima_dir / "skills" / "incident-summary" / "SKILL.md").read_text("utf-8"))
    assert meta["trust_level"] == "trusted"
    assert meta["promotion_status"] == "active"
    assert meta["approved_by"] == "ops-lead"


def test_tool_handler_promotes_and_approves_procedure(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    (anima_dir / "skills").mkdir(parents=True)
    _write_procedure(anima_dir)

    memory = MagicMock()
    memory.read_permissions.return_value = ""
    memory.search_memory_text.return_value = []
    handler = ToolHandler(anima_dir=anima_dir, memory=memory, messenger=None, tool_registry=[])

    draft_text = handler.handle(
        "promote_procedure_to_skill",
        {"path": "procedures/incident-summary.md", "skill_name": "incident-summary"},
    )
    draft = json.loads(draft_text)
    assert draft["status"] == "review"
    assert (anima_dir / "skills" / "quarantine" / "incident-summary" / "SKILL.md").exists()

    approved_text = handler.handle(
        "promote_procedure_to_skill",
        {"action": "approve", "skill_name": "incident-summary", "approved_by": "ops-lead"},
    )
    approved = json.loads(approved_text)
    assert approved["status"] == "active"
    assert (anima_dir / "skills" / "incident-summary" / "SKILL.md").exists()


def test_tool_schema_exposes_promotion_tool() -> None:
    tools = build_tool_list(include_create_skill=True)
    names = {tool["name"] for tool in tools}
    assert "create_skill" in names
    assert "promote_procedure_to_skill" in names
