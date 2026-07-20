# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""P0-B index gap tests: cold catch-up + skills sparse fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.memory.rag.indexer import IndexDirectoryResult, MemoryIndexer
from core.memory.rag_search import RAGMemorySearch
from core.skills.curator import SkillCurator

# ── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "alice"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def common_knowledge_dir(tmp_path: Path) -> Path:
    d = tmp_path / "common_knowledge"
    d.mkdir()
    return d


@pytest.fixture
def common_skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "common_skills"
    d.mkdir()
    return d


@pytest.fixture
def rag(
    anima_dir: Path,
    common_knowledge_dir: Path,
    common_skills_dir: Path,
) -> RAGMemorySearch:
    return RAGMemorySearch(anima_dir, common_knowledge_dir, common_skills_dir)


def _write_skill(
    root: Path,
    name: str,
    *,
    body: str = "Deploy release safely",
    use_when: str = "general workflow",
) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {body}\n"
        f"use_when: [{use_when}]\n"
        "---\n\n"
        f"# {name}\n\n{body}\n",
        encoding="utf-8",
    )
    return skill_md


_SAMPLE_MD = "# Title\n\n## Section A\n\n" + ("body sentence with enough length to chunk. " * 5)


# ── Cold catch-up indexing ───────────────────────────────


class TestColdCatchupIndexing:
    def test_init_indexer_indexes_knowledge_episodes_skills(
        self,
        rag: RAGMemorySearch,
        anima_dir: Path,
    ) -> None:
        """Empty collection + source files → cold init indexes all three types."""
        knowledge_dir = anima_dir / "knowledge"
        knowledge_dir.mkdir()
        (knowledge_dir / "topic.md").write_text(_SAMPLE_MD, encoding="utf-8")

        episodes_dir = anima_dir / "episodes"
        episodes_dir.mkdir()
        (episodes_dir / "2026-07-01.md").write_text(_SAMPLE_MD, encoding="utf-8")

        skills_dir = anima_dir / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "deploy-helper")

        mock_indexer = MagicMock()
        mock_indexer.index_directory.return_value = IndexDirectoryResult(
            chunks_indexed=1,
            files_indexed=1,
        )
        mock_vector_store = MagicMock()

        with (
            patch(
                "core.memory.rag.singleton.get_vector_store",
                return_value=mock_vector_store,
            ),
            patch(
                "core.memory.rag.MemoryIndexer",
                return_value=mock_indexer,
            ),
        ):
            rag._init_indexer()

        types_called = {c.args[1] for c in mock_indexer.index_directory.call_args_list}
        assert "knowledge" in types_called
        assert "episodes" in types_called
        assert "skills" in types_called

        by_type = {c.args[1]: c.args[0] for c in mock_indexer.index_directory.call_args_list}
        assert by_type["knowledge"] == knowledge_dir
        assert by_type["episodes"] == episodes_dir
        assert by_type["skills"] == skills_dir

    def test_init_indexer_second_call_does_not_reindex(
        self,
        anima_dir: Path,
        common_knowledge_dir: Path,
        common_skills_dir: Path,
    ) -> None:
        """Second cold init skips re-embedding when hash matches and collection exists."""
        knowledge_dir = anima_dir / "knowledge"
        knowledge_dir.mkdir()
        (knowledge_dir / "topic.md").write_text(_SAMPLE_MD, encoding="utf-8")

        episodes_dir = anima_dir / "episodes"
        episodes_dir.mkdir()
        (episodes_dir / "2026-07-01.md").write_text(_SAMPLE_MD, encoding="utf-8")

        skills_dir = anima_dir / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "deploy-helper")

        mock_store = MagicMock()
        mock_store.upsert.return_value = True
        # After first index, collections exist so hash skip kicks in.
        known: list[str] = []

        def _list_collections() -> list[str]:
            return list(known)

        def _upsert(collection: str, documents: list) -> bool:
            if collection not in known:
                known.append(collection)
            return True

        mock_store.list_collections.side_effect = _list_collections
        mock_store.upsert.side_effect = _upsert

        def _make_real_indexer(vector_store, anima_name, anima_dir_arg, **kwargs):
            with patch.object(MemoryIndexer, "_init_embedding_model"):
                idx = MemoryIndexer(vector_store, anima_name, anima_dir_arg)
            idx._generate_embeddings = MagicMock(return_value=[[0.1] * 4])
            return idx

        with (
            patch(
                "core.memory.rag.singleton.get_vector_store",
                return_value=mock_store,
            ),
            patch(
                "core.memory.rag.MemoryIndexer",
                side_effect=_make_real_indexer,
            ),
        ):
            rag1 = RAGMemorySearch(anima_dir, common_knowledge_dir, common_skills_dir)
            rag1._init_indexer()
            first_upserts = mock_store.upsert.call_count
            assert first_upserts > 0

            rag2 = RAGMemorySearch(anima_dir, common_knowledge_dir, common_skills_dir)
            rag2._init_indexer()
            # Second init must not re-embed (index_meta hash + collection exists)
            assert mock_store.upsert.call_count == first_upserts


