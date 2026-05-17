from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for legacy flat personal skill read handling."""

from pathlib import Path
from unittest.mock import MagicMock

from core.skills.usage import SkillUsageTracker
from core.tooling.handler_memory import MemoryToolsMixin


def _memory_mixin(anima_dir: Path) -> MagicMock:
    mixin = MagicMock(spec=MemoryToolsMixin)
    mixin._anima_dir = anima_dir
    mixin._superuser = False
    mixin._subordinate_activity_dirs = []
    mixin._subordinate_management_files = []
    mixin._descendant_activity_dirs = []
    mixin._descendant_state_files = []
    mixin._descendant_state_dirs = []
    mixin._read_paths = set()
    mixin._is_skill_path = MemoryToolsMixin._is_skill_path
    mixin._is_flat_personal_skill_path = MemoryToolsMixin._is_flat_personal_skill_path
    mixin._record_skill_view_if_applicable = lambda rel: MemoryToolsMixin._record_skill_view_if_applicable(mixin, rel)
    return mixin


def test_read_memory_file_gates_and_tracks_flat_personal_skill(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    skills_dir = anima_dir / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / "flat-skill.md").write_text(
        "---\nname: flat-skill\ndescription: Flat skill\n---\n\n# Flat Skill\n",
        encoding="utf-8",
    )
    (skills_dir / "blocked-flat.md").write_text(
        "---\nname: blocked-flat\ndescription: Blocked flat\ntrust_level: blocked\n---\n\n# Blocked\n",
        encoding="utf-8",
    )
    nested_note = skills_dir / "flat-skill" / "references" / "note.md"
    nested_note.parent.mkdir(parents=True)
    nested_note.write_text("# Reference note\n", encoding="utf-8")

    mixin = _memory_mixin(anima_dir)

    allowed = MemoryToolsMixin._handle_read_memory_file(mixin, {"path": "skills/flat-skill.md"})
    assert "# Flat Skill" in allowed
    assert SkillUsageTracker(anima_dir).get_stats("flat-skill").view_count == 1

    blocked = MemoryToolsMixin._handle_read_memory_file(mixin, {"path": "skills/blocked-flat.md"})
    assert "SkillBlocked" in blocked
    assert "trust_level_blocked" in blocked

    nested = MemoryToolsMixin._handle_read_memory_file(mixin, {"path": "skills/flat-skill/references/note.md"})
    assert "# Reference note" in nested
    assert SkillUsageTracker(anima_dir).get_stats("note").view_count == 0
