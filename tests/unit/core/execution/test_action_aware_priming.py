"""Tests for ACTION-RULE attachment in the PostToolUse SDK hook."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class FakeRule:
    doc_id: str
    content: str
    score: float = 0.95


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    """Create a minimal anima directory structure."""
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "run").mkdir()
    return tmp_path


class TestPostToolUseActionAttachment:
    """PostToolUse attaches relevant ACTION-RULE bodies via additionalContext."""

    @pytest.mark.asyncio
    async def test_action_tool_attaches_rule_body(self, anima_dir, monkeypatch):
        from core.execution._sdk_hooks import _build_post_tool_hook
        from core.memory import action_gate

        monkeypatch.setattr(
            action_gate,
            "_search_action_rules",
            lambda *args, **kwargs: [
                FakeRule(
                    "mei/knowledge/send-rule.md#0",
                    "## [ACTION-RULE] Send check\ntrigger_tools: send_message\n---\nConfirm first.",
                    0.95,
                )
            ],
        )

        hook = _build_post_tool_hook(anima_dir)
        result = await hook(
            {"hook_event_name": "PostToolUse", "tool_name": "mcp__aw__send_message", "tool_input": {"content": "hi"}},
            "t1",
            {"signal": None},
        )

        assert result["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        additional = result["hookSpecificOutput"]["additionalContext"]
        assert "## [ACTION-RULE] Send check" in additional
        assert "<action-rule path=" in additional
        assert "Confirm first." in additional

    @pytest.mark.asyncio
    async def test_action_tool_with_no_rules_returns_empty(self, anima_dir, monkeypatch):
        from core.execution._sdk_hooks import _build_post_tool_hook
        from core.memory import action_gate

        monkeypatch.setattr(action_gate, "_search_action_rules", lambda *args, **kwargs: [])
        hook = _build_post_tool_hook(anima_dir)

        result = await hook(
            {"hook_event_name": "PostToolUse", "tool_name": "mcp__aw__send_message", "tool_input": {"content": "hi"}},
            "t1",
            {"signal": None},
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_non_action_tool_returns_empty(self, anima_dir):
        from core.execution._sdk_hooks import _build_post_tool_hook

        hook = _build_post_tool_hook(anima_dir)
        result = await hook(
            {"hook_event_name": "PostToolUse", "tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}},
            "t1",
            {"signal": None},
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_search_error_fails_open_to_empty(self, anima_dir, monkeypatch):
        from core.execution._sdk_hooks import _build_post_tool_hook
        from core.memory import action_gate

        def raise_search(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(action_gate, "_search_action_rules", raise_search)
        hook = _build_post_tool_hook(anima_dir)

        result = await hook(
            {"hook_event_name": "PostToolUse", "tool_name": "mcp__aw__send_message", "tool_input": {"content": "hi"}},
            "t1",
            {"signal": None},
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_write_edit_still_runs(self, anima_dir):
        """The original Write/Edit frontmatter path still fires for knowledge files."""
        from core.execution._sdk_hooks import _build_post_tool_hook

        (anima_dir / "knowledge" / "topic.md").write_text("# H1", encoding="utf-8")
        hook = _build_post_tool_hook(anima_dir)
        result = await hook(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(anima_dir / "knowledge" / "topic.md"), "content": "new"},
            },
            "t1",
            {"signal": None},
        )
        # Frontmatter update is fire-and-forget (async_ = True).
        assert result == {"async_": True}
