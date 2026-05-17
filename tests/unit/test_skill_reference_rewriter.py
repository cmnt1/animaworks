from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for skill reference rewrite proposals."""

import json
from pathlib import Path

from core.skills.reference_rewriter import collect_reference_rewrite_changes, rewrite_skill_references_in_text


def test_absorbed_into_replaces_cron_skill_pointer_without_duplicates() -> None:
    text = (
        "## Daily\n"
        "schedule: 0 9 * * *\n"
        "skills:\n"
        "  - old-skill\n"
        "  - umbrella-skill\n"
        "  - other-skill\n"
        "Run daily.\n"
    )

    rewritten = rewrite_skill_references_in_text(text, "old-skill", absorbed_into="umbrella-skill")

    assert "old-skill" not in rewritten
    assert rewritten.count("umbrella-skill") == 1
    assert "other-skill" in rewritten


def test_archive_without_absorbed_into_removes_empty_skills_field() -> None:
    text = "## Daily\nskills: [old-skill]\nDo work.\n"

    rewritten = rewrite_skill_references_in_text(text, "old-skill", absorbed_into=None)

    assert "skills:" not in rewritten
    assert "old-skill" not in rewritten
    assert "Do work." in rewritten


def test_jsonl_task_skill_pointer_rewrite(tmp_path: Path) -> None:
    task = {
        "task_id": "t1",
        "meta": {
            "skills": ["old-skill", "umbrella-skill"],
            "skill_name": "old-skill",
        },
    }
    text = json.dumps(task, ensure_ascii=False) + "\n"

    rewritten = rewrite_skill_references_in_text(text, "old-skill", absorbed_into="umbrella-skill")
    parsed = json.loads(rewritten)

    assert parsed["meta"]["skills"] == ["umbrella-skill"]
    assert parsed["meta"]["skill_name"] == "umbrella-skill"


def test_collect_reference_rewrite_changes_covers_cron_and_task_queue(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    (anima_dir / "state").mkdir(parents=True)
    (anima_dir / "cron.md").write_text("## Daily\nskills: [old-skill, kept]\n", encoding="utf-8")
    (anima_dir / "state" / "task_queue.jsonl").write_text(
        json.dumps({"task_id": "t1", "meta": {"skills": ["old-skill"]}}) + "\n",
        encoding="utf-8",
    )

    changes = collect_reference_rewrite_changes(anima_dir, "old-skill", absorbed_into=None)

    assert {change.path for change in changes} == {"cron.md", "state/task_queue.jsonl"}
    assert all("old-skill" in change.before for change in changes)
    assert all("old-skill" not in change.after for change in changes)
