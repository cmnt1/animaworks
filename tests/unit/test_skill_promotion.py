from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for procedure-to-skill promotion."""

import json
from pathlib import Path

from core.memory.frontmatter import parse_frontmatter
from core.skills.promotion import (
    PROMOTION_DRAFT_CREATED,
    ProcedureToSkillConverter,
)
from core.time_utils import now_iso


def _write_procedure(anima_dir: Path, name: str, *, body: str = "Step 1: Do the safe thing.") -> Path:
    procedures = anima_dir / "procedures"
    procedures.mkdir(parents=True, exist_ok=True)
    path = procedures / f"{name}.md"
    path.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: Procedure for {name}\n"
        "success_count: 3\n"
        "failure_count: 0\n"
        "confidence: 0.95\n"
        f"last_used: {now_iso()}\n"
        "domains: [operations]\n"
        "trigger_phrases: [run deploy]\n"
        "---\n\n"
        f"# {name}\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_find_candidates_uses_policy_thresholds(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    procedure = _write_procedure(anima_dir, "deploy-flow")

    converter = ProcedureToSkillConverter(anima_dir)
    candidate = converter.candidate_from_path(procedure)

    assert candidate is not None
    assert candidate.eligible is True
    assert converter.find_candidates() == [candidate]


def test_draft_creates_quarantine_skill_with_required_metadata(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    _write_procedure(anima_dir, "deploy-flow")

    result = ProcedureToSkillConverter(anima_dir).create_quarantine_skill("procedures/deploy-flow.md")

    assert result.status == "review"
    assert result.requires_human_approval is True
    assert not (anima_dir / "skills" / "deploy-flow" / "SKILL.md").exists()

    skill_md = anima_dir / result.quarantine_path
    meta, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    assert meta["trust_level"] == "quarantine"
    assert meta["promotion_status"] == "review"
    assert meta["source"]["type"] == "anima"
    assert meta["source"]["origin"] == "procedure_promotion"
    assert meta["version"] == 1
    assert meta["use_when"]
    assert meta["trigger_phrases"]
    assert meta["negative_phrases"] == []
    assert meta["domains"] == ["operations"]
    assert meta["security"]["scan_status"] == "scanned"
    assert "## Pitfalls" in body
    assert "## Verification" in body

    audit_line = (anima_dir / "state" / "skill_promotion.jsonl").read_text(encoding="utf-8").splitlines()[0]
    audit = json.loads(audit_line)
    assert audit["event_type"] == PROMOTION_DRAFT_CREATED
    assert audit["skill_name"] == "deploy-flow"


def test_dangerous_draft_aborts_before_quarantine(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    _write_procedure(anima_dir, "dangerous-flow", body="Run rm -rf / before continuing.")

    result = ProcedureToSkillConverter(anima_dir).create_quarantine_skill("procedures/dangerous-flow.md")

    assert result.status == "blocked"
    assert result.scan_verdict == "dangerous"
    assert not (anima_dir / "skills" / "quarantine" / "dangerous-flow").exists()
    assert not (anima_dir / "skills" / "dangerous-flow").exists()


def test_approve_moves_skill_to_active_and_records_create_event(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    _write_procedure(anima_dir, "deploy-flow")
    converter = ProcedureToSkillConverter(anima_dir)
    converter.create_quarantine_skill("procedures/deploy-flow.md")

    result = converter.approve_skill("deploy-flow", approved_by="mei")

    assert result.status == "active"
    assert not (anima_dir / "skills" / "quarantine" / "deploy-flow").exists()
    active_skill = anima_dir / "skills" / "deploy-flow" / "SKILL.md"
    assert active_skill.exists()
    meta, _body = parse_frontmatter(active_skill.read_text(encoding="utf-8"))
    assert meta["trust_level"] == "trusted"
    assert meta["promotion_status"] == "active"
    assert meta["approved_by"] == "mei"
    assert meta["approved_at"]

    usage_lines = (anima_dir / "state" / "skill_usage.jsonl").read_text(encoding="utf-8").splitlines()
    usage = json.loads(usage_lines[-1])
    assert usage["skill_name"] == "deploy-flow"
    assert usage["event_type"] == "create"


def test_external_send_risk_keeps_runtime_human_approval(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    _write_procedure(anima_dir, "send-status")
    converter = ProcedureToSkillConverter(anima_dir)
    converter.create_quarantine_skill(
        "procedures/send-status.md",
        metadata_overrides={"risk": {"external_send": True}},
    )

    converter.approve_skill("send-status", approved_by="mei")

    meta, _body = parse_frontmatter((anima_dir / "skills" / "send-status" / "SKILL.md").read_text(encoding="utf-8"))
    assert meta["risk"]["external_send"] is True
    assert meta["risk"]["requires_human_approval"] is True
