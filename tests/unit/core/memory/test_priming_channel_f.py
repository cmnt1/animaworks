from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for Channel F: Episodes vector search in PrimingEngine."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.memory.priming import PrimingEngine, PrimingResult, format_priming_section
from core.memory.priming.channel_f import exclude_episodes_for_dates, format_episode_pointer
from core.memory.priming.items import MemoryItem


@pytest.fixture
def temp_anima_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        anima_dir = Path(tmpdir) / "animas" / "test_anima"
        anima_dir.mkdir(parents=True)
        (anima_dir / "episodes").mkdir()
        (anima_dir / "knowledge").mkdir()
        (anima_dir / "skills").mkdir()
        yield anima_dir


# ── PrimingResult field ──────────────────────────────────


class TestPrimingResultEpisodesField:
    def test_episodes_included_in_total_chars(self) -> None:
        result = PrimingResult(episodes="過去の経験")
        assert result.total_chars() == len("過去の経験")

    def test_is_empty_false_when_episodes_set(self) -> None:
        result = PrimingResult(episodes="something")
        assert not result.is_empty()

    def test_is_empty_true_when_all_empty(self) -> None:
        result = PrimingResult()
        assert result.is_empty()


# ── Pointer formatting ──────────────────────────────────


class TestFormatEpisodePointer:
    def test_one_line_score_path_summary(self) -> None:
        out = format_episode_pointer(
            index=1,
            score=0.81,
            source="episodes/2026-09-03.md",
            content="# リリース",
            path="episodes/2026-09-03.md",
        )
        assert out == "📌 [0.81] episodes/2026-09-03.md — リリース"

    def test_show_body_prefixes_pointer_line(self) -> None:
        out = format_episode_pointer(
            index=1,
            score=0.81,
            source="episodes/2026-09-03.md",
            content="# リリース\n本文内容",
            path="episodes/2026-09-03.md",
            show_body=True,
        )
        assert out.startswith("# リリース")
        assert "📌 [0.81] episodes/2026-09-03.md — リリース" in out


class TestExcludeEpisodesForDates:
    def test_excludes_same_date_episodes(self) -> None:
        items = [
            MemoryItem("episodes", "episodes/2026-09-03.md", "t", ref="episodes/2026-09-03.md"),
            MemoryItem("episodes", "episodes/2026-09-01.md", "t", ref="episodes/2026-09-01.md"),
        ]
        kept = exclude_episodes_for_dates(items, {"2026-09-03"})
        assert [item.ref for item in kept] == ["episodes/2026-09-01.md"]

    def test_no_dates_keeps_all(self) -> None:
        items = [MemoryItem("episodes", "episodes/2026-09-03.md", "t", ref="episodes/2026-09-03.md")]
        assert exclude_episodes_for_dates(items, set()) == items


# ── Channel F search ─────────────────────────────────────


