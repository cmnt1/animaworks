"""Unit tests for consolidation atomic-fact-extraction chunking."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.memory.facts.chunking import split_text_for_fact_extraction
from core.memory.facts.extraction import FactExtractionOutcome
from core.memory.facts.store import FactRecord
from core.memory.maintenance.consolidation import ConsolidationEngine


def _record(n: int) -> FactRecord:
    return FactRecord(text=f"fact-{n}", source_episode="ep")


class TestSplitTextForFactExtraction:
    """Tests for the pure chunking helper."""

    def test_within_limit_returns_single_chunk(self) -> None:
        text = "## 2026-09-30\nLínea a\nLínea b"
        assert split_text_for_fact_extraction(text, 10_000) == [text]

    def test_empty_string_returns_empty_list(self) -> None:
        assert split_text_for_fact_extraction("", 12000) == []

    def test_max_chars_zero_disables_splitting(self) -> None:
        text = "hello\nworld\n" * 100
        assert split_text_for_fact_extraction(text, 0) == [text]

    def test_negative_max_chars_disables_splitting(self) -> None:
        text = "hello"
        assert split_text_for_fact_extraction(text, -5) == [text]

    def test_heading_preferred_over_blank_line(self) -> None:
        # A '#' heading should be used as the boundary even when a blank line
        # (and a newline) also exist. The next chunk must begin with the '#.'
        max_chars = 90
        text = ("A" * 70) + "\n\n" + ("# Heading " * 10) + ("tail" * 40)
        chunks = split_text_for_fact_extraction(text, max_chars)
        assert len(chunks) > 1
        assert len(chunks[0]) <= max_chars
        # boundary lands right before the heading line, not at the blank line
        assert chunks[1].startswith("# Heading")

    def test_blank_line_used_when_no_heading(self) -> None:
        max_chars = 20
        text = "aaaaaaaaaa" + "\n\n" + "bbbbbbbbbbbbbbbbbbbb"
        chunks = split_text_for_fact_extraction(text, max_chars)
        assert len(chunks) > 1
        assert chunks[0] == "aaaaaaaaaa\n\n"
        assert chunks[1].startswith("bbbb")

    def test_hard_cut_when_no_boundary(self) -> None:
        text = "A" * 100
        chunks = split_text_for_fact_extraction(text, 30)
        assert all(len(c) <= 30 for c in chunks)
        assert len(chunks) >= 4

    def test_concatenation_restores_original(self) -> None:
        text = "## 2026-09-30\n" + ("paragraph " * 20) + "\n\n# Another heading\n" + ("more data " * 30)
        chunks = split_text_for_fact_extraction(text, 40)
        assert "".join(chunks) == text


class TestExtractFactsFromTextOutcome:
    """Tests for ConsolidationEngine.extract_facts_from_text_outcome."""

    def _engine(self) -> ConsolidationEngine:
        return ConsolidationEngine(Path("/tmp/nonexistent-anima"), "anima-test")

    def _cfg(self, chunk_chars: int) -> SimpleNamespace:
        return SimpleNamespace(consolidation=SimpleNamespace(fact_extraction_chunk_chars=chunk_chars))

    async def test_three_chunks_aggregated_and_records_concatenated(self) -> None:
        engine = self._engine()
        text = "# H1 heading\n" + ("x" * 60) + "\n# H2 heading\n" + ("y" * 60) + "\n# H3 heading\n" + ("z" * 60)
        outcomes = [
            FactExtractionOutcome([_record(1)], False),
            FactExtractionOutcome([_record(2), _record(3)], False),
            FactExtractionOutcome([], False),
        ]
        mock_extract = AsyncMock(side_effect=outcomes)
        with (
            patch("core.config.load_config", return_value=self._cfg(80)),
            patch(
                "core.memory.facts.extraction.extract_and_store_facts_with_outcome",
                mock_extract,
            ),
        ):
            result = await engine.extract_facts_from_text_outcome(text, source_episode="ep")

        assert mock_extract.call_count == 3
        assert result.facts_extracted == 3
        assert result.failed is False
        assert result.failed_chunks == 0
        assert result.total_chunks == 3
        assert [r.text for r in result.records] == ["fact-1", "fact-2", "fact-3"]

    async def test_middle_chunk_failure_keeps_others_with_failed_count(self) -> None:
        engine = self._engine()
        text = "# A heading\n" + ("a" * 60) + "\n# B heading\n" + ("b" * 60) + "\n# C heading\n" + ("c" * 60)
        outcomes = [
            FactExtractionOutcome([_record(1)], False),
            FactExtractionOutcome([], True, "fact_llm", "boom"),
            FactExtractionOutcome([_record(3)], False),
        ]
        mock_extract = AsyncMock(side_effect=outcomes)
        with (
            patch("core.config.load_config", return_value=self._cfg(80)),
            patch(
                "core.memory.facts.extraction.extract_and_store_facts_with_outcome",
                mock_extract,
            ),
        ):
            result = await engine.extract_facts_from_text_outcome(text, source_episode="ep")

        assert mock_extract.call_count == 3
        assert result.facts_extracted == 2
        assert result.failed is True
        assert result.failed_chunks == 1
        assert result.facts_failed == 1
        assert result.failure_stage == "fact_llm"
        assert result.failure_reason.startswith("chunk 2/3:")

    async def test_chunk_exception_does_not_stop_processing(self) -> None:
        engine = self._engine()
        text = "# A heading\n" + ("a" * 60) + "\n# B heading\n" + ("b" * 60) + "\n# C heading\n" + ("c" * 60)
        outcomes = [
            FactExtractionOutcome([_record(1)], False),
            RuntimeError("chunk exploded"),
            FactExtractionOutcome([_record(3)], False),
        ]
        mock_extract = AsyncMock(side_effect=outcomes)
        with (
            patch("core.config.load_config", return_value=self._cfg(80)),
            patch(
                "core.memory.facts.extraction.extract_and_store_facts_with_outcome",
                mock_extract,
            ),
        ):
            result = await engine.extract_facts_from_text_outcome(text, source_episode="ep")

        assert mock_extract.await_count == 3
        assert result.facts_extracted == 2
        assert result.failed is True
        assert result.failed_chunks == 1
        assert result.failure_reason.startswith("chunk 2/3:")

    async def test_short_text_calls_once_for_backward_compat(self) -> None:
        engine = self._engine()
        text = "## Short summary\nA tiny summary with no detail here."
        mock_extract = AsyncMock(return_value=FactExtractionOutcome([_record(9)], False))
        with (
            patch("core.config.load_config", return_value=self._cfg(12000)),
            patch(
                "core.memory.facts.extraction.extract_and_store_facts_with_outcome",
                mock_extract,
            ),
        ):
            result = await engine.extract_facts_from_text_outcome(text, source_episode="ep")

        assert mock_extract.await_count == 1
        assert result.facts_extracted == 1
        assert result.total_chunks == 1
        assert result.failed is False

    async def test_chunk_chars_zero_calls_once(self) -> None:
        engine = self._engine()
        text = "# H1\n" + ("x" * 60) + "\n# H2\n" + ("y" * 60)
        mock_extract = AsyncMock(return_value=FactExtractionOutcome([_record(1)], False))
        with (
            patch("core.config.load_config", return_value=self._cfg(0)),
            patch(
                "core.memory.facts.extraction.extract_and_store_facts_with_outcome",
                mock_extract,
            ),
        ):
            result = await engine.extract_facts_from_text_outcome(text, source_episode="ep")
        assert mock_extract.await_count == 1
        assert result.total_chunks == 1
