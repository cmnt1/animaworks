from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Integration tests for Phase 3: RAG index update + success/failure tracking."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.skills.usage import SkillUsageTracker

# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    """Create a minimal anima directory."""
    d = tmp_path / "animas" / "test-anima"
    for sub in ("episodes", "knowledge", "procedures", "skills", "state"):
        (d / sub).mkdir(parents=True)
    return d


@pytest.fixture
def memory(anima_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a MemoryManager that skips RAG initialization."""
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(anima_dir.parent.parent))

    data_dir = anima_dir.parent.parent
    (data_dir / "company").mkdir(parents=True, exist_ok=True)
    (data_dir / "common_skills").mkdir(parents=True, exist_ok=True)
    (data_dir / "common_knowledge").mkdir(parents=True, exist_ok=True)
    (data_dir / "shared" / "users").mkdir(parents=True, exist_ok=True)

    from core.memory.manager import MemoryManager

    return MemoryManager(anima_dir)


# ── 3-1: RAG index auto-update after write_memory_file ───


class TestRAGIndexAutoUpdate:
    """Test that writing to skills/ or procedures/ triggers RAG re-indexing."""

    def test_skill_write_triggers_index(self, memory, anima_dir: Path) -> None:
        """Writing a skill file should attempt to index it."""
        # Set up a mock indexer
        mock_indexer = MagicMock()
        mock_indexer.index_file = MagicMock(return_value=1)
        memory._indexer = mock_indexer
        memory._indexer_initialized = True

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle(
            "write_memory_file",
            {
                "path": "skills/test-skill.md",
                "content": "---\ndescription: test\n---\n\n# Test Skill",
            },
        )

        assert "Written to" in result
        mock_indexer.index_file.assert_called_once()
        call_args = mock_indexer.index_file.call_args
        assert call_args[1]["memory_type"] == "skills"
        assert call_args[1]["force"] is True

    def test_procedure_write_triggers_index(self, memory, anima_dir: Path) -> None:
        """Writing a procedure file should attempt to index it."""
        mock_indexer = MagicMock()
        mock_indexer.index_file = MagicMock(return_value=1)
        memory._indexer = mock_indexer
        memory._indexer_initialized = True

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle(
            "write_memory_file",
            {
                "path": "procedures/deploy.md",
                "content": "---\ndescription: deploy\n---\n\n# Deploy",
            },
        )

        assert "Written to" in result
        mock_indexer.index_file.assert_called_once()
        call_args = mock_indexer.index_file.call_args
        assert call_args[1]["memory_type"] == "procedures"

    def test_knowledge_write_triggers_knowledge_index(self, memory, anima_dir: Path) -> None:
        """Writing to knowledge/ should trigger knowledge RAG indexing."""
        mock_indexer = MagicMock()
        memory._indexer = mock_indexer
        memory._indexer_initialized = True

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        handler.handle(
            "write_memory_file",
            {
                "path": "knowledge/notes.md",
                "content": "# Some knowledge",
            },
        )

        mock_indexer.index_file.assert_called_once()
        call_args = mock_indexer.index_file.call_args
        assert call_args[1]["memory_type"] == "knowledge"

    def test_index_failure_does_not_break_write(self, memory, anima_dir: Path) -> None:
        """RAG index failure should be logged but not block the write."""
        mock_indexer = MagicMock()
        mock_indexer.index_file = MagicMock(side_effect=RuntimeError("index error"))
        memory._indexer = mock_indexer
        memory._indexer_initialized = True

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle(
            "write_memory_file",
            {
                "path": "procedures/failing.md",
                "content": "---\ndescription: test\n---\n\n# Test",
            },
        )

        assert "Written to" in result  # write still succeeds


# ── 3-2: report_procedure_outcome tool ───────────────────


class TestReportProcedureOutcome:
    """Test the report_procedure_outcome tool handler."""

    def test_success_increments_count(self, memory, anima_dir: Path) -> None:
        """Reporting success should increment success_count and update confidence."""
        # Create procedure with initial metadata
        memory.write_procedure_with_meta(
            Path("deploy.md"),
            "# Deploy Steps\n\n1. Pull\n2. Build",
            {
                "description": "deploy procedure",
                "success_count": 3,
                "failure_count": 1,
                "confidence": 0.75,
                "last_used": None,
            },
        )

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        handler._record_memory_file_used = MagicMock()
        result = handler.handle(
            "report_procedure_outcome",
            {
                "path": "procedures/deploy.md",
                "success": True,
                "notes": "Deployed successfully",
            },
        )

        assert "成功" in result
        assert "confidence: 0.80" in result

        # Verify metadata was updated
        meta = memory.read_procedure_metadata(
            anima_dir / "procedures" / "deploy.md",
        )
        assert meta["success_count"] == 4
        assert meta["failure_count"] == 1
        assert abs(meta["confidence"] - 0.8) < 0.01
        assert meta["last_used"] is not None
        handler._record_memory_file_used.assert_called_once_with("procedures/deploy.md")

    def test_failure_increments_count(self, memory, anima_dir: Path) -> None:
        """Reporting failure should increment failure_count and lower confidence."""
        memory.write_procedure_with_meta(
            Path("backup.md"),
            "# Backup",
            {
                "description": "backup procedure",
                "success_count": 2,
                "failure_count": 0,
                "confidence": 1.0,
            },
        )

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle(
            "report_procedure_outcome",
            {
                "path": "procedures/backup.md",
                "success": False,
                "notes": "Backup failed due to disk full",
            },
        )

        assert "失敗" in result
        meta = memory.read_procedure_metadata(
            anima_dir / "procedures" / "backup.md",
        )
        assert meta["failure_count"] == 1
        assert abs(meta["confidence"] - 2 / 3) < 0.01
        assert SkillUsageTracker(anima_dir).get_stats("backup").failure_count == 1

    def test_missing_file_returns_error(self, memory, anima_dir: Path) -> None:
        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle(
            "report_procedure_outcome",
            {
                "path": "procedures/nonexistent.md",
                "success": True,
            },
        )
        assert "error" in result.lower() or "not found" in result.lower()

    def test_empty_path_returns_error(self, memory, anima_dir: Path) -> None:
        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        result = handler.handle(
            "report_procedure_outcome",
            {
                "path": "",
                "success": True,
            },
        )
        assert "error" in result.lower()

    def test_body_content_preserved(self, memory, anima_dir: Path) -> None:
        """The procedure body should be preserved when metadata is updated."""
        body_text = "# Complex Procedure\n\n1. Step one\n2. Step two\n3. Step three"
        memory.write_procedure_with_meta(
            Path("complex.md"),
            body_text,
            {"description": "complex", "success_count": 0, "failure_count": 0, "confidence": 0.5},
        )

        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir, memory)
        handler.handle(
            "report_procedure_outcome",
            {
                "path": "procedures/complex.md",
                "success": True,
            },
        )

        # Read the file content and verify body is intact
        content = memory.read_procedure_content(
            anima_dir / "procedures" / "complex.md",
        )
        assert "Step one" in content
        assert "Step two" in content
        assert "Step three" in content


# ── 3-2: Schema registration ────────────────────────────


class TestProcedureToolSchema:
    """Test that the procedure outcome tool is registered in schemas."""

    def test_schema_in_build_tool_list(self) -> None:
        from core.tooling.schemas import build_tool_list

        tools = build_tool_list()
        names = {t["name"] for t in tools}
        assert "report_procedure_outcome" in names

    def test_schema_in_build_unified_tool_list(self) -> None:
        from core.tooling.schemas import build_unified_tool_list

        tools = build_unified_tool_list(include_create_skill=False)
        names = {t["name"] for t in tools}
        assert "report_procedure_outcome" in names

    def test_schema_has_required_fields(self) -> None:
        from core.tooling.schemas import PROCEDURE_TOOLS

        schema = PROCEDURE_TOOLS[0]
        assert schema["name"] == "report_procedure_outcome"
        params = schema["parameters"]
        assert "path" in params["properties"]
        assert "success" in params["properties"]
        assert "notes" in params["properties"]
        assert set(params["required"]) == {"path", "success"}


# Auto-outcome tracking was removed; explicit report_procedure_outcome covers the live path.