# ── Skills sparse fallback ───────────────────────────────


class TestSkillsKeywordFallback:
    def test_skills_keyword_fallback_returns_matches_when_vector_unavailable(
        self,
        rag: RAGMemorySearch,
        anima_dir: Path,
        common_knowledge_dir: Path,
        common_skills_dir: Path,
    ) -> None:
        """Vector unavailable → skills scope still returns SKILL.md keyword hits."""
        skills_dir = anima_dir / "skills"
        skills_dir.mkdir()
        _write_skill(
            skills_dir,
            "deploy-helper",
            body="Deploy release safely with checklist",
            use_when="deploy release",
        )
        _write_skill(
            skills_dir,
            "other-skill",
            body="Unrelated cooking recipe notes",
            use_when="kitchen cooking",
        )

        knowledge_dir = anima_dir / "knowledge"
        knowledge_dir.mkdir()
        episodes_dir = anima_dir / "episodes"
        episodes_dir.mkdir()
        procedures_dir = anima_dir / "procedures"
        procedures_dir.mkdir()

        with patch.object(rag, "_get_indexer", return_value=None):
            results = rag.search_memory_text(
                "deploy release",
                scope="skills",
                knowledge_dir=knowledge_dir,
                episodes_dir=episodes_dir,
                procedures_dir=procedures_dir,
                common_knowledge_dir=common_knowledge_dir,
            )

        sources = [r["source_file"] for r in results]
        assert any("deploy-helper" in s for s in sources)
        assert not any("other-skill" in s for s in sources)
        assert all(r["search_method"] == "keyword_fallback" for r in results)
        assert all(r["memory_type"] in ("skills", "common_skills") for r in results)

    def test_skills_keyword_fallback_excludes_curator_denied(
        self,
        rag: RAGMemorySearch,
        anima_dir: Path,
        common_knowledge_dir: Path,
        common_skills_dir: Path,
    ) -> None:
        """Archived/denied skills must not appear in sparse results."""
        skills_dir = anima_dir / "skills"
        skills_dir.mkdir()
        _write_skill(
            skills_dir,
            "active-skill",
            body="Deploy release workflow steps",
            use_when="deploy release",
        )
        _write_skill(
            skills_dir,
            "old-skill",
            body="Deploy release legacy workflow",
            use_when="deploy release",
        )
        SkillCurator(anima_dir).archive_skill("old-skill", reason="unused")

        knowledge_dir = anima_dir / "knowledge"
        knowledge_dir.mkdir()
        episodes_dir = anima_dir / "episodes"
        episodes_dir.mkdir()
        procedures_dir = anima_dir / "procedures"
        procedures_dir.mkdir()

        with patch.object(rag, "_get_indexer", return_value=None):
            results = rag.search_memory_text(
                "deploy release",
                scope="skills",
                knowledge_dir=knowledge_dir,
                episodes_dir=episodes_dir,
                procedures_dir=procedures_dir,
                common_knowledge_dir=common_knowledge_dir,
            )

        sources = [r["source_file"] for r in results]
        assert any("active-skill" in s for s in sources)
        assert not any("old-skill" in s for s in sources)

    def test_skills_keyword_fallback_includes_common_skills(
        self,
        rag: RAGMemorySearch,
        anima_dir: Path,
        common_knowledge_dir: Path,
        common_skills_dir: Path,
    ) -> None:
        """Shared common_skills are scanned in sparse skills search."""
        _write_skill(
            common_skills_dir,
            "shared-deploy",
            body="Shared deploy release handbook",
            use_when="deploy release",
        )

        knowledge_dir = anima_dir / "knowledge"
        knowledge_dir.mkdir()
        episodes_dir = anima_dir / "episodes"
        episodes_dir.mkdir()
        procedures_dir = anima_dir / "procedures"
        procedures_dir.mkdir()

        with patch.object(rag, "_get_indexer", return_value=None):
            results = rag.search_memory_text(
                "deploy release",
                scope="skills",
                knowledge_dir=knowledge_dir,
                episodes_dir=episodes_dir,
                procedures_dir=procedures_dir,
                common_knowledge_dir=common_knowledge_dir,
            )

        sources = [r["source_file"] for r in results]
        assert any("common_skills/shared-deploy/SKILL.md" == s or "shared-deploy" in s for s in sources)
        assert any(r["memory_type"] == "common_skills" for r in results)
