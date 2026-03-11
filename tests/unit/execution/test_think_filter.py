"""Tests for StreamingThinkFilter and strip_thinking_tags."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from core.execution.base import StreamingThinkFilter, strip_thinking_tags


# ── strip_thinking_tags ──────────────────────────────────────


class TestStripThinkingTags:
    def test_no_think_tags(self):
        thinking, response = strip_thinking_tags("Hello world")
        assert thinking == ""
        assert response == "Hello world"

    def test_with_think_tags(self):
        text = "<think>reasoning here</think>actual response"
        thinking, response = strip_thinking_tags(text)
        assert thinking == "reasoning here"
        assert response == "actual response"

    def test_think_tag_stripped_from_thinking(self):
        text = "<think>some thinking</think>response"
        thinking, response = strip_thinking_tags(text)
        assert "<think>" not in thinking
        assert thinking == "some thinking"

    def test_empty_think_block(self):
        text = "<think></think>response"
        thinking, response = strip_thinking_tags(text)
        assert thinking == ""
        assert response == "response"

    def test_multiline_thinking(self):
        text = "<think>line1\nline2\nline3</think>response"
        thinking, response = strip_thinking_tags(text)
        assert thinking == "line1\nline2\nline3"
        assert response == "response"

    def test_no_closing_tag(self):
        text = "<think>unclosed thinking"
        thinking, response = strip_thinking_tags(text)
        assert thinking == ""
        assert response == text

    def test_whitespace_after_closing_tag(self):
        text = "<think>thought</think>  \nresponse"
        thinking, response = strip_thinking_tags(text)
        assert thinking == "thought"

    def test_missing_open_tag(self):
        """vLLM reasoning parser may strip <think> but leave </think>."""
        text = "reasoning here</think>actual response"
        thinking, response = strip_thinking_tags(text)
        assert thinking == "reasoning here"
        assert response == "actual response"


# ── StreamingThinkFilter ─────────────────────────────────────


class TestStreamingThinkFilter:
    def test_no_think_tags_passthrough(self):
        f = StreamingThinkFilter()
        thinking, text = f.feed("Hello world")
        # Short non-think content is buffered during probe phase
        assert thinking == ""
        assert text == ""
        # Flush releases the buffered text
        flushed = f.flush()
        assert flushed == "Hello world"

    def test_think_tag_in_single_chunk(self):
        f = StreamingThinkFilter()
        thinking, text = f.feed("<think>reasoning</think>response")
        assert "reasoning" in thinking
        assert "<think>" not in thinking
        assert text == "response"

    def test_think_tag_across_chunks(self):
        f = StreamingThinkFilter()
        t1, r1 = f.feed("<thi")
        assert t1 == "" and r1 == ""

        t2, r2 = f.feed("nk>my thinking</think>response text")
        assert "<think>" not in t2
        assert "my thinking" in t2
        assert r2 == "response text"

    def test_think_tag_stripped_from_output(self):
        f = StreamingThinkFilter()
        thinking, text = f.feed("<think>hello</think>world")
        assert not thinking.startswith("<think>")
        assert thinking == "hello"
        assert text == "world"

    def test_flush_without_closing_tag(self):
        f = StreamingThinkFilter()
        t, r = f.feed("<think>partial thinking")
        assert t == "" and r == ""
        flushed = f.flush()
        assert "partial thinking" in flushed

    def test_flush_empty_when_complete(self):
        f = StreamingThinkFilter()
        f.feed("<think>thought</think>response")
        flushed = f.flush()
        assert flushed == ""

    def test_non_think_content_immediate_passthrough(self):
        f = StreamingThinkFilter()
        t1, r1 = f.feed("regular content")
        assert t1 == "" and r1 == "regular content"
        t2, r2 = f.feed(" more content")
        assert t2 == "" and r2 == " more content"

    def test_after_done_passthrough(self):
        f = StreamingThinkFilter()
        f.feed("<think>thought</think>first")
        t, r = f.feed("second")
        assert t == "" and r == "second"

    def test_response_newline_stripped(self):
        f = StreamingThinkFilter()
        t, r = f.feed("<think>thought</think>\n\nresponse")
        assert r == "response"

    def test_whitespace_before_think_tag(self):
        f = StreamingThinkFilter()
        t, r = f.feed("  <think>thought</think>response")
        assert "thought" in t
        assert r == "response"

    def test_buffer_overflow_safety_valve(self):
        f = StreamingThinkFilter()
        huge = "<think>" + "x" * 60_000
        t, r = f.feed(huge)
        assert r != ""
        assert t == ""

    # ── Pattern 2: missing <think> but </think> present ──────

    def test_missing_open_tag_single_chunk(self):
        """vLLM reasoning parser may strip <think> but leave </think>."""
        f = StreamingThinkFilter()
        t, r = f.feed("reasoning content here</think>\n\nactual response")
        assert "reasoning content here" in t
        assert r == "actual response"

    def test_missing_open_tag_across_chunks(self):
        """Thinking without <think> spread across multiple chunks."""
        f = StreamingThinkFilter()
        t1, r1 = f.feed("I need to ")
        assert t1 == "" and r1 == ""

        t2, r2 = f.feed("analyze this carefully")
        assert t2 == "" and r2 == ""

        t3, r3 = f.feed("</think>\n\nHere is my response")
        assert "I need to analyze this carefully" in t3
        assert r3 == "Here is my response"

    def test_missing_open_tag_probe_limit(self):
        """Content without any think tags should pass through after probe limit."""
        f = StreamingThinkFilter()
        # Feed content well beyond probe limit without any </think>
        long_text = "x" * 600
        t, r = f.feed(long_text)
        assert t == ""
        assert r == long_text

    def test_missing_open_tag_gradual_probe(self):
        """Content without think tags, fed in small chunks."""
        f = StreamingThinkFilter()
        results = []
        for i in range(100):
            t, r = f.feed(f"chunk{i} ")
            results.append((t, r))

        # Eventually the probe limit is hit and text is released
        all_text = "".join(r for _, r in results)
        all_think = "".join(t for t, _ in results)
        assert all_think == ""
        assert "chunk0" in all_text

    def test_missing_open_tag_flush(self):
        """Flush with content still probing (no </think> found)."""
        f = StreamingThinkFilter()
        t, r = f.feed("short content")
        assert t == "" and r == ""
        flushed = f.flush()
        assert flushed == "short content"
