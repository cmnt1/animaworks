"""Unit tests for priming query quality (build_queries, _build_context_query)."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from core.memory.priming.utils import _build_context_query, build_queries

# ── build_queries: no conversation context ──


class TestBuildQueriesNoContext:
    """build_queries without recent_human_messages."""

    def test_message_only_one_query(self):
        """Message only → 1 query."""
        result = build_queries("Hello world", [])
        assert result == ["Hello world"]

    def test_message_and_keywords_two_queries(self):
        """Message + keywords → 2 queries."""
        result = build_queries("このIssueを裏で実装して", ["Issue", "裏", "実装"])
        assert len(result) == 2
        assert result[0] == "このIssueを裏で実装して"
        assert result[1] == "Issue 裏 実装"

    def test_duplicate_message_keyword_one_query(self):
        """Duplicate message/keyword → 1 query (deduplicated)."""
        # When kw_query equals msg_query (e.g. message is "foo" and keywords are ["foo"])
        result = build_queries("foo", ["foo"])
        assert len(result) == 1
        assert result[0] == "foo"


# ── build_queries: with conversation context ──


class TestBuildQueriesWithContext:
    """build_queries with recent_human_messages adds 3rd context query."""

    def test_recent_human_messages_adds_third_query(self):
        """recent_human_messages provided → 3 queries."""
        result = build_queries(
            "最新の進捗は？",
            ["進捗"],
            recent_human_messages=["昨日のタスクを完了した", "今日は新機能を実装する"],
        )
        assert len(result) == 3
        assert result[0] == "最新の進捗は？"
        assert result[1] == "進捗"
        assert "昨日のタスクを完了した" in result[2]
        assert "今日は新機能を実装する" in result[2]

    def test_context_query_different_from_message_included(self):
        """Context query different from message → included."""
        result = build_queries(
            "最新の進捗は？",
            [],
            recent_human_messages=["別の話題のメッセージ"],
        )
        assert len(result) == 2
        assert result[0] == "最新の進捗は？"
        assert result[1] == "別の話題のメッセージ"

    def test_context_query_same_as_message_not_duplicated(self):
        """Context query same as message → not duplicated."""
        msg = "同じメッセージ"
        result = build_queries(
            msg,
            [],
            recent_human_messages=[msg],
        )
        assert len(result) == 1
        assert result[0] == msg


# ── _build_context_query truncation ──


class TestBuildContextQueryTruncation:
    """_build_context_query truncation behavior."""

    def test_total_under_500_all_included(self):
        """Total under 500 chars → all messages included."""
        msgs = ["Short msg 1", "Short msg 2", "Short msg 3"]
        result = _build_context_query(msgs, max_chars=500)
        assert result == "Short msg 1\nShort msg 2\nShort msg 3"

    def test_total_over_500_truncated_at_boundary(self):
        """Total over 500 chars → truncated at boundary."""
        msgs = ["a" * 200, "b" * 200, "c" * 200]  # 600 chars total
        result = _build_context_query(msgs, max_chars=500)
        # Content sum capped at 500; newlines add a few chars
        assert len(result) <= 510
        assert "a" * 200 in result
        # Second message included; third may be partial
        assert "b" * 200 in result or "b" in result

    def test_empty_list_returns_empty_string(self):
        """Empty list → empty string."""
        result = _build_context_query([], max_chars=500)
        assert result == ""

    def test_single_long_message_truncated_to_500(self):
        """Single long message → truncated to 500 chars."""
        long_msg = "x" * 1000
        result = _build_context_query([long_msg], max_chars=500)
        assert len(result) == 500
        assert result == "x" * 500


class TestBuildQueriesEdgeCases:
    """Edge cases for build_queries."""

    def test_none_message_returns_keyword_only(self):
        result = build_queries(None, ["topic"])  # type: ignore[arg-type]
        assert result == ["topic"]

    def test_none_message_empty_keywords(self):
        result = build_queries(None, [])  # type: ignore[arg-type]
        assert result == []

    def test_empty_message_and_keywords(self):
        result = build_queries("", [])
        assert result == []
