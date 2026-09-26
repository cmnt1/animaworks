from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.memory.activity import ActivityEntry
from core.memory.priming import channel_c, channel_f, outbound
from core.memory.priming.channel_e import _itemize_pending_tasks
from core.memory.priming.engine import PrimingEngine
from core.memory.priming.items import ItemizedMemory, MemoryItem, render_items, select_within_budget
from core.memory.rag.store import Document, SearchResult
from core.prompt.tokens import estimate_tokens


def test_select_within_budget_keeps_whole_items_in_priority_order() -> None:
    lower = MemoryItem("recent_activity", "lower", "低" * 40, updated="2026-09-07T10:00:00+09:00", rank=1)
    older = MemoryItem("recent_activity", "older", "古" * 40, updated="2026-09-07T09:00:00+09:00", rank=2)
    newer = MemoryItem("recent_activity", "newer", "新" * 40, updated="2026-09-07T11:00:00+09:00", rank=2)
    budget = estimate_tokens(render_items([newer, older], ""))

    selected = select_within_budget([lower, older, newer], budget)

    assert selected == [newer, older]
    assert estimate_tokens(render_items(selected, "")) <= budget
    assert all(item.text in render_items(selected, "") for item in selected)
    assert lower.text not in render_items(selected, "")


def test_sentence_boundary_trim_handles_japanese_and_english() -> None:
    from core.memory.activity import ActivityLogger
    from core.memory.priming.channel_b import _format_entry_at_sentence_boundary

    for prefix, boundary in (("日" * 130, "。"), ("English words " * 11, "!")):
        entry = ActivityEntry(
            ts="2026-09-08T12:00:00+09:00",
            type="message_received",
            content=prefix + boundary + "切り捨て対象" * 30,
            from_person="human",
        )

        rendered = _format_entry_at_sentence_boundary(
            ActivityLogger(Path("/tmp/test-anima")),
            entry,
            content_trim=200,
        )

        before_pointer = rendered.split("\n  ->", 1)[0]
        assert before_pointer.endswith(boundary)
        assert "切り捨て対象" not in before_pointer


def test_sentence_boundary_trim_uses_ellipsis_when_boundary_is_too_early() -> None:
    from core.memory.activity import ActivityLogger
    from core.memory.priming.channel_b import _format_entry_at_sentence_boundary

    content = "短い文。" + "続" * 250
    entry = ActivityEntry(
        ts="2026-09-08T12:00:00+09:00",
        type="message_received",
        content=content,
        from_person="human",
    )

    rendered = _format_entry_at_sentence_boundary(
        ActivityLogger(Path("/tmp/test-anima")),
        entry,
        content_trim=200,
    )

    assert content[:200] + "…" in rendered


def test_pending_tasks_are_split_with_task_ids_as_keys() -> None:
    items = _itemize_pending_tasks(
        "## Active Parallel Tasks\n"
        "- [task-a] First task (running 1m)\n"
        "  first description\n"
        "- [task-b] Second task (running 2m)"
    )

    assert [item.key for item in items] == ["task-a", "task-b"]
    assert "first description" in items[0].text
    assert "Second task" in items[1].text


