from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Tests for knowledge frontmatter read/write behavior."""

from pathlib import Path

import pytest

# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def temp_anima_dir(tmp_path: Path) -> Path:
    """Create a temporary anima directory structure."""
    anima_dir = tmp_path / "test_anima"
    (anima_dir / "episodes").mkdir(parents=True)
    (anima_dir / "knowledge").mkdir(parents=True)
    (anima_dir / "procedures").mkdir(parents=True)
    (anima_dir / "skills").mkdir(parents=True)
    (anima_dir / "state").mkdir(parents=True)
    return anima_dir


@pytest.fixture
def memory_manager(temp_anima_dir: Path):
    """Create a MemoryManager instance."""
    from core.memory.manager import MemoryManager

    return MemoryManager(temp_anima_dir)


# ── Frontmatter Read/Write ──────────────────────────────────


class TestWriteKnowledgeWithMeta:
    """Test write_knowledge_with_meta method."""

    def test_basic_write(self, memory_manager: object, temp_anima_dir: Path) -> None:
        """Write a knowledge file with metadata and verify structure."""
        path = temp_anima_dir / "knowledge" / "test-topic.md"
        metadata = {
            "created_at": "2026-02-18T10:00:00",
            "confidence": 0.9,
            "auto_consolidated": True,
        }
        content = "# Test Topic\n\nThis is a test."

        memory_manager.write_knowledge_with_meta(path, content, metadata)

        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert "confidence: 0.9" in text
        assert "auto_consolidated: true" in text
        assert "# Test Topic" in text

    def test_write_creates_parent_dirs(
        self,
        memory_manager: object,
        temp_anima_dir: Path,
    ) -> None:
        """write_knowledge_with_meta creates parent directories if needed."""
        path = temp_anima_dir / "knowledge" / "sub" / "deep" / "file.md"
        metadata = {"created_at": "2026-01-01"}
        memory_manager.write_knowledge_with_meta(path, "content", metadata)
        assert path.exists()

    def test_write_unicode_content(
        self,
        memory_manager: object,
        temp_anima_dir: Path,
    ) -> None:
        """Japanese content survives round-trip through YAML frontmatter."""
        path = temp_anima_dir / "knowledge" / "unicode.md"
        metadata = {"tags": ["日本語", "テスト"]}
        content = "# 日本語テスト\n\nこれはテストです。"

        memory_manager.write_knowledge_with_meta(path, content, metadata)

        read_content = memory_manager.read_knowledge_content(path)
        assert "日本語テスト" in read_content
        read_meta = memory_manager.read_knowledge_metadata(path)
        assert "日本語" in read_meta.get("tags", [])


class TestReadKnowledgeContent:
    """Test read_knowledge_content method."""

    def test_with_frontmatter(
        self,
        memory_manager: object,
        temp_anima_dir: Path,
    ) -> None:
        """Content is returned without frontmatter."""
        path = temp_anima_dir / "knowledge" / "with-fm.md"
        path.write_text(
            "---\nconfidence: 0.8\n---\n\n# Topic\n\nBody text.",
            encoding="utf-8",
        )

        result = memory_manager.read_knowledge_content(path)
        assert result == "# Topic\n\nBody text."
        assert "---" not in result
        assert "confidence" not in result

    def test_without_frontmatter(
        self,
        memory_manager: object,
        temp_anima_dir: Path,
    ) -> None:
        """Files without frontmatter return full text (backward compat)."""
        path = temp_anima_dir / "knowledge" / "no-fm.md"
        path.write_text("# Old Style\n\nLegacy content.", encoding="utf-8")

        result = memory_manager.read_knowledge_content(path)
        assert "# Old Style" in result
        assert "Legacy content." in result

    def test_empty_frontmatter(
        self,
        memory_manager: object,
        temp_anima_dir: Path,
    ) -> None:
        """Empty frontmatter block is handled gracefully."""
        path = temp_anima_dir / "knowledge" / "empty-fm.md"
        path.write_text("---\n---\n\nBody only.", encoding="utf-8")

        result = memory_manager.read_knowledge_content(path)
        assert result == "Body only."


class TestReadKnowledgeMetadata:
    """Test read_knowledge_metadata method."""

    def test_with_frontmatter(
        self,
        memory_manager: object,
        temp_anima_dir: Path,
    ) -> None:
        """Metadata dictionary is correctly parsed from YAML frontmatter."""
        path = temp_anima_dir / "knowledge" / "meta.md"
        path.write_text(
            "---\nconfidence: 0.85\nauto_consolidated: true\n---\n\nContent.",
            encoding="utf-8",
        )

        meta = memory_manager.read_knowledge_metadata(path)
        assert meta["confidence"] == 0.85
        assert meta["auto_consolidated"] is True

    def test_without_frontmatter(
        self,
        memory_manager: object,
        temp_anima_dir: Path,
    ) -> None:
        """Files without frontmatter return empty dict."""
        path = temp_anima_dir / "knowledge" / "no-meta.md"
        path.write_text("# Just content", encoding="utf-8")

        meta = memory_manager.read_knowledge_metadata(path)
        assert meta == {}

    def test_invalid_yaml(
        self,
        memory_manager: object,
        temp_anima_dir: Path,
    ) -> None:
        """Invalid YAML frontmatter returns empty dict."""
        path = temp_anima_dir / "knowledge" / "bad-yaml.md"
        path.write_text("---\n: invalid: yaml: [\n---\n\nContent.", encoding="utf-8")

        meta = memory_manager.read_knowledge_metadata(path)
        assert meta == {}


class TestRoundTrip:
    """Test write + read round-trip."""

    def test_full_roundtrip(
        self,
        memory_manager: object,
        temp_anima_dir: Path,
    ) -> None:
        """Metadata and content survive a write-then-read round trip."""
        path = temp_anima_dir / "knowledge" / "roundtrip.md"
        metadata = {
            "created_at": "2026-02-18T10:00:00",
            "confidence": 0.75,
            "source_episodes": ["2026-02-17.md", "2026-02-18.md"],
        }
        content = "# Round Trip Test\n\nThis should survive."

        memory_manager.write_knowledge_with_meta(path, content, metadata)

        read_content = memory_manager.read_knowledge_content(path)
        read_meta = memory_manager.read_knowledge_metadata(path)

        assert read_content == content
        assert read_meta["confidence"] == 0.75
        assert read_meta["source_episodes"] == ["2026-02-17.md", "2026-02-18.md"]


# ── Indexer Frontmatter Strip ────────────────────────────────


class TestIndexerStripFrontmatter:
    """Test MemoryIndexer._strip_frontmatter static method."""

    def test_strip_with_frontmatter(self) -> None:
        """Frontmatter block is removed from content."""
        from core.memory.rag.indexer import MemoryIndexer

        content = "---\nkey: value\ntags: [a, b]\n---\n\n# Heading\n\nBody."
        result = MemoryIndexer._strip_frontmatter(content)
        assert result == "# Heading\n\nBody."
        assert "---" not in result

    def test_strip_without_frontmatter(self) -> None:
        """Content without frontmatter is returned unchanged."""
        from core.memory.rag.indexer import MemoryIndexer

        content = "# Heading\n\nBody text."
        result = MemoryIndexer._strip_frontmatter(content)
        assert result == content

    def test_strip_empty_frontmatter(self) -> None:
        """Empty frontmatter block is stripped."""
        from core.memory.rag.indexer import MemoryIndexer

        content = "---\n---\n\nBody only."
        result = MemoryIndexer._strip_frontmatter(content)
        assert result == "Body only."

    def test_strip_preserves_internal_dashes(self) -> None:
        """Triple dashes within body are not treated as frontmatter delimiter."""
        from core.memory.rag.indexer import MemoryIndexer

        content = "No frontmatter here.\n\n---\n\nThis is a horizontal rule."
        result = MemoryIndexer._strip_frontmatter(content)
        assert result == content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
