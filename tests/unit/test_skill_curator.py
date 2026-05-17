from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Skill Curator lifecycle management."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from core.memory.frontmatter import parse_frontmatter
from core.skills.curator import SkillCurator
from core.skills.index import SkillIndex
from core.skills.models import SkillLifecycleState, SkillMetadata, SkillUsageEventType
from core.skills.router import SkillRouter
from core.skills.usage import SkillUsageTracker
from core.tooling.handler_memory import MemoryToolsMixin


def _write_skill(
    anima_dir: Path,
    name: str,
    *,
    description: str = "Deploy release safely",
    extra: str = "",
) -> Path:
    skill_dir = anima_dir / "skills" / name
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "use_when: [deploy release]\n"
        "trigger_phrases: [deploy release]\n"
        "domains: [software-delivery]\n"
        f"{extra}"
        "---\n\n"
        f"# {name}\n",
        encoding="utf-8",
    )
    return skill_md


def test_replay_state_restores_latest_lifecycle_state(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    curator = SkillCurator(anima_dir)

    curator.archive_skill("old-skill", reason="unused", actor="mei")
    curator.restore_skill("old-skill", reason="needed", actor="mei")

    replay = curator.replay_state()
    assert replay.states["old-skill"] == SkillLifecycleState.active
    assert len(replay.events) == 2


def test_usage_stats_drive_lifecycle_suggestions_and_protected_skips_archive(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    old = SkillMetadata(name="old", last_used_at=datetime.now(UTC) - timedelta(days=181))
    protected = SkillMetadata(name="protected-old", protected=True, last_used_at=datetime.now(UTC) - timedelta(days=181))
    flaky = SkillMetadata(name="flaky")
    patched = SkillMetadata(name="patched")
    tracker = SkillUsageTracker(anima_dir)
    for _ in range(7):
        tracker.record("flaky", SkillUsageEventType.failure)
    for _ in range(3):
        tracker.record("flaky", SkillUsageEventType.success)
    for _ in range(5):
        tracker.record("patched", SkillUsageEventType.patch)

    suggestions = SkillCurator(anima_dir).suggest_lifecycle_transitions([old, protected, flaky, patched])
    by_name = {s.skill_name: s for s in suggestions}

    assert by_name["old"].suggested_state == SkillLifecycleState.archived
    assert "protected-old" not in by_name
    assert by_name["flaky"].suggested_state == SkillLifecycleState.review
    assert by_name["patched"].reason == "patch_count_consolidation"


def test_duplicate_detector_uses_routing_and_lexical_signals(tmp_path: Path) -> None:
    curator = SkillCurator(tmp_path / "alice")
    left = SkillMetadata(
        name="gmail-draft",
        description="Draft concise Gmail replies for partners",
        trigger_phrases=["gmail draft", "partner reply"],
        domains=["email"],
    )
    right = SkillMetadata(
        name="gmail-reply-drafts",
        description="Draft Gmail replies for partner email",
        trigger_phrases=["gmail draft", "partner reply"],
        domains=["email"],
    )

    duplicates = curator.detect_duplicates([left, right])

    assert duplicates
    assert "routing_metadata_overlap" in duplicates[0].signals
    assert "description_lexical_overlap" in duplicates[0].signals


def test_index_router_and_read_memory_file_block_curator_archived_skill(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    common_dir = tmp_path / "common_skills"
    common_dir.mkdir()
    _write_skill(anima_dir, "old-skill")
    _write_skill(anima_dir, "new-skill", description="Deploy release safely with new workflow")
    SkillCurator(anima_dir).archive_skill("old-skill", reason="unused", actor="curator")

    index = SkillIndex(anima_dir / "skills", common_dir, anima_dir=anima_dir)
    names = {meta.name for meta in index.all_skills}
    assert "old-skill" not in names
    assert "new-skill" in names

    all_entries = index.search("", include_blocked=True)
    routed = SkillRouter(min_score=0.1).route("deploy release", all_entries, top_k=5)
    assert "old-skill" not in {candidate.name for candidate in routed}

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
    mixin._record_skill_view_if_applicable = MagicMock()

    result = MemoryToolsMixin._handle_read_memory_file(mixin, {"path": "skills/old-skill/SKILL.md"})
    assert "SkillBlocked" in result
    assert "curator_archived" in result


def test_restore_refuses_trust_blocked_skill(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    _write_skill(anima_dir, "danger", extra="trust_level: blocked\n")
    curator = SkillCurator(anima_dir)

    try:
        curator.restore_skill("danger", reason="try restore")
    except ValueError as exc:
        assert "cannot be restored" in str(exc)
    else:
        raise AssertionError("Expected trust-blocked skill restore to fail")


def test_archive_generates_reference_rewrite_proposal(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    (anima_dir / "cron.md").write_text(
        "## Daily\nschedule: 0 9 * * *\nskills:\n  - old-skill\n  - new-skill\nDo work.\n",
        encoding="utf-8",
    )

    event = SkillCurator(anima_dir).archive_skill(
        "old-skill",
        reason="merged",
        absorbed_into="new-skill",
    )

    assert event.absorbed_into == "new-skill"
    assert event.proposal_path
    proposal = anima_dir / event.proposal_path
    assert proposal.exists()
    assert "- old-skill" in proposal.read_text(encoding="utf-8")


def test_curator_state_is_append_only_and_does_not_rewrite_skill_md(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    skill_md = _write_skill(anima_dir, "stable")
    before_meta, before_body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))

    SkillCurator(anima_dir).archive_skill("stable", reason="unused")

    after_meta, after_body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    assert after_meta == before_meta
    assert after_body == before_body


def test_rag_indexer_skips_archived_skill(tmp_path: Path) -> None:
    from core.memory.rag.indexer import MemoryIndexer

    anima_dir = tmp_path / "alice"
    skill_md = _write_skill(anima_dir, "old-skill")
    SkillCurator(anima_dir).archive_skill("old-skill", reason="unused")
    vector_store = MagicMock()
    indexer = MemoryIndexer(vector_store, "alice", anima_dir, embedding_model=MagicMock())

    chunks = indexer.index_file(skill_md, memory_type="skills", force=True)

    assert chunks == 0
    vector_store.create_collection.assert_not_called()
    vector_store.upsert.assert_not_called()