@pytest.mark.asyncio
async def test_c0_uses_title_for_table_header_and_orders_by_updated(tmp_path: Path, monkeypatch) -> None:
    anima_dir = tmp_path / "animas" / "mei"
    knowledge_dir = anima_dir / "knowledge"
    knowledge_dir.mkdir(parents=True)
    docs = [
        Document(
            id="old",
            content="# Very short old title\n\nUseful old summary",
            metadata={
                "source_file": "knowledge/old.md",
                "anima": "mei",
                "importance": "important",
                "updated_at": "2026-01-01T00:00:00+09:00",
            },
        ),
        Document(
            id="new",
            content="# A much longer but newer title\n\n| chatID | 名称 | 理由 |",
            metadata={
                "source_file": "knowledge/new.md",
                "anima": "mei",
                "importance": "important",
                "updated_at": "2026-09-07T00:00:00+09:00",
            },
        ),
    ]
    retriever = MagicMock()
    retriever.get_important_chunks.return_value = [SearchResult(document=doc, score=1.0) for doc in docs]

    async def direct_call(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(channel_c.asyncio, "to_thread", direct_call)
    output = await channel_c.channel_c0_important_knowledge(anima_dir, knowledge_dir, lambda: retriever)

    assert "| chatID | 名称 | 理由 |" not in output
    assert output.index("A much longer but newer title") < output.index("Very short old title")
    assert output.items[0].ref == "knowledge/new.md"


@pytest.mark.asyncio
async def test_channel_f_returns_one_item_per_episode(tmp_path: Path, monkeypatch) -> None:
    anima_dir = tmp_path / "animas" / "mei"
    episodes_dir = anima_dir / "episodes"
    episodes_dir.mkdir(parents=True)
    searcher = MagicMock()
    searcher.last_search_meta = {"abstain": False}
    searcher.search_many.return_value = [
        {
            "doc_id": "mei/episodes/2026-09-01.md#0",
            "source_file": "episodes/2026-09-01.md",
            "content": "# Release retrospective",
            "score": 0.75,
        }
    ]

    async def direct_call(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(channel_f.asyncio, "to_thread", direct_call)
    monkeypatch.setattr(channel_f, "build_unified_searcher", lambda *args: searcher)
    monkeypatch.setattr(channel_f.MemoryIndexer, "is_ragignored", lambda path: False)

    output = await channel_f.channel_f_episodes(
        anima_dir,
        episodes_dir,
        lambda: None,
        ["release"],
        message="release",
    )

    assert len(output.items) == 1
    assert output.items[0].key == "episodes/2026-09-01.md"
    assert output.items[0].updated == "2026-09-01"
    assert output.items[0].rank == 0.75


@pytest.mark.asyncio
async def test_recent_outbound_returns_one_item_per_activity(tmp_path: Path, monkeypatch) -> None:
    anima_dir = tmp_path / "animas" / "mei"
    anima_dir.mkdir(parents=True)
    entry = ActivityEntry(
        ts="2026-09-07T12:00:00+09:00",
        type="message_sent",
        summary="release report sent",
        from_person="mei",
        to_person="human",
    )

    class FakeActivityLogger:
        def __init__(self, path: Path) -> None:
            assert path == anima_dir

        def recent(self, **kwargs):
            return [entry]

    monkeypatch.setattr("core.memory.activity.ActivityLogger", FakeActivityLogger)
    monkeypatch.setattr(outbound, "now_local", lambda: datetime.fromisoformat(entry.ts))

    output = await outbound.collect_recent_outbound(anima_dir)

    assert len(output.items) == 1
    assert output.items[0].key == f"{entry.ts}||mei"
    assert "release report sent" in output.items[0].text


@pytest.mark.asyncio
async def test_prime_memories_selects_items_within_single_budget(tmp_path: Path, monkeypatch) -> None:
    anima_dir = tmp_path / "animas" / "mei"
    (anima_dir / "knowledge").mkdir(parents=True)
    (anima_dir / "episodes").mkdir()
    engine = PrimingEngine(anima_dir)
    knowledge_items = tuple(
        MemoryItem(
            "related_knowledge",
            f"knowledge/{index}.md",
            f"知識{index}:" + "い" * 30,
            ref=f"knowledge/{index}.md",
            updated=f"2026-09-07T11:0{index}:00+09:00",
            rank=float(index),
        )
        for index in range(10)
    )

    async def empty(*args, **kwargs):
        return ""

    async def knowledge(*args, **kwargs):
        return ItemizedMemory(render_items(knowledge_items, ""), knowledge_items), ItemizedMemory("")

    monkeypatch.setattr(engine, "_channel_a_sender_profile", empty)
    monkeypatch.setattr(engine, "_channel_b_recent_activity", empty)
    monkeypatch.setattr(engine, "_channel_c0_important_knowledge", empty)
    monkeypatch.setattr(engine, "_channel_c_related_knowledge", knowledge)
    monkeypatch.setattr(engine, "_channel_e_pending_tasks", empty)
    monkeypatch.setattr(engine, "_collect_recent_outbound", empty)
    monkeypatch.setattr(engine, "_channel_f_episodes", empty)
    monkeypatch.setattr(engine, "_collect_pending_human_notifications", empty)
    monkeypatch.setattr(engine, "_channel_g_graph_context", empty)

    result = await engine.prime_memories("知識を確認", max_tokens=160)

    # Items are selected whole by rank, emitted intact (never "..."-truncated).
    assert estimate_tokens(result.related_knowledge) <= 160
    assert "..." not in result.related_knowledge
    emitted = [item.rank for item in result.items.get("related_knowledge", ())]
    assert emitted == sorted(emitted, reverse=True)


@pytest.mark.asyncio
async def test_prime_memories_related_keeps_whole_channel_c_item(tmp_path: Path, monkeypatch) -> None:
    anima_dir = tmp_path / "animas" / "mei"
    (anima_dir / "knowledge").mkdir(parents=True)
    (anima_dir / "episodes").mkdir()
    engine = PrimingEngine(anima_dir)
    high = MemoryItem(
        "related_knowledge",
        "knowledge/high.md",
        "📌 上位 " + "甲" * 40,
        ref="knowledge/high.md",
        rank=2,
    )
    low = MemoryItem(
        "related_knowledge",
        "knowledge/low.md",
        "📌 下位 " + "乙" * 40,
        ref="knowledge/low.md",
        rank=1,
    )
    related_items = (low, high)

    async def empty(*args, **kwargs):
        return ""

    async def related(*args, **kwargs):
        return ItemizedMemory(render_items(related_items, ""), related_items), ItemizedMemory("")

    monkeypatch.setattr(engine, "_channel_a_sender_profile", empty)
    monkeypatch.setattr(engine, "_channel_b_recent_activity", empty)
    monkeypatch.setattr(engine, "_channel_c0_important_knowledge", empty)
    monkeypatch.setattr(engine, "_channel_c_related_knowledge", related)
    monkeypatch.setattr(engine, "_channel_e_pending_tasks", empty)
    monkeypatch.setattr(engine, "_collect_recent_outbound", empty)
    monkeypatch.setattr(engine, "_channel_f_episodes", empty)
    monkeypatch.setattr(engine, "_collect_pending_human_notifications", empty)

    budget = estimate_tokens(high.text)
    result = await engine.prime_memories("知識を確認", max_tokens=budget)

    # Only the highest-rank item fits; the whole pointer is kept, never split.
    assert result.related_knowledge == high.text
    assert result.items["related_knowledge"] == (high,)
    assert low.text not in result.related_knowledge
    assert "..." not in result.related_knowledge


async def empty_pair() -> tuple[str, str]:
    return "", ""