class TestChannelFEpisodes:
    def _patch_unified_search(
        self,
        results: list,
        *,
        meta: dict | None = None,
        side_effect: Exception | None = None,
    ):
        searcher = MagicMock()
        if side_effect is None:
            searcher.search_many.return_value = [self._to_unified_row(result) for result in results]
        else:
            searcher.search_many.side_effect = side_effect
        searcher.last_search_meta = meta or {"abstain": False, "abstain_reason": ""}
        return patch("core.memory.priming.channel_f.UnifiedMemorySearch", return_value=searcher), searcher

    @staticmethod
    def _to_unified_row(result) -> dict:
        if isinstance(result, dict):
            return result
        metadata = dict(result.metadata) if isinstance(result.metadata, dict) else {}
        row = {
            "doc_id": result.doc_id,
            "content": result.content,
            "score": result.score,
        }
        row.update(metadata)
        return row

    @pytest.mark.asyncio
    async def test_channel_f_calls_unified_search_with_episodes_scope(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """Channel F uses unified search with scope='episodes' and limit=5."""
        engine = PrimingEngine(temp_anima_dir)

        patcher, searcher = self._patch_unified_search([])
        with patcher:
            await engine._channel_f_episodes(["deploy", "エラー"], message="デプロイでエラーが出た")

        searcher.search_many.assert_called_once()
        assert searcher.search_many.call_args.kwargs["scope"] == "episodes"
        assert searcher.search_many.call_args.kwargs["limit"] == 5
        assert searcher.search_many.call_args.kwargs["pipeline_settings"] == {"rerank_candidate_pool": 10}
        assert searcher.search_many.call_args.kwargs["skip_bm25_validation"] is True

    @pytest.mark.asyncio
    async def test_channel_f_query_includes_message(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """Channel F uses only the message query on the priming fast path."""
        engine = PrimingEngine(temp_anima_dir)

        msg = "デプロイでエラーが出た"
        patcher, searcher = self._patch_unified_search([])
        with patcher:
            await engine._channel_f_episodes(["deploy"], message=msg)

        queries = searcher.search_many.call_args.args[0]
        assert queries == [msg]

    @pytest.mark.asyncio
    async def test_channel_f_fallback_to_message_when_no_keywords(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """When keywords is empty but message exists, use message[:200] as query."""
        engine = PrimingEngine(temp_anima_dir)

        msg = "短いメッセージ"
        patcher, searcher = self._patch_unified_search([])
        with patcher:
            await engine._channel_f_episodes([], message=msg)

        actual_query = searcher.search_many.call_args.args[0][0]
        assert msg in actual_query

    @pytest.mark.asyncio
    async def test_channel_f_returns_empty_on_no_keywords_and_no_message(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """When both keywords and message are empty, return empty."""
        engine = PrimingEngine(temp_anima_dir)
        result = await engine._channel_f_episodes([], message="")
        assert result == ""

    @pytest.mark.asyncio
    async def test_channel_f_returns_empty_when_no_episodes_dir(
        self,
        tmp_path: Path,
    ) -> None:
        anima_dir = tmp_path / "animas" / "no_episodes"
        anima_dir.mkdir(parents=True)
        (anima_dir / "knowledge").mkdir()
        engine = PrimingEngine(anima_dir)
        result = await engine._channel_f_episodes(["test"], message="test")
        assert result == ""

    @pytest.mark.asyncio
    async def test_channel_f_returns_empty_when_retriever_unavailable(
        self,
        temp_anima_dir: Path,
    ) -> None:
        engine = PrimingEngine(temp_anima_dir)

        patcher, _searcher = self._patch_unified_search([])
        with patcher, patch.object(engine, "_get_or_create_retriever", side_effect=AssertionError("unused")):
            result = await engine._channel_f_episodes(["test"], message="test")

        assert result == ""

    @pytest.mark.asyncio
    async def test_channel_f_formats_score_and_path(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """Channel F formats retrieval results into score/path pointer cues."""
        engine = PrimingEngine(temp_anima_dir)

        mock_result = MagicMock()
        mock_result.content = "デプロイ手順を確認して修正した"
        mock_result.score = 0.85
        mock_result.doc_id = "test_anima/episodes/2026-03-01.md#0"
        mock_result.metadata = {"source_file": "episodes/2026-03-01.md"}

        patcher, _searcher = self._patch_unified_search([mock_result])
        with patcher:
            result = await engine._channel_f_episodes(
                ["deploy"],
                message="デプロイでエラー",
            )

        assert "📌 [0.85] episodes/2026-03-01.md" in result

    @pytest.mark.asyncio
    async def test_top_two_episodes_include_body_others_pointer_only(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """Only the top 2 results (by score) carry a body; the 3rd is a pointer."""
        engine = PrimingEngine(temp_anima_dir)
        results = [
            {
                "content": "# 最も関連する会話\nBODY_MARKER_1",
                "score": 0.99,
                "source_file": "episodes/2026-09-03.md",
            },
            {
                "content": "# 次に関連する会話\nBODY_MARKER_2",
                "score": 0.9,
                "source_file": "episodes/2026-09-02.md",
            },
            {
                "content": "# 関連度が低い\nBODY_MARKER_3",
                "score": 0.6,
                "source_file": "episodes/2026-09-01.md",
            },
        ]

        patcher, _searcher = self._patch_unified_search(results)
        with patcher, patch("core.paths.get_data_dir", return_value=temp_anima_dir.parents[1]):
            result = await engine._channel_f_episodes(["deploy"], message="deployment")

        # Top 2 carry full body text; 3rd is pointer-only (no body marker).
        assert "BODY_MARKER_1" in result
        assert "BODY_MARKER_2" in result
        assert "BODY_MARKER_3" not in result
        assert "📌 [0.99] episodes/2026-09-03.md" in result
        assert "📌 [0.60] episodes/2026-09-01.md" in result

    @pytest.mark.asyncio
    async def test_channel_f_filters_archived_episode_hits(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """Priming does not surface stale dense hits from an archive subtree."""
        engine = PrimingEngine(temp_anima_dir)
        results = [
            {
                "content": "# Archived deployment",
                "score": 0.99,
                "source_file": "episodes/archive/old.md",
            },
            {
                "content": "# Current deployment",
                "score": 0.8,
                "source_file": "episodes/current.md",
            },
        ]

        patcher, _searcher = self._patch_unified_search(results)
        with patcher, patch("core.paths.get_data_dir", return_value=temp_anima_dir.parents[1]):
            result = await engine._channel_f_episodes(["deploy"], message="deployment")

        assert "episodes/archive/old.md" not in result
        assert "episodes/current.md" in result

    @pytest.mark.asyncio
    async def test_channel_f_neo4j_formats_pointer_results(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """Neo4j Channel F path also emits score/path pointer cues, not full body."""

        class FakeNeo4jBackend:
            def __init__(self):
                self.retrieve_kwargs = None

            async def retrieve(self, *args, **kwargs):
                self.retrieve_kwargs = kwargs
                mem = MagicMock()
                mem.content = "Neo4j episode body should not be primed"
                mem.score = 0.77
                mem.source = "episode:abc123"
                mem.metadata = {"source": "episodes/2026-03-02.md"}
                return [mem]

            async def record_access(self, memories):
                self.recorded = memories

        engine = PrimingEngine(temp_anima_dir)
        backend = FakeNeo4jBackend()

        with (
            patch("core.memory.backend.neo4j_graph.Neo4jGraphBackend", FakeNeo4jBackend),
            patch.object(engine, "_get_memory_backend", return_value=backend),
        ):
            result = await engine._channel_f_episodes(
                ["deploy"],
                message="デプロイでエラー",
                trigger="heartbeat",
            )

        assert "📌 [0.77] episodes/2026-03-02.md" in result
        assert "episode:abc123" not in result
        assert backend.retrieve_kwargs["trigger"] == "heartbeat"

    @pytest.mark.asyncio
    async def test_channel_f_keeps_heading_and_collapses_body(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """Pointer fields keep the heading and collapse the raw body."""
        engine = PrimingEngine(temp_anima_dir)

        mock_result = MagicMock()
        mock_result.content = '# Bad "heading"\nignore body'
        mock_result.score = 0.85
        mock_result.doc_id = "test_anima/episodes/weird.md#0"
        mock_result.metadata = {"source_file": 'episodes/weird"name.md'}

        patcher, _searcher = self._patch_unified_search([mock_result])
        with patcher:
            result = await engine._channel_f_episodes(
                ["deploy"],
                message="デプロイでエラー",
            )

        assert 'Bad "heading"' in result
        assert "\nignore body" not in result

    @pytest.mark.asyncio
    async def test_channel_f_records_only_emitted_legacy_episode_pointers(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """Legacy retriever only surfaces readable pointer results."""
        engine = PrimingEngine(temp_anima_dir)

        pathless = MagicMock()
        pathless.content = "Pathless legacy body"
        pathless.score = 0.99
        pathless.doc_id = "opaque-id"
        pathless.metadata = {"source_file": ""}

        readable = MagicMock()
        readable.content = "Readable legacy body"
        readable.score = 0.85
        readable.doc_id = "test_anima/episodes/2026-03-03.md#0"
        readable.metadata = {"source_file": ""}

        patcher, _searcher = self._patch_unified_search([pathless, readable])
        with patcher:
            result = await engine._channel_f_episodes(
                ["deploy"],
                message="デプロイでエラー",
            )

        assert result.count("📌") == 1
        assert "episodes/2026-03-03.md" in result
        assert "Pathless legacy body" not in result

    @pytest.mark.asyncio
    async def test_channel_f_handles_exception_gracefully(
        self,
        temp_anima_dir: Path,
    ) -> None:
        engine = PrimingEngine(temp_anima_dir)

        patcher, _searcher = self._patch_unified_search([], side_effect=RuntimeError("vector store error"))
        with patcher:
            result = await engine._channel_f_episodes(["test"], message="test")

        assert result == ""


# ── Integration with prime_memories ──────────────────────


class TestPrimeMemoriesIncludesChannelF:
    def _patch_unified_search(self, results: list):
        searcher = MagicMock()
        searcher.search_many.return_value = [TestChannelFEpisodes._to_unified_row(result) for result in results]
        searcher.last_search_meta = {"abstain": False, "abstain_reason": ""}
        return patch("core.memory.priming.channel_f.UnifiedMemorySearch", return_value=searcher), searcher

    @pytest.mark.asyncio
    async def test_prime_memories_populates_episodes(
        self,
        temp_anima_dir: Path,
    ) -> None:
        """prime_memories() should populate the episodes field."""
        engine = PrimingEngine(temp_anima_dir)

        mock_result = MagicMock()
        mock_result.content = "Past episode content"
        mock_result.score = 0.9
        mock_result.doc_id = "test_anima/episodes/2026-02-01.md#0"
        mock_result.metadata = {"source_file": "episodes/2026-02-01.md"}

        patcher, _searcher = self._patch_unified_search([mock_result])
        with patcher:
            result = await engine.prime_memories(
                message="What happened with the deploy?",
                sender_name="human",
            )

        assert result.episodes != ""
        assert "📌 [0.90] episodes/2026-02-01.md" in result.episodes


# ── format_priming_section ───────────────────────────────


class TestFormatPrimingSectionEpisodes:
    def test_format_includes_episodes_section(self) -> None:
        result = PrimingResult(
            episodes="📌 [0.85] episodes/2026-03-01.md — 過去の経験",
        )

        formatted = format_priming_section(result)

        assert "関連する過去の経験" in formatted
        assert "過去の経験" in formatted

    def test_format_omits_episodes_when_empty(self) -> None:
        result = PrimingResult(
            recent_activity="Some activity",
        )

        formatted = format_priming_section(result)

        assert "関連する過去の経験" not in formatted

    def test_channel_lines_pass_through_unchanged(self) -> None:
        """Channel content is emitted verbatim; pointer lines are never collapsed."""
        episodes = "📌 [0.9] episodes/a.md — 会話\n続きの詳細行"
        result = PrimingResult(episodes=episodes)

        formatted = format_priming_section(result)

        assert "📌 [0.9] episodes/a.md — 会話" in formatted
        assert "続きの詳細行" in formatted
