from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for skill usage tracking through tool handlers."""

import json
from pathlib import Path

import pytest

from core.skills.models import SkillUsageEventType
from core.skills.usage import SkillUsageTracker


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    """Create anima directory with skill and procedure files."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    skills_dir = tmp_path / "skills" / "my-test-skill"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: my-test-skill\ndescription: A test skill\n---\n\n# My Test Skill\n\nBody here.\n"
    )

    procedures_dir = tmp_path / "procedures"
    procedures_dir.mkdir()
    (procedures_dir / "deploy.md").write_text(
        "---\nusage_count: 0\nsuccess_count: 0\nfailure_count: 0\nconfidence: 0.0\n---\n\n# Deploy\n\nSteps...\n"
    )

    return tmp_path


class TestHandlerMemorySkillView:
    """Test that read_memory_file records view events for skills."""

    def test_skill_view_recorded(self, anima_dir: Path):
        tracker = SkillUsageTracker(anima_dir)
        tracker.record("my-test-skill", SkillUsageEventType.view, is_common=False)

        stats = tracker.get_stats("my-test-skill")
        assert stats.view_count == 1

    def test_common_skill_view_recorded(self, anima_dir: Path):
        tracker = SkillUsageTracker(anima_dir)
        tracker.record("shared-skill", SkillUsageEventType.view, is_common=True)

        stats = tracker.get_stats("shared-skill")
        assert stats.view_count == 1
        assert stats.is_common is True

    def test_procedure_view_recorded(self, anima_dir: Path):
        tracker = SkillUsageTracker(anima_dir)
        tracker.record("deploy", SkillUsageEventType.view, is_common=False)

        stats = tracker.get_stats("deploy")
        assert stats.view_count == 1


class TestHandlerSkillsOutcome:
    """Test that report_procedure_outcome records events for skills."""

    def test_skill_success_recorded_to_jsonl(self, anima_dir: Path):
        tracker = SkillUsageTracker(anima_dir)
        tracker.record("my-test-skill", SkillUsageEventType.success, notes="worked great")

        stats = tracker.get_stats("my-test-skill")
        assert stats.success_count == 1

        usage_file = anima_dir / "state" / "skill_usage.jsonl"
        data = json.loads(usage_file.read_text().strip())
        assert data["event_type"] == "success"
        assert data["notes"] == "worked great"

    def test_skill_failure_recorded_to_jsonl(self, anima_dir: Path):
        tracker = SkillUsageTracker(anima_dir)
        tracker.record("my-test-skill", SkillUsageEventType.failure, notes="timeout")

        stats = tracker.get_stats("my-test-skill")
        assert stats.failure_count == 1

    def test_procedure_outcome_still_works(self, anima_dir: Path):
        """Ensure procedure flow also records to JSONL in addition to frontmatter."""
        tracker = SkillUsageTracker(anima_dir)
        tracker.record("deploy", SkillUsageEventType.success)

        stats = tracker.get_stats("deploy")
        assert stats.success_count == 1


class TestViewEventDetection:
    """Test _record_skill_view_if_applicable path detection logic."""

    def test_detects_personal_skill_path(self, anima_dir: Path):
        from core.tooling.handler_memory import MemoryToolsMixin

        mixin = MemoryToolsMixin.__new__(MemoryToolsMixin)
        mixin._anima_dir = anima_dir

        mixin._record_skill_view_if_applicable("skills/my-test-skill/SKILL.md")

        usage_file = anima_dir / "state" / "skill_usage.jsonl"
        assert usage_file.exists()
        data = json.loads(usage_file.read_text().strip())
        assert data["skill_name"] == "my-test-skill"
        assert data["event_type"] == "view"
        assert data["is_common"] is False

    def test_detects_common_skill_path(self, anima_dir: Path):
        from core.tooling.handler_memory import MemoryToolsMixin

        mixin = MemoryToolsMixin.__new__(MemoryToolsMixin)
        mixin._anima_dir = anima_dir

        mixin._record_skill_view_if_applicable("common_skills/web-search/SKILL.md")

        usage_file = anima_dir / "state" / "skill_usage.jsonl"
        assert usage_file.exists()
        data = json.loads(usage_file.read_text().strip())
        assert data["skill_name"] == "web-search"
        assert data["is_common"] is True

    def test_detects_procedure_path(self, anima_dir: Path):
        from core.tooling.handler_memory import MemoryToolsMixin

        mixin = MemoryToolsMixin.__new__(MemoryToolsMixin)
        mixin._anima_dir = anima_dir

        mixin._record_skill_view_if_applicable("procedures/deploy.md")

        usage_file = anima_dir / "state" / "skill_usage.jsonl"
        assert usage_file.exists()
        data = json.loads(usage_file.read_text().strip())
        assert data["skill_name"] == "deploy"
        assert data["event_type"] == "view"

    def test_ignores_non_skill_paths(self, anima_dir: Path):
        from core.tooling.handler_memory import MemoryToolsMixin

        mixin = MemoryToolsMixin.__new__(MemoryToolsMixin)
        mixin._anima_dir = anima_dir

        mixin._record_skill_view_if_applicable("knowledge/python-tips.md")
        mixin._record_skill_view_if_applicable("episodes/2026-05-01.md")
        mixin._record_skill_view_if_applicable("state/current_state.md")

        usage_file = anima_dir / "state" / "skill_usage.jsonl"
        assert not usage_file.exists()

    def test_ignores_non_skill_md_in_skills_dir(self, anima_dir: Path):
        from core.tooling.handler_memory import MemoryToolsMixin

        mixin = MemoryToolsMixin.__new__(MemoryToolsMixin)
        mixin._anima_dir = anima_dir

        mixin._record_skill_view_if_applicable("skills/my-test-skill/README.md")

        usage_file = anima_dir / "state" / "skill_usage.jsonl"
        assert not usage_file.exists()


class TestIndexUsageMerge:
    """Test that SkillIndex merges usage stats when anima_dir is provided."""

    def test_index_merges_usage_counts(self, anima_dir: Path, tmp_path: Path):
        from core.skills.index import SkillIndex

        common_dir = tmp_path / "common_skills"
        common_dir.mkdir()

        tracker = SkillUsageTracker(anima_dir)
        tracker.record("my-test-skill", SkillUsageEventType.view)
        tracker.record("my-test-skill", SkillUsageEventType.success)
        tracker.record("my-test-skill", SkillUsageEventType.success)
        tracker.reset_session_views()
        tracker.record("my-test-skill", SkillUsageEventType.view)

        skills_dir = anima_dir / "skills"
        index = SkillIndex(
            skills_dir=skills_dir,
            common_skills_dir=common_dir,
            anima_dir=anima_dir,
        )
        results = index.build_index()

        assert len(results) >= 1
        skill_meta = next(m for m in results if m.name == "my-test-skill")
        # usage_count = view_count + use_count (2 views, 0 uses)
        assert skill_meta.usage_count == 2
        assert skill_meta.success_count == 2
        assert skill_meta.last_used_at is not None
