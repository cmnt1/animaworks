from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import json
import logging
from pathlib import Path

from core.skills.ledger import SkillLedger, rollback_skill_change
from core.skills.promotion import ProcedureToSkillConverter


def _personal_tree(tmp_path: Path) -> tuple[Path, Path]:
    data_dir = tmp_path
    anima_dir = data_dir / "animas" / "alice"
    anima_dir.mkdir(parents=True)
    return data_dir, anima_dir


def test_ledger_records_snapshot_and_rollback_restores_one_change(tmp_path: Path) -> None:
    data_dir, anima_dir = _personal_tree(tmp_path)
    skill_path = anima_dir / "skills" / "deploy" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    original = "# Deploy\n\nOriginal steps.\n"
    updated = "# Deploy\n\nUpdated steps.\n"
    skill_path.write_text(original, encoding="utf-8")

    skill_path.write_text(updated, encoding="utf-8")
    ledger = SkillLedger(anima_dir, data_dir=data_dir)
    entry = ledger.record_change(
        skill_path,
        before_text=original,
        after_text=updated,
        before_exists=True,
        after_exists=True,
        actor="alice",
        route="write_memory_file",
        reason="update runbook",
    )

    assert entry["skill_name"] == "deploy"
    assert entry["path"] == "skills/deploy/SKILL.md"
    assert entry["snapshot_path"] == f"state/skill_ledger/{entry['id']}.md"
    assert (anima_dir / entry["snapshot_path"]).read_text(encoding="utf-8") == original
    assert not (anima_dir / "skills" / "skill_ledger").exists()
    rows = [json.loads(line) for line in (anima_dir / "state" / "skill_ledger.jsonl").read_text().splitlines()]
    assert rows == [entry]

    succeeded, message = rollback_skill_change(entry, data_dir=data_dir, anima_dir=anima_dir)

    assert succeeded, message
    assert skill_path.read_text(encoding="utf-8") == original
    rollback_rows = ledger.read_entries()
    assert rollback_rows[-1]["route"] == "rollback"
    assert rollback_rows[-1]["reason"] == f"rollback of {entry['id']}"


def test_rollback_restores_deletion_and_removes_created_skill(tmp_path: Path) -> None:
    data_dir, anima_dir = _personal_tree(tmp_path)
    ledger = SkillLedger(anima_dir, data_dir=data_dir)
    skill_path = anima_dir / "skills" / "deploy" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)

    created = "# Newly created\n"
    skill_path.write_text(created, encoding="utf-8")
    create_entry = ledger.record_change(
        skill_path,
        before_text="",
        after_text=created,
        before_exists=False,
        after_exists=True,
        actor="alice",
        route="create_skill",
    )
    succeeded, message = rollback_skill_change(create_entry, data_dir=data_dir, anima_dir=anima_dir)
    assert succeeded, message
    assert not skill_path.exists()

    deleted = "# Deleted skill\n"
    skill_path.write_text(deleted, encoding="utf-8")
    skill_path.unlink()
    delete_entry = ledger.record_change(
        skill_path,
        before_text=deleted,
        after_text=None,
        before_exists=True,
        after_exists=False,
        actor="alice",
        route="archive_memory_file",
    )
    succeeded, message = rollback_skill_change(delete_entry, data_dir=data_dir, anima_dir=anima_dir)
    assert succeeded, message
    assert skill_path.read_text(encoding="utf-8") == deleted


def test_rollback_refuses_when_skill_changed_after_ledger_entry(tmp_path: Path) -> None:
    data_dir, anima_dir = _personal_tree(tmp_path)
    skill_path = anima_dir / "skills" / "deploy" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    original = "original\n"
    first_update = "first update\n"
    skill_path.write_text(original, encoding="utf-8")
    skill_path.write_text(first_update, encoding="utf-8")
    entry = SkillLedger(anima_dir, data_dir=data_dir).record_change(
        skill_path,
        before_text=original,
        after_text=first_update,
        before_exists=True,
        after_exists=True,
        actor="alice",
        route="write_memory_file",
    )
    later_update = "later update\n"
    skill_path.write_text(later_update, encoding="utf-8")

    succeeded, message = rollback_skill_change(entry, data_dir=data_dir, anima_dir=anima_dir)

    assert not succeeded
    assert "changed later" in message
    assert skill_path.read_text(encoding="utf-8") == later_update
    assert len(SkillLedger(anima_dir, data_dir=data_dir).read_entries()) == 1


def test_automatic_writer_skips_pinned_human_skill(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.INFO)
    anima_dir = tmp_path / "animas" / "alice"
    skill_path = anima_dir / "skills" / "handbook" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    original = "---\npinned: true\nauthor: human\n---\n\n# Human handbook\n"
    skill_path.write_text(original, encoding="utf-8")
    converter = ProcedureToSkillConverter(anima_dir)

    written = converter._write_skill_file(
        skill_path,
        {"name": "handbook", "description": "automated update"},
        "# Automated body",
        actor="autolearn",
        automatic=True,
    )

    assert not written
    assert skill_path.read_text(encoding="utf-8") == original
    assert "Automatic skill edit skipped" in caplog.text
    assert not (anima_dir / "state" / "skill_ledger.jsonl").exists()
