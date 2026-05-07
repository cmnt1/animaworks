"""Tests for [ACTION-RULE] indexing and retrieval."""

from __future__ import annotations

import pytest

from core.memory.rag.indexer import MemoryIndexer


class TestActionRuleMetadataExtraction:
    """Test _extract_metadata correctly parses [ACTION-RULE] markers."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        from pathlib import Path

        self._anima_dir = tmp_path / "anima"
        self._anima_dir.mkdir()
        knowledge_dir = self._anima_dir / "knowledge"
        knowledge_dir.mkdir()
        self._test_file = knowledge_dir / "test.md"
        self._test_file.write_text("")

    def _call_extract(self, content: str, **kwargs):
        """Call _extract_metadata on a MemoryIndexer instance."""
        indexer = MemoryIndexer.__new__(MemoryIndexer)
        indexer.collection_prefix = "test"
        indexer.anima_dir = self._anima_dir
        self._test_file.write_text(content)
        return indexer._extract_metadata(
            file_path=self._test_file,
            content=content,
            memory_type=kwargs.get("memory_type", "knowledge"),
            chunk_index=kwargs.get("chunk_index", 0),
            total_chunks=kwargs.get("total_chunks", 1),
        )

    def test_basic_action_rule(self):
        content = (
            "## [ACTION-RULE] ペンディング報告前のChatwork確認\n"
            "trigger_tools: call_human, send_message\n"
            "keywords: ペンディング, pending, 報告\n"
            "---\n"
            "報告する前にChatworkを確認すること。\n"
        )
        metadata = self._call_extract(content)
        assert metadata["type"] == "action_rule"
        assert metadata["trigger_tools"] == "call_human,send_message"
        assert metadata["action_rule_keywords"] == "ペンディング,pending,報告"

    def test_action_rule_without_keywords(self):
        content = (
            "## [ACTION-RULE] 送信前確認\n"
            "trigger_tools: gmail_send\n"
            "---\n"
            "宛先を確認すること。\n"
        )
        metadata = self._call_extract(content)
        assert metadata["type"] == "action_rule"
        assert metadata["trigger_tools"] == "gmail_send"
        assert "action_rule_keywords" not in metadata

    def test_action_rule_with_important(self):
        content = (
            "## [ACTION-RULE] [IMPORTANT] 顧客データ変更前の承認\n"
            "trigger_tools: write_memory_file\n"
            "---\n"
            "上司の承認を得ること。\n"
        )
        metadata = self._call_extract(content)
        assert metadata["type"] == "action_rule"
        assert metadata["trigger_tools"] == "write_memory_file"
        assert metadata["importance"] == "important"

    def test_action_rule_missing_trigger_tools(self):
        content = (
            "## [ACTION-RULE] ルール名\n"
            "keywords: something\n"
            "---\n"
            "本文\n"
        )
        metadata = self._call_extract(content)
        assert "type" not in metadata or metadata.get("type") != "action_rule"

    def test_action_rule_multiple_trigger_tools_with_spaces(self):
        content = (
            "## [ACTION-RULE] テスト\n"
            "trigger_tools:  call_human ,  send_message , post_channel  \n"
            "---\n"
            "本文\n"
        )
        metadata = self._call_extract(content)
        assert metadata["type"] == "action_rule"
        assert metadata["trigger_tools"] == "call_human,send_message,post_channel"

    def test_no_action_rule_marker(self):
        content = "## 通常のknowledge\n\nこれはただの知識です。\n"
        metadata = self._call_extract(content)
        assert metadata.get("type") != "action_rule"

    def test_action_rule_without_separator(self):
        """trigger_tools without --- separator should still work."""
        content = (
            "## [ACTION-RULE] テスト\n"
            "trigger_tools: call_human\n"
            "\n"
            "ルール本文がここから始まる。\n"
        )
        metadata = self._call_extract(content)
        assert metadata["type"] == "action_rule"
        assert metadata["trigger_tools"] == "call_human"


class TestActionRuleRetrieverFiltering:
    """Test search_action_rules filters by trigger_tools correctly."""

    def test_trigger_tools_case_insensitive_matching(self):
        from core.memory.rag.retriever import MemoryRetriever, RetrievalResult

        retriever = MemoryRetriever.__new__(MemoryRetriever)

        mock_results = [
            ("id1", "rule content", 0.90, {"type": "action_rule", "trigger_tools": "call_human,send_message"}),
            ("id2", "other rule", 0.85, {"type": "action_rule", "trigger_tools": "gmail_send"}),
        ]

        def mock_search(query, collection, top_k, filter_metadata=None):
            return mock_results

        retriever._vector_search_collection = mock_search

        results = retriever.search_action_rules("call_human", "test query", "mei")
        assert len(results) == 1
        assert results[0].doc_id == "id1"

    def test_min_score_filtering(self):
        from core.memory.rag.retriever import MemoryRetriever

        retriever = MemoryRetriever.__new__(MemoryRetriever)

        mock_results = [
            ("id1", "rule content", 0.75, {"type": "action_rule", "trigger_tools": "call_human"}),
        ]

        retriever._vector_search_collection = lambda *a, **kw: mock_results

        results = retriever.search_action_rules("call_human", "test", "mei", min_score=0.80)
        assert len(results) == 0

    def test_empty_results(self):
        from core.memory.rag.retriever import MemoryRetriever

        retriever = MemoryRetriever.__new__(MemoryRetriever)
        retriever._vector_search_collection = lambda *a, **kw: []

        results = retriever.search_action_rules("call_human", "test", "mei")
        assert results == []

    def test_results_sorted_by_score(self):
        from core.memory.rag.retriever import MemoryRetriever

        retriever = MemoryRetriever.__new__(MemoryRetriever)

        mock_results = [
            ("id1", "rule A", 0.82, {"type": "action_rule", "trigger_tools": "call_human"}),
            ("id2", "rule B", 0.95, {"type": "action_rule", "trigger_tools": "call_human"}),
            ("id3", "rule C", 0.88, {"type": "action_rule", "trigger_tools": "call_human"}),
        ]

        retriever._vector_search_collection = lambda *a, **kw: mock_results

        results = retriever.search_action_rules("call_human", "test", "mei")
        assert results[0].doc_id == "id2"
        assert results[1].doc_id == "id3"
        assert results[2].doc_id == "id1"
