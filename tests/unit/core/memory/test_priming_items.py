from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.memory.activity import ActivityEntry
from core.memory.priming import channel_c, channel_f, outbound
from core.memory.priming.channel_e import _itemize_pending_tasks
from core.memory.priming.consolidate import consolidate_items
from core.memory.priming.constants import (
    _BUDGET_IMPORTANT_KNOWLEDGE,
    _BUDGET_RECENT_ACTIVITY,
    _BUDGET_RELATED_KNOWLEDGE,
)
from core.memory.priming.engine import PrimingEngine
from core.memory.priming.items import ItemizedMemory, MemoryItem, render_items, select_within_budget
from core.memory.priming.result import PrimingResult
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


def test_consolidate_drops_old_keys_long_text_matches_and_duplicate_refs() -> None:
    shared = "これは時刻だけが異なる重複本文です。" * 8
    items = {
        "recent_activity": (
            MemoryItem("recent_activity", "same", "old", updated="2026-09-06"),
            MemoryItem("recent_activity", "same", "new", updated="2026-09-07"),
            MemoryItem("recent_activity", "a", f"[10:00] {shared} activity suffix"),
        ),
        "episodes": (MemoryItem("episodes", "b", f"[11:30] prefix {shared}"),),
        "important_knowledge": (
            MemoryItem("important_knowledge", "chunk-1", "old ref", ref="knowledge/rule.md", updated="2026-01"),
            MemoryItem("important_knowledge", "chunk-2", "new ref", ref="knowledge/rule.md", updated="2026-09"),
        ),
    }

    result = consolidate_items(PrimingResult(items=items))

    assert [item.text for item in result.items["recent_activity"]] == ["new", f"[10:00] {shared} activity suffix"]
    assert result.items["episodes"] == ()
    assert [item.text for item in result.items["important_knowledge"]] == ["new ref"]
    assert result.related_knowledge.count("knowledge/rule.md") == 0


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
                "updated_at": "2026-01-01T00:00:00+09:00",
            },
        ),
        Document(
            id="new",
            content="# A much longer but newer title\n\n| chatID | 名称 | 理由 |",
            metadata={
                "source_file": "knowledge/new.md",
                "anima": "mei",
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
async def test_prime_memories_item_budgets_and_cross_channel_dedup(tmp_path: Path, monkeypatch) -> None:
    anima_dir = tmp_path / "animas" / "mei"
    (anima_dir / "knowledge").mkdir(parents=True)
    (anima_dir / "episodes").mkdir()
    engine = PrimingEngine(anima_dir)
    repeated_key = "2026-09-07T12:00:00+09:00|chat|human"
    activity_items = tuple(
        MemoryItem(
            "recent_activity",
            repeated_key if index == 0 else f"activity-{index}",
            f"活動{index}:" + "あ" * 190,
            updated=f"2026-09-07T12:{index:02d}:00+09:00",
            rank=float(index),
        )
        for index in range(10)
    )
    knowledge_items = tuple(
        MemoryItem(
            "important_knowledge",
            repeated_key if index == 0 else f"knowledge-{index}",
            f"知識{index}:" + "い" * 190 + f' -> read_memory_file(path="knowledge/{index}.md")',
            ref=f"knowledge/{index}.md",
            updated=f"2026-09-07T11:{index:02d}:00+09:00",
            rank=float(index),
        )
        for index in range(10)
    )

    async def empty(*args, **kwargs):
        return ""

    async def activity(*args, **kwargs):
        return ItemizedMemory(render_items(activity_items, ""), activity_items)

    async def knowledge(*args, **kwargs):
        return ItemizedMemory(
            render_items(knowledge_items, "### [IMPORTANT] Knowledge (summary pointers)"),
            knowledge_items,
        )

    monkeypatch.setattr(engine, "_channel_a_sender_profile", empty)
    monkeypatch.setattr(engine, "_channel_b_recent_activity", activity)
    monkeypatch.setattr(engine, "_channel_c0_important_knowledge", knowledge)
    monkeypatch.setattr(engine, "_channel_c_related_knowledge", lambda *args, **kwargs: empty_pair())
    monkeypatch.setattr(engine, "_channel_e_pending_tasks", empty)
    monkeypatch.setattr(engine, "_collect_recent_outbound", empty)
    monkeypatch.setattr(engine, "_channel_f_episodes", empty)
    monkeypatch.setattr(engine, "_collect_pending_human_notifications", empty)
    monkeypatch.setattr(engine, "_channel_g_graph_context", empty)

    result = await engine.prime_memories("重複を確認", enable_dynamic_budget=False)

    assert estimate_tokens(result.recent_activity) <= _BUDGET_RECENT_ACTIVITY
    assert estimate_tokens(result.related_knowledge) <= _BUDGET_RELATED_KNOWLEDGE
    emitted_keys = [item.key for items in result.items.values() for item in items]
    assert emitted_keys.count(repeated_key) == 1
    assert estimate_tokens(result.related_knowledge) <= _BUDGET_IMPORTANT_KNOWLEDGE


async def empty_pair() -> tuple[str, str]:
    return "", ""
