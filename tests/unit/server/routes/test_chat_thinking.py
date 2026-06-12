"""Unit tests for thinking_text handling in SSE done events."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json

from server.routes.chat import _chunk_to_event, _handle_chunk


class TestDoneEventThinkingText:
    """Verify that thinking_text is stripped from done SSE and replaced with thinking_summary."""

    def _make_cycle_done_chunk(self, thinking_text: str = "", summary: str = "response"):
        return {
            "type": "cycle_done",
            "cycle_result": {
                "trigger": "chat",
                "action": "responded",
                "summary": summary,
                "thinking_text": thinking_text,
                "duration_ms": 100,
                "context_usage_ratio": 0.5,
                "session_chained": False,
                "total_turns": 1,
                "tool_call_records": [{"name": "test_tool"}],
                "usage": None,
            },
        }

    def test_thinking_text_removed_from_handle_chunk(self):
        chunk = self._make_cycle_done_chunk(thinking_text="secret thinking")
        sse_str, _ = _handle_chunk(chunk)
        assert sse_str is not None
        data_line = [line for line in sse_str.split("\n") if line.startswith("data:")][0]
        data = json.loads(data_line[len("data:") :])
        assert "thinking_text" not in data
        assert data.get("thinking_summary") == "secret thinking"

    def test_thinking_summary_truncated_to_5000(self):
        long_thinking = "x" * 8000
        chunk = self._make_cycle_done_chunk(thinking_text=long_thinking)
        sse_str, _ = _handle_chunk(chunk)
        data_line = [line for line in sse_str.split("\n") if line.startswith("data:")][0]
        data = json.loads(data_line[len("data:") :])
        assert len(data["thinking_summary"]) == 5000

    def test_empty_thinking_text_gives_null_summary(self):
        chunk = self._make_cycle_done_chunk(thinking_text="")
        sse_str, _ = _handle_chunk(chunk)
        data_line = [line for line in sse_str.split("\n") if line.startswith("data:")][0]
        data = json.loads(data_line[len("data:") :])
        assert data["thinking_summary"] is None

    def test_tool_call_records_removed(self):
        chunk = self._make_cycle_done_chunk(thinking_text="think")
        sse_str, _ = _handle_chunk(chunk)
        data_line = [line for line in sse_str.split("\n") if line.startswith("data:")][0]
        data = json.loads(data_line[len("data:") :])
        assert "tool_call_records" not in data

    def test_chunk_to_event_thinking_text_removed(self):
        chunk = self._make_cycle_done_chunk(thinking_text="secret")
        result = _chunk_to_event(chunk)
        assert result is not None
        event_name, payload = result
        assert event_name == "done"
        assert "thinking_text" not in payload
        assert payload.get("thinking_summary") == "secret"

    def test_chunk_to_event_tool_records_removed(self):
        chunk = self._make_cycle_done_chunk(thinking_text="")
        result = _chunk_to_event(chunk)
        assert result is not None
        _, payload = result
        assert "tool_call_records" not in payload

    # ── Defensive strip_thinking_tags in done event ──────

    def test_handle_chunk_strips_leaked_think_tags_from_summary(self):
        """If summary still contains <think>...</think>, strip and move to thinking_summary."""
        chunk = self._make_cycle_done_chunk(
            thinking_text="",
            summary="<think>leaked reasoning</think>clean response",
        )
        sse_str, clean = _handle_chunk(chunk)
        data_line = [line for line in sse_str.split("\n") if line.startswith("data:")][0]
        data = json.loads(data_line[len("data:") :])
        assert data["summary"] == "clean response"
        assert "<think>" not in data["summary"]
        assert data["thinking_summary"] == "leaked reasoning"
        assert clean == "clean response"

    def test_handle_chunk_strips_missing_open_tag_from_summary(self):
        """vLLM pattern: </think> present but <think> absent in summary."""
        chunk = self._make_cycle_done_chunk(
            thinking_text="",
            summary="reasoning content</think>\n\nactual response",
        )
        sse_str, clean = _handle_chunk(chunk)
        data_line = [line for line in sse_str.split("\n") if line.startswith("data:")][0]
        data = json.loads(data_line[len("data:") :])
        assert data["summary"] == "actual response"
        assert "</think>" not in data["summary"]
        assert "reasoning content" in data["thinking_summary"]

    def test_chunk_to_event_strips_leaked_think_tags(self):
        """WebSocket path also strips leaked think tags from summary."""
        chunk = self._make_cycle_done_chunk(
            thinking_text="",
            summary="<think>ws leaked</think>ws clean",
        )
        result = _chunk_to_event(chunk)
        assert result is not None
        _, payload = result
        assert payload["summary"] == "ws clean"
        assert payload["thinking_summary"] == "ws leaked"

    def test_handle_chunk_preserves_existing_thinking_text(self):
        """If thinking_text is already set, leaked tags don't overwrite it."""
        chunk = self._make_cycle_done_chunk(
            thinking_text="proper thinking from safety net",
            summary="<think>leaked</think>response",
        )
        sse_str, _ = _handle_chunk(chunk)
        data_line = [line for line in sse_str.split("\n") if line.startswith("data:")][0]
        data = json.loads(data_line[len("data:") :])
        assert data["summary"] == "response"
        assert data["thinking_summary"] == "proper thinking from safety net"


class TestMeetingRedirectEvent:
    """Verify meeting redirect stream chunks keep deduplication metadata."""

    def test_handle_chunk_preserves_redirect_id(self):
        chunk = {
            "type": "meeting_redirect",
            "room_id": "abc123def456",
            "redirect_id": "redirect-1",
            "from": "sakura",
            "to": "rin",
            "content": "Please share status",
            "intent": "question",
            "ts": "2026-06-12T00:00:00+09:00",
        }

        sse_str, response_text = _handle_chunk(chunk)

        assert response_text == ""
        assert sse_str is not None
        data_line = [line for line in sse_str.split("\n") if line.startswith("data:")][0]
        data = json.loads(data_line[len("data:") :])
        assert data["redirect_id"] == "redirect-1"

    def test_chunk_to_event_preserves_redirect_id(self):
        result = _chunk_to_event(
            {
                "type": "meeting_redirect",
                "room_id": "abc123def456",
                "redirect_id": "redirect-1",
                "from": "sakura",
                "to": "rin",
                "content": "Please share status",
                "intent": "question",
                "ts": "2026-06-12T00:00:00+09:00",
            }
        )

        assert result is not None
        event_name, payload = result
        assert event_name == "meeting_redirect"
        assert payload["redirect_id"] == "redirect-1"
