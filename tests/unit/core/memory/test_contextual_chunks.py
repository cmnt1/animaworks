"""Unit tests for contextual chunk headers (P1-B memory search).

Covers:
- Episode embedding text starts with ``[YYYY-MM-DD | title > heading]``
- Knowledge without date uses ``[title > heading]``; title fallbacks
- BM25 hits via filename date year + title tokens absent from body
- procedures / facts chunks do not get headers
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.memory.bm25 import rebuild_longterm_bm25_index, search_longterm_memory_bm25
from core.memory.rag.contextual_header import (
    apply_contextual_header,
    build_contextual_chunk_header,
    extract_heading_path,
    resolve_chunk_date,
    resolve_file_title,
)


# ── Helper unit tests ─────────────────────────────────────────


def test_build_header_with_date_title_heading() -> None:
    assert (
        build_contextual_chunk_header(
            date="2026-07-15",
            file_title="natsumeタスク死",
            heading_path="09:30 — Morning",
        )
        == "[2026-07-15 | natsumeタスク死 > 09:30 — Morning]"
    )


def test_build_header_without_date() -> None:
    assert (
        build_contextual_chunk_header(
            date=None,
            file_title="Orbit Notes",
            heading_path="Calibration",
        )
        == "[Orbit Notes > Calibration]"
    )


def test_build_header_without_heading() -> None:
    assert (
        build_contextual_chunk_header(
            date="2026-07-15",
            file_title="Daily",
            heading_path=None,
        )
        == "[2026-07-15 | Daily]"
    )


def test_resolve_date_from_filename_prefix(tmp_path: Path) -> None:
    path = tmp_path / "2026-07-15_notes.md"
    assert resolve_chunk_date(path, {}) == "2026-07-15"


def test_resolve_date_from_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    assert resolve_chunk_date(path, {"date": "2026-03-01T12:00:00"}) == "2026-03-01"


def test_resolve_title_frontmatter_over_h1(tmp_path: Path) -> None:
    path = tmp_path / "file.md"
    assert resolve_file_title(path, "# H1 Title\n\nbody", {"title": "FM Title"}) == "FM Title"


def test_resolve_title_h1_fallback(tmp_path: Path) -> None:
    path = tmp_path / "file.md"
    assert resolve_file_title(path, "# Heading One\n\nbody", {}) == "Heading One"


def test_resolve_title_stem_fallback(tmp_path: Path) -> None:
    path = tmp_path / "my-stem-name.md"
    assert resolve_file_title(path, "no headings here", {}) == "my-stem-name"


def test_extract_heading_path_from_section() -> None:
    assert extract_heading_path("## Morning Brief\n\nbody text") == "Morning Brief"
    assert extract_heading_path("# Only H1\n\nbody") is None
    assert extract_heading_path("plain preamble text") is None


# ── Indexer integration ───────────────────────────────────────


class TestIndexerContextualHeaders:
    @pytest.fixture
    def anima_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "anima"
        d.mkdir()
        (d / "episodes").mkdir()
        (d / "knowledge").mkdir()
        (d / "procedures").mkdir()
        (d / "facts").mkdir()
        return d

    def _make_indexer(self, anima_dir: Path):
        from core.memory.rag.indexer import MemoryIndexer

        with patch.object(MemoryIndexer, "_init_embedding_model"):
            return MemoryIndexer(
                MagicMock(),
                anima_name=anima_dir.name,
                anima_dir=anima_dir,
            )

    def test_episode_chunk_starts_with_date_title_heading(self, anima_dir: Path) -> None:
        indexer = self._make_indexer(anima_dir)
        f = anima_dir / "episodes" / "2026-07-15.md"
        f.write_text(
            "---\ntitle: natsumeタスク死\n---\n\n"
            "## 09:30 — Morning\n\n"
            "Task died without recovery. No date or title word here.\n\n"
            "## 14:00 — Afternoon\n\n"
            "Follow-up notes only.\n",
            encoding="utf-8",
        )

        chunks = indexer._chunk_by_time_headings(f, f.read_text(encoding="utf-8"), "episodes")
        assert len(chunks) == 2
        assert chunks[0].content.startswith("[2026-07-15 | natsumeタスク死 > 09:30 — Morning]")
        assert chunks[1].content.startswith("[2026-07-15 | natsumeタスク死 > 14:00 — Afternoon]")
        # Body still present after header
        assert "Task died without recovery" in chunks[0].content

    def test_knowledge_no_date_header_uses_title_and_heading(self, anima_dir: Path) -> None:
        indexer = self._make_indexer(anima_dir)
        f = anima_dir / "knowledge" / "orbit-notes.md"
        f.write_text(
            "---\ntitle: Orbit Notes\n---\n\n"
            "## Calibration\n\n"
            "Telemetry handoff details without the title word.\n",
            encoding="utf-8",
        )

        chunks = indexer._chunk_by_markdown_headings(f, f.read_text(encoding="utf-8"), "knowledge")
        assert len(chunks) >= 1
        assert chunks[0].content.startswith("[Orbit Notes > Calibration]")
        assert not chunks[0].content.startswith("[20")

    def test_knowledge_title_fallback_to_h1(self, anima_dir: Path) -> None:
        indexer = self._make_indexer(anima_dir)
        f = anima_dir / "knowledge" / "stem-file.md"
        f.write_text(
            "# H1 Document Title\n\n"
            "## Section Alpha\n\n"
            "Body content long enough for a real section chunk here.\n",
            encoding="utf-8",
        )

        chunks = indexer._chunk_by_markdown_headings(f, f.read_text(encoding="utf-8"), "knowledge")
        # Preamble may exist if long enough; section chunk must use H1 as title.
        section = next(c for c in chunks if "Section Alpha" in c.content)
        assert section.content.startswith("[H1 Document Title > Section Alpha]")

    def test_knowledge_title_fallback_to_stem(self, anima_dir: Path) -> None:
        indexer = self._make_indexer(anima_dir)
        f = anima_dir / "knowledge" / "unique-stem-xyz.md"
        f.write_text(
            "## Only Section\n\n"
            "Body without any top-level title heading at all.\n",
            encoding="utf-8",
        )

        chunks = indexer._chunk_by_markdown_headings(f, f.read_text(encoding="utf-8"), "knowledge")
        assert len(chunks) == 1
        assert chunks[0].content.startswith("[unique-stem-xyz > Only Section]")

    def test_procedures_chunk_has_no_header(self, anima_dir: Path) -> None:
        indexer = self._make_indexer(anima_dir)
        f = anima_dir / "procedures" / "deploy.md"
        body = "# Deploy Procedure\n\nStep one then step two for release.\n"
        f.write_text(body, encoding="utf-8")

        chunks = indexer._chunk_whole_file(f, f.read_text(encoding="utf-8"), "procedures")
        assert len(chunks) == 1
        assert not chunks[0].content.startswith("[")
        assert chunks[0].content.startswith("# Deploy Procedure")

    def test_facts_chunk_has_no_header(self, anima_dir: Path) -> None:
        indexer = self._make_indexer(anima_dir)
        f = anima_dir / "facts" / "entities.jsonl"
        line = (
            '{"text":"Alice works at Acme",'
            '"source_entity":"Alice","target_entity":"Acme",'
            '"edge_type":"WORKS_AT"}\n'
        )
        f.write_text(line, encoding="utf-8")

        chunks = indexer._chunk_file(f, f.read_text(encoding="utf-8"), "facts")
        assert len(chunks) >= 1
        for chunk in chunks:
            assert not chunk.content.startswith("[")
            assert "Alice" in chunk.content

    def test_chunk_id_unchanged_with_header(self, anima_dir: Path) -> None:
        indexer = self._make_indexer(anima_dir)
        f = anima_dir / "knowledge" / "id-check.md"
        f.write_text("## Alpha\n\nBody text for alpha section.\n", encoding="utf-8")
        chunks = indexer._chunk_by_markdown_headings(f, f.read_text(encoding="utf-8"), "knowledge")
        assert chunks[0].id == f"{anima_dir.name}/knowledge/id-check.md#0"
        assert chunks[0].metadata["chunk_index"] == 0


# ── BM25 integration ──────────────────────────────────────────


def _write_longterm(anima_dir: Path, rel: str, content: str) -> None:
    path = anima_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_bm25_hits_via_filename_date_and_title_tokens(tmp_path: Path) -> None:
    """Date (year token) + title word absent from body still retrieve the doc."""
    anima_dir = tmp_path / "animas" / "alice"
    # Body deliberately omits the unique title token UniqueCodenameZulu.
    _write_longterm(
        anima_dir,
        "episodes/2026-07-15.md",
        "---\ntitle: UniqueCodenameZulu\n---\n\n"
        "## Morning\n\n"
        "The process failed silently during handoff review only.\n",
    )
    # Distractor without the title token
    _write_longterm(
        anima_dir,
        "knowledge/other.md",
        "# Other\n\nUnrelated baseline memo for IDF corpus weight.\n",
    )

    rebuild_longterm_bm25_index(anima_dir)

    # Year token from date prefix + title token only present in header
    hits = search_longterm_memory_bm25(
        anima_dir,
        "2026 UniqueCodenameZulu",
        memory_types=("episodes", "knowledge"),
        top_k=5,
    )
    assert hits
    assert hits[0]["source_file"] == "episodes/2026-07-15.md"
    assert "UniqueCodenameZulu" in hits[0]["content"]
    assert hits[0]["content"].startswith("[2026-07-15 | UniqueCodenameZulu")


def test_bm25_procedures_content_has_no_contextual_header(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    _write_longterm(
        anima_dir,
        "procedures/runbook.md",
        "---\ntitle: SecretTitleToken\n---\n\n"
        "# Runbook\n\nProcedure steps without the secret title in body.\n",
    )
    rebuild_longterm_bm25_index(anima_dir)

    hits = search_longterm_memory_bm25(
        anima_dir,
        "Procedure steps",
        memory_types=("procedures",),
        top_k=5,
    )
    assert hits
    assert not hits[0]["content"].startswith("[")
    # Title-only query should not rely on header tokens for procedures
    title_hits = search_longterm_memory_bm25(
        anima_dir,
        "SecretTitleToken",
        memory_types=("procedures",),
        top_k=5,
    )
    assert title_hits == [] or "SecretTitleToken" not in title_hits[0].get("content", "")


def test_apply_skips_non_target_memory_types(tmp_path: Path) -> None:
    path = tmp_path / "procedures" / "x.md"
    path.parent.mkdir(parents=True)
    path.write_text("body", encoding="utf-8")
    out = apply_contextual_header(
        "raw body",
        file_path=path,
        body="raw body",
        memory_type="procedures",
        frontmatter={"title": "T"},
    )
    assert out == "raw body"
