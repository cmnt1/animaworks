from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for recursive directory indexing (Issue #20).

Verifies that index_directory uses rglob for all memory types and
skills/common_skills only index SKILL.md.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("scipy")


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def temp_anima_dir():
    """Create a temp anima directory with subdirectory structures."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        anima_dir = base / "animas" / "test"
        anima_dir.mkdir(parents=True)

        # knowledge — flat (backward compat)
        kdir = anima_dir / "knowledge"
        kdir.mkdir()
        (kdir / "topic-a.md").write_text("# Topic A\n\nFlat knowledge file.\n")

        # common_knowledge — nested subdirectories
        ckdir = base / "common_knowledge"
        ckdir.mkdir()
        (ckdir / "top-level.md").write_text("# Top Level\n\nDirect file.\n")

        org_dir = ckdir / "organization"
        org_dir.mkdir()
        (org_dir / "structure.md").write_text("# Organization Structure\n\n## Hierarchy\nFlat org.\n")
        (org_dir / "roles.md").write_text("# Roles\n\n## Engineer\nWrites code.\n")

        comm_dir = ckdir / "communication"
        comm_dir.mkdir()
        (comm_dir / "messaging-guide.md").write_text("# Messaging Guide\n\n## DM Rules\nMax 2 per run.\n")

        # skills — nested SKILL.md + extra files that should NOT be indexed
        sdir = anima_dir / "skills"
        sdir.mkdir()
        skill1 = sdir / "deploy"
        skill1.mkdir()
        (skill1 / "SKILL.md").write_text("# Deploy Skill\n\nDeploy stuff.\n")
        (skill1 / "README.md").write_text("# Readme\n\nThis should not be indexed.\n")

        skill2 = sdir / "monitoring"
        skill2.mkdir()
        (skill2 / "SKILL.md").write_text("# Monitoring Skill\n\nMonitor stuff.\n")

        # common_skills — nested with templates that should NOT be indexed
        csdir = base / "common_skills"
        csdir.mkdir()
        cs1 = csdir / "skill-creator"
        cs1.mkdir()
        (cs1 / "SKILL.md").write_text("# Skill Creator\n\nCreate skills.\n")
        templates = cs1 / "templates"
        templates.mkdir()
        (templates / "template.md").write_text("# Template\n\nNot a skill.\n")

        # shared_users — nested user dirs
        shared = base / "shared"
        shared.mkdir()
        users_dir = shared / "users"
        users_dir.mkdir()
        user1 = users_dir / "alice"
        user1.mkdir()
        (user1 / "index.md").write_text("# Alice\n\nUser profile.\n")
        user2 = users_dir / "bob"
        user2.mkdir()
        (user2 / "index.md").write_text("# Bob\n\nAnother user.\n")

        yield {
            "base": base,
            "anima_dir": anima_dir,
            "common_knowledge": ckdir,
            "skills": sdir,
            "common_skills": csdir,
            "shared_users": users_dir,
        }


# ── Test: index_directory rglob for standard types ──────────────


def test_index_directory_finds_subdirectory_files(temp_anima_dir):
    """index_directory with rglob finds .md files in subdirectories."""
    ckdir = temp_anima_dir["common_knowledge"]

    mock_store = MagicMock()
    mock_store.create_collection = MagicMock()
    mock_store.upsert = MagicMock()

    from core.memory.rag.indexer import MemoryIndexer

    indexer = MemoryIndexer(
        mock_store,
        "shared",
        temp_anima_dir["base"],
    )
    indexer._generate_embeddings = MagicMock(side_effect=lambda texts, **kw: [[0.1] * 384 for _ in texts])

    chunks = indexer.index_directory(ckdir, "common_knowledge").chunks_indexed

    assert chunks > 0, "Should index files from subdirectories"
    upsert_calls = mock_store.upsert.call_args_list
    all_docs = []
    for call in upsert_calls:
        all_docs.extend(call[1]["documents"] if "documents" in call[1] else call[0][1])

    source_files = {d.metadata.get("source_file", "") for d in all_docs}
    assert any("organization" in sf for sf in source_files), (
        f"Expected subdirectory path in source_file, got: {source_files}"
    )


def test_index_directory_excludes_archive_subtree(temp_anima_dir):
    """Dense indexing ignores archive directories without relying on .ragignore."""
    knowledge_dir = temp_anima_dir["anima_dir"] / "knowledge"
    archived = knowledge_dir / "archive" / "old.md"
    archived.parent.mkdir()
    archived.write_text("# Archived\n\nMust not be embedded.\n", encoding="utf-8")

    mock_store = MagicMock()
    mock_store.create_collection = MagicMock()
    mock_store.upsert = MagicMock()

    from core.memory.rag.indexer import MemoryIndexer

    indexer = MemoryIndexer(mock_store, "test", temp_anima_dir["anima_dir"])
    indexer._generate_embeddings = MagicMock(side_effect=lambda texts, **kw: [[0.1] * 384 for _ in texts])
    index_file = MagicMock(side_effect=indexer.index_file)
    indexer.index_file = index_file
    result = indexer.index_directory(knowledge_dir, "knowledge")

    assert result.files_indexed == 1
    index_file.assert_called_once_with(knowledge_dir / "topic-a.md", "knowledge", force=False)


# ── Test: skills only index SKILL.md ────────────────────────────


def test_index_directory_skills_only_skill_md(temp_anima_dir):
    """index_directory for skills type only indexes SKILL.md files."""
    sdir = temp_anima_dir["skills"]

    mock_store = MagicMock()
    mock_store.create_collection = MagicMock()
    mock_store.upsert = MagicMock()

    from core.memory.rag.indexer import MemoryIndexer

    indexer = MemoryIndexer(
        mock_store,
        "test",
        temp_anima_dir["anima_dir"],
    )
    indexer._generate_embeddings = MagicMock(side_effect=lambda texts, **kw: [[0.1] * 384 for _ in texts])

    chunks = indexer.index_directory(sdir, "skills").chunks_indexed

    assert chunks > 0, "Should index SKILL.md files"

    upsert_calls = mock_store.upsert.call_args_list
    all_docs = []
    for call in upsert_calls:
        all_docs.extend(call[1]["documents"] if "documents" in call[1] else call[0][1])

    for doc in all_docs:
        sf = doc.metadata.get("source_file", "")
        assert "SKILL.md" in sf, f"Skills should only index SKILL.md, got: {sf}"
        assert "README" not in sf, f"README.md should not be indexed, got: {sf}"


def test_index_directory_common_skills_excludes_templates(temp_anima_dir):
    """index_directory for common_skills excludes template .md files."""
    csdir = temp_anima_dir["common_skills"]

    mock_store = MagicMock()
    mock_store.create_collection = MagicMock()
    mock_store.upsert = MagicMock()

    from core.memory.rag.indexer import MemoryIndexer

    indexer = MemoryIndexer(
        mock_store,
        "shared",
        temp_anima_dir["base"],
    )
    indexer._generate_embeddings = MagicMock(side_effect=lambda texts, **kw: [[0.1] * 384 for _ in texts])

    chunks = indexer.index_directory(csdir, "common_skills").chunks_indexed

    assert chunks > 0, "Should index SKILL.md in common_skills"

    upsert_calls = mock_store.upsert.call_args_list
    all_docs = []
    for call in upsert_calls:
        all_docs.extend(call[1]["documents"] if "documents" in call[1] else call[0][1])

    for doc in all_docs:
        sf = doc.metadata.get("source_file", "")
        assert "template" not in sf.lower(), f"Template files should not be indexed, got: {sf}"


# ── Test: shared_users indexing ─────────────────────────────────


def test_index_directory_shared_users_finds_nested(temp_anima_dir):
    """index_directory indexes user profiles in {username}/index.md."""
    users_dir = temp_anima_dir["shared_users"]

    mock_store = MagicMock()
    mock_store.create_collection = MagicMock()
    mock_store.upsert = MagicMock()

    shared_base = temp_anima_dir["base"] / "shared"
    from core.memory.rag.indexer import MemoryIndexer

    indexer = MemoryIndexer(
        mock_store,
        "shared",
        shared_base,
    )
    indexer._generate_embeddings = MagicMock(side_effect=lambda texts, **kw: [[0.1] * 384 for _ in texts])

    chunks = indexer.index_directory(users_dir, "shared_users").chunks_indexed

    assert chunks > 0, "Should index nested user profile files"
