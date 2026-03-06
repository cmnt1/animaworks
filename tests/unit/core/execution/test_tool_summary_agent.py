"""Tests for 'Agent' tool name support in _tool_summary.py."""
from __future__ import annotations

from core.execution._tool_summary import make_tool_detail_chunk, summarize_tool_args


class TestAgentToolSummary:
    def test_agent_description(self):
        desc = "Research AI safety papers"
        result = summarize_tool_args("Agent", {"description": desc})
        assert result == desc

    def test_agent_truncates_at_80(self):
        desc = "a" * 100
        result = summarize_tool_args("Agent", {"description": desc})
        assert len(result) == 80

    def test_agent_empty_description(self):
        result = summarize_tool_args("Agent", {})
        assert result == ""

    def test_task_still_works(self):
        result = summarize_tool_args("Task", {"description": "Build project"})
        assert result == "Build project"


class TestMakeToolDetailChunkAgent:
    def test_agent_returns_chunk(self):
        chunk = make_tool_detail_chunk("Agent", "tool_a1", {"description": "research"})
        assert chunk is not None
        assert chunk["type"] == "tool_detail"
        assert chunk["tool_name"] == "Agent"
        assert chunk["detail"] == "research"

    def test_agent_empty_returns_none(self):
        chunk = make_tool_detail_chunk("Agent", "tool_a2", {})
        assert chunk is None
