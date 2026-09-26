"""Unit tests for PostToolUse knowledge frontmatter hook."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


class TestBuildPostToolHook:
    """Tests for _build_post_tool_hook factory."""

    def _make_hook(self, anima_dir: Path):
        from core.execution.engines.claude._sdk_hooks import _build_post_tool_hook

        return _build_post_tool_hook(anima_dir)

    @pytest.mark.asyncio
    async def test_ignores_non_write_edit_tools(self, tmp_path):
        hook = self._make_hook(tmp_path)
        result = await hook(
            {"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "knowledge" / "x.md")}},
            None,
            None,
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_ignores_non_knowledge_path(self, tmp_path):
        hook = self._make_hook(tmp_path)
        result = await hook(
            {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "episodes" / "2026-03-12.md")}},
            None,
            None,
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_ignores_non_md_files(self, tmp_path):
        hook = self._make_hook(tmp_path)
        result = await hook(
            {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "knowledge" / "data.json")}},
            None,
            None,
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_triggers_for_knowledge_md(self, tmp_path):
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        test_file = knowledge_dir / "test.md"
        test_file.write_text("---\nversion: 1\n---\n\n# Test", encoding="utf-8")

        hook = self._make_hook(tmp_path)
        result = await hook(
            {"tool_name": "Write", "tool_input": {"file_path": str(test_file)}},
            None,
            None,
        )
        assert result.get("async_") is True

    @pytest.mark.asyncio
    async def test_triggers_for_edit_tool(self, tmp_path):
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        test_file = knowledge_dir / "test.md"
        test_file.write_text("---\nversion: 2\n---\n\n# Test", encoding="utf-8")

        hook = self._make_hook(tmp_path)
        result = await hook(
            {"tool_name": "Edit", "tool_input": {"file_path": str(test_file)}},
            None,
            None,
        )
        assert result.get("async_") is True


class TestMcpRuleAttachment:
    """PostToolUse must attach ACTION-RULE bodies exactly once per tool result.

    MCP aw tools (``mcp__aw__*``) get rules attached by the handler
    (``core.tooling.handler``), so PostToolUse must NOT attach them again
    for those tools — otherwise the rule body would appear twice.
    """

    @pytest.mark.asyncio
    async def test_mcp_tool_does_not_attach_action_rules(self, tmp_path, monkeypatch):
        from core.execution.engines.claude._sdk_hooks import _build_post_tool_hook
        from core.tooling import action_gate
        from core.tooling.action_gate import ActionRule

        found = [ActionRule(rule_id="r1", content="RULE-BODY", score=0.9)]
        calls = []

        def _fake_find_action_rules(*args, **kwargs):
            calls.append(args)
            return found

        monkeypatch.setattr(action_gate, "find_action_rules", _fake_find_action_rules)
        monkeypatch.setattr(action_gate, "format_action_rules", lambda rules: "RULE-BODY")

        hook = _build_post_tool_hook(tmp_path)
        result = await hook(
            {"tool_name": "mcp__aw__send_message", "tool_input": {"to": "u", "text": "hi"}},
            None,
            None,
        )
        # MCP rules are attached handler-side; PostToolUse must not add them.
        assert result == {}
        assert calls == []


class TestUpdateKnowledgeFrontmatter:
    """Tests for _update_knowledge_frontmatter."""

    @pytest.mark.asyncio
    async def test_updates_version_and_timestamp(self, tmp_path):
        from core.execution.engines.claude._sdk_hooks import _update_knowledge_frontmatter

        knowledge_file = tmp_path / "test.md"
        knowledge_file.write_text(
            "---\ncreated_at: '2026-03-01'\nupdated_at: '2026-03-01'\nversion: 3\n---\n\n# Content\nBody text",
            encoding="utf-8",
        )

        await _update_knowledge_frontmatter(knowledge_file)

        text = knowledge_file.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        meta_str = text.split("---")[1]
        meta = yaml.safe_load(meta_str)
        assert meta["version"] == 4
        assert meta["updated_at"] != "2026-03-01"
        assert "# Content" in text
        assert "Body text" in text

    @pytest.mark.asyncio
    async def test_skips_file_without_frontmatter(self, tmp_path):
        from core.execution.engines.claude._sdk_hooks import _update_knowledge_frontmatter

        knowledge_file = tmp_path / "no_fm.md"
        original = "# Just a title\n\nNo frontmatter here."
        knowledge_file.write_text(original, encoding="utf-8")

        await _update_knowledge_frontmatter(knowledge_file)

        assert knowledge_file.read_text(encoding="utf-8") == original

    @pytest.mark.asyncio
    async def test_skips_empty_frontmatter(self, tmp_path):
        from core.execution.engines.claude._sdk_hooks import _update_knowledge_frontmatter

        knowledge_file = tmp_path / "empty_fm.md"
        original = "---\n---\n\n# Content"
        knowledge_file.write_text(original, encoding="utf-8")

        await _update_knowledge_frontmatter(knowledge_file)

        assert knowledge_file.read_text(encoding="utf-8") == original

    @pytest.mark.asyncio
    async def test_handles_missing_version(self, tmp_path):
        from core.execution.engines.claude._sdk_hooks import _update_knowledge_frontmatter

        knowledge_file = tmp_path / "no_version.md"
        knowledge_file.write_text(
            "---\ncreated_at: '2026-03-01'\n---\n\n# Content",
            encoding="utf-8",
        )

        await _update_knowledge_frontmatter(knowledge_file)

        text = knowledge_file.read_text(encoding="utf-8")
        meta_str = text.split("---")[1]
        meta = yaml.safe_load(meta_str)
        assert meta["version"] == 1

    @pytest.mark.asyncio
    async def test_preserves_body_content(self, tmp_path):
        from core.execution.engines.claude._sdk_hooks import _update_knowledge_frontmatter

        knowledge_file = tmp_path / "preserve.md"
        knowledge_file.write_text(
            "---\nversion: 1\nconfidence: 0.9\n---\n\n# Title\n\nParagraph 1\n\n## Section\n\nParagraph 2",
            encoding="utf-8",
        )

        await _update_knowledge_frontmatter(knowledge_file)

        text = knowledge_file.read_text(encoding="utf-8")
        assert "# Title" in text
        assert "Paragraph 1" in text
        assert "## Section" in text
        assert "Paragraph 2" in text
        meta_str = text.split("---")[1]
        meta = yaml.safe_load(meta_str)
        assert meta["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_handles_nonexistent_file(self, tmp_path):
        from core.execution.engines.claude._sdk_hooks import _update_knowledge_frontmatter

        await _update_knowledge_frontmatter(tmp_path / "does_not_exist.md")

    @pytest.mark.asyncio
    async def test_knowledge_subdirectory(self, tmp_path):
        """Verify hook fires for files in knowledge/ subdirectories."""
        from core.execution.engines.claude._sdk_hooks import _build_post_tool_hook

        knowledge_dir = tmp_path / "knowledge" / "subdir"
        knowledge_dir.mkdir(parents=True)
        test_file = knowledge_dir / "deep.md"
        test_file.write_text("---\nversion: 1\n---\n\n# Deep", encoding="utf-8")

        hook = _build_post_tool_hook(tmp_path)
        result = await hook(
            {"tool_name": "Write", "tool_input": {"file_path": str(test_file)}},
            None,
            None,
        )
        assert result.get("async_") is True
