"""Tests for [ACTION-RULE] indexing and retrieval."""

from __future__ import annotations

import pytest

from core.memory.rag.indexer import MemoryIndexer


class TestActionRuleMetadataExtraction:
    """Test _extract_metadata correctly parses [ACTION-RULE] markers."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):

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
        content = "## [ACTION-RULE] 送信前確認\ntrigger_tools: gmail_send\n---\n宛先を確認すること。\n"
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
        content = "## [ACTION-RULE] ルール名\nkeywords: something\n---\n本文\n"
        metadata = self._call_extract(content)
        assert "type" not in metadata or metadata.get("type") != "action_rule"

    def test_action_rule_multiple_trigger_tools_with_spaces(self):
        content = "## [ACTION-RULE] テスト\ntrigger_tools:  call_human ,  send_message , post_channel  \n---\n本文\n"
        metadata = self._call_extract(content)
        assert metadata["type"] == "action_rule"
        assert metadata["trigger_tools"] == "call_human,send_message,post_channel"

    def test_no_action_rule_marker(self):
        content = "## 通常のknowledge\n\nこれはただの知識です。\n"
        metadata = self._call_extract(content)
        assert metadata.get("type") != "action_rule"

    def test_fenced_action_rule_example_is_not_indexed(self):
        """[ACTION-RULE] examples inside ``` fences are not real action rules."""
        content = (
            "Actions are rules that pause before side effects.\n"
            "Here is an example (do not treat as a real rule):\n"
            "```markdown\n"
            "## [ACTION-RULE] 顧客メモ更新前の確認\n"
            "trigger_tools: write_memory_file\n"
            "---\n"
            "メモを更新する前に顧客選択を確認する。\n"
            "```\n"
            "End of guide.\n"
        )
        metadata = self._call_extract(content)
        assert metadata.get("type") != "action_rule"
        assert "trigger_tools" not in metadata

    def test_tilde_fenced_action_rule_example_is_not_indexed(self):
        """~~~ fences are also stripped when evaluating action rules."""
        content = "Guide:\n~~~\n## [ACTION-RULE] 送信前確認\ntrigger_tools: gmail_send\n---\n本文\n~~~\n"
        metadata = self._call_extract(content)
        assert metadata.get("type") != "action_rule"

    def test_action_rule_outside_fence_is_still_indexed(self):
        """A real rule written outside any fence keeps type=action_rule."""
        content = (
            "```\n"
            "## [ACTION-RULE] 例（これ自体は無視）\n"
            "trigger_tools: write_memory_file\n"
            "---\n"
            "例本文\n"
            "```\n"
            "\n"
            "## [ACTION-RULE] 本物のルール\n"
            "trigger_tools: call_human\n"
            "---\n"
            "本当に適用するルール。\n"
        )
        metadata = self._call_extract(content)
        assert metadata["type"] == "action_rule"
        assert metadata["trigger_tools"] == "call_human"

    def test_guide_template_is_not_indexed_as_action_rule(self):
        """The shipped action-rules-guide template must not become an action rule."""
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2] / ".." / ".."
        guide = repo / "templates" / "ja" / "common_knowledge" / "operations" / "action-rules-guide.md"
        metadata = self._call_extract(guide.read_text(encoding="utf-8"))
        assert metadata.get("type") != "action_rule"
        assert "trigger_tools" not in metadata

    def _chunk(self, content: str):
        """Run the real ## chunker (the path used for knowledge/common_knowledge)."""
        indexer = MemoryIndexer.__new__(MemoryIndexer)
        indexer.collection_prefix = "test"
        indexer.anima_dir = self._anima_dir
        indexer.anima_name = "test"
        self._test_file.write_text(content)
        return indexer._chunk_by_markdown_headings(self._test_file, content, "common_knowledge")

    def test_guide_template_chunks_are_not_action_rules(self):
        """Fenced examples must not become action rules even after ## chunking.

        The chunker used to split on ``## [ACTION-RULE] ...`` lines inside the
        guide's code fences, producing chunks without their opening fence that
        were then indexed as real rules (the write_memory_file example blocked
        every memory write in production).
        """
        from pathlib import Path

        repo = Path(__file__).resolve().parents[2] / ".." / ".."
        guide = repo / "templates" / "ja" / "common_knowledge" / "operations" / "action-rules-guide.md"
        chunks = self._chunk(guide.read_text(encoding="utf-8"))
        assert chunks, "guide should produce chunks"
        offenders = [c.content[:60] for c in chunks if c.metadata.get("type") == "action_rule"]
        assert offenders == []
        assert all("trigger_tools" not in c.metadata for c in chunks)

    def test_real_rule_outside_fence_is_chunked_as_action_rule(self):
        content = (
            "# 説明\n\n"
            "## 例\n\n```markdown\n## [ACTION-RULE] 例\ntrigger_tools: call_human\n---\n例\n```\n\n"
            "## [ACTION-RULE] 本物\ntrigger_tools: write_memory_file\nkeywords: memo\n---\n本物のルール。\n"
        )
        chunks = self._chunk(content)
        rules = [c for c in chunks if c.metadata.get("type") == "action_rule"]
        assert len(rules) == 1
        assert rules[0].metadata["trigger_tools"] == "write_memory_file"
        assert "本物" in rules[0].content

    def test_action_rule_without_separator(self):
        """trigger_tools without --- separator should still work."""
        content = "## [ACTION-RULE] テスト\ntrigger_tools: call_human\n\nルール本文がここから始まる。\n"
        metadata = self._call_extract(content)
        assert metadata["type"] == "action_rule"
        assert metadata["trigger_tools"] == "call_human"


class TestActionRuleRetrieverFiltering:
    """Test search_action_rules filters by trigger_tools correctly."""

    def test_trigger_tools_case_insensitive_matching(self):
        from core.memory.rag.retriever import MemoryRetriever

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
