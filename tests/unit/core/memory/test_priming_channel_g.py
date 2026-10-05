from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for Channel G: recent atomic facts in PrimingEngine."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config.schemas import PrimingConfig
from core.i18n import t
from core.memory.priming import PrimingEngine, PrimingResult, channel_g, format_priming_section
from core.text.tokens import estimate_tokens


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    path = tmp_path / "animas" / "test_anima"
    path.mkdir(parents=True)
    (path / "knowledge").mkdir()
    return path


def _searcher(rows: list[dict] | None = None, *, error: Exception | None = None) -> MagicMock:
    searcher = MagicMock()
    searcher.search_many.return_value = rows or []
    if error is not None:
        searcher.search_many.side_effect = error
    searcher.last_search_meta = {"abstain": False}
    return searcher


def _stub_non_recall_channels(monkeypatch: pytest.MonkeyPatch, engine: PrimingEngine) -> None:
    monkeypatch.setattr(engine, "_channel_a_sender_profile", AsyncMock(return_value=""))
    monkeypatch.setattr(engine, "_channel_b_recent_activity", AsyncMock(return_value=""))
    monkeypatch.setattr(engine, "_channel_c0_important_knowledge", AsyncMock(return_value=""))
    monkeypatch.setattr(engine, "_channel_e_pending_tasks", AsyncMock(return_value=""))
    monkeypatch.setattr(engine, "_channel_f_episodes", AsyncMock(return_value=""))
    monkeypatch.setattr(engine, "_collect_recent_outbound", AsyncMock(return_value=""))
    monkeypatch.setattr(engine, "_collect_pending_human_notifications", AsyncMock(return_value=""))


@pytest.mark.asyncio
async def test_collect_recent_facts_formats_fact_and_searches_facts_scope(anima_dir: Path) -> None:
    searcher = _searcher(
        [
            {
                "source_file": "facts/preferences.jsonl",
                "content": "Rin prefers tea",
                "source_entity": "Rin",
                "edge_type": "PREFERS",
                "target_entity": "tea",
            }
        ]
    )
    with (
        patch("core.memory.priming.channel_g.UnifiedMemorySearch", return_value=searcher),
        patch("core.memory.priming.channel_g.get_min_retrieval_score", return_value=0.42),
    ):
        result = await channel_g.collect_recent_facts(
            anima_dir,
            lambda: None,
            ["tea preference"],
            trigger="inbox:alice",
        )

    assert result == "## Recent Facts\n- [Rin PREFERS tea] Rin prefers tea"
    kwargs = searcher.search_many.call_args.kwargs
    assert kwargs["scope"] == "facts"
    assert kwargs["limit"] == 10
    assert kwargs["trigger"] == "inbox"
    assert kwargs["min_score"] == 0.42


@pytest.mark.asyncio
async def test_collect_recent_facts_returns_empty_for_no_hits_or_search_error(anima_dir: Path) -> None:
    searcher = _searcher()
    with patch("core.memory.priming.channel_g.UnifiedMemorySearch", return_value=searcher):
        no_hits = await channel_g.collect_recent_facts(anima_dir, lambda: None, ["unmatched"])

    assert no_hits == ""

    failed_searcher = _searcher(error=RuntimeError("search failed"))
    with patch("core.memory.priming.channel_g.UnifiedMemorySearch", return_value=failed_searcher):
        failed = await channel_g.collect_recent_facts(anima_dir, lambda: None, ["query"])

    assert failed == ""


@pytest.mark.asyncio
async def test_collect_recent_facts_excludes_denied_sources(
    anima_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denied_root = anima_dir / "facts" / "private"
    denied_root.mkdir(parents=True)
    monkeypatch.setattr(channel_g, "load_denied_roots", lambda _anima_dir: (denied_root.resolve(),))
    searcher = _searcher(
        [
            {
                "source_file": "facts/private/secret.jsonl",
                "content": "A private fact",
                "source_entity": "Rin",
                "edge_type": "KNOWS",
                "target_entity": "secret",
            }
        ]
    )
    with patch("core.memory.priming.channel_g.UnifiedMemorySearch", return_value=searcher):
        result = await channel_g.collect_recent_facts(anima_dir, lambda: None, ["secret"])

    assert result == ""


@pytest.mark.asyncio
async def test_collect_recent_facts_truncates_to_budget(anima_dir: Path) -> None:
    searcher = _searcher(
        [
            {
                "source_file": f"facts/fact-{index}.jsonl",
                "content": "A long matching fact " * 80,
                "source_entity": "Rin",
                "edge_type": "RELATES_TO",
                "target_entity": "memory",
            }
            for index in range(5)
        ]
    )
    with patch("core.memory.priming.channel_g.UnifiedMemorySearch", return_value=searcher):
        result = await channel_g.collect_recent_facts(
            anima_dir,
            lambda: None,
            ["memory"],
            budget_tokens=32,
        )

    assert result
    assert estimate_tokens(result) <= 32
    # The header and the best match survive; the tail is cut.
    assert result.startswith(t("priming.recent_facts_header"))


def test_priming_result_tracks_recent_facts() -> None:
    result = PrimingResult(recent_facts="fact")

    assert not result.is_empty()
    assert result.total_chars() == len("fact")
    assert result.estimated_tokens() == estimate_tokens("fact")


def test_format_priming_section_places_recent_facts_after_related_knowledge() -> None:
    result = PrimingResult(
        related_knowledge="C channel marker",
        recent_facts="## Recent Facts\n- [Rin PREFERS tea] Rin prefers tea",
    )

    formatted = format_priming_section(result)

    assert formatted.index("C channel marker") < formatted.index("## Recent Facts")


@pytest.mark.asyncio
async def test_engine_includes_recent_facts_in_formatted_chat_priming(
    anima_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = PrimingEngine(anima_dir)
    _stub_non_recall_channels(monkeypatch, engine)
    monkeypatch.setattr(engine, "_recent_facts_settings", lambda: (True, 500))
    monkeypatch.setattr(engine, "_channel_c_related_knowledge", AsyncMock(return_value=("", "")))
    collect_facts = AsyncMock(return_value="## Recent Facts\n- [Rin PREFERS tea] Rin prefers tea")
    monkeypatch.setattr(engine, "_channel_g_recent_facts", collect_facts)

    result = await engine.prime_memories("What tea does Rin prefer?", channel="chat")
    formatted = format_priming_section(result)

    collect_facts.assert_awaited_once()
    assert collect_facts.await_args.kwargs["budget_tokens"] == 500
    assert collect_facts.await_args.kwargs["trigger"] == "chat"
    assert "## Recent Facts" in formatted
    assert "[Rin PREFERS tea] Rin prefers tea" in formatted


@pytest.mark.asyncio
async def test_engine_skips_recent_facts_when_disabled(
    anima_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = PrimingEngine(anima_dir)
    _stub_non_recall_channels(monkeypatch, engine)
    monkeypatch.setattr(engine, "_recent_facts_settings", lambda: (False, 500))
    monkeypatch.setattr(engine, "_channel_c_related_knowledge", AsyncMock(return_value=("", "")))
    collect_facts = AsyncMock(return_value="## Recent Facts\n- hidden")
    monkeypatch.setattr(engine, "_channel_g_recent_facts", collect_facts)

    result = await engine.prime_memories("A question", channel="chat")

    collect_facts.assert_not_awaited()
    assert result.recent_facts == ""
    assert "## Recent Facts" not in format_priming_section(result)


@pytest.mark.asyncio
async def test_engine_recent_facts_budget_does_not_reduce_channel_c_budget(
    anima_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = PrimingEngine(anima_dir)
    _stub_non_recall_channels(monkeypatch, engine)
    monkeypatch.setattr(engine, "_recent_facts_settings", lambda: (True, 500))
    monkeypatch.setattr(engine, "_channel_c_related_knowledge", AsyncMock(return_value=("C" * 1000, "")))
    monkeypatch.setattr(engine, "_channel_g_recent_facts", AsyncMock(return_value="G" * 1000))

    result = await engine.prime_memories("A question", channel="chat", max_tokens=100)

    assert 90 <= estimate_tokens(result.related_knowledge) <= 100
    assert result.recent_facts == "G" * 1000


def test_recent_facts_config_defaults() -> None:
    config = PrimingConfig()

    assert config.recent_facts_enabled is True
    assert config.recent_facts_max_tokens == 500


def test_engine_reads_recent_facts_config(
    anima_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = PrimingEngine(anima_dir)
    priming = PrimingConfig(recent_facts_enabled=False, recent_facts_max_tokens=123)
    monkeypatch.setattr("core.config.models.load_config", lambda: SimpleNamespace(priming=priming))

    assert engine._recent_facts_settings() == (False, 123)


@pytest.mark.asyncio
async def test_collect_recent_facts_caps_each_fact(anima_dir: Path) -> None:
    searcher = _searcher(
        [
            {"source_file": "facts/a.jsonl", "content": "x" * 1000},
            {"source_file": "facts/b.jsonl", "content": "second fact"},
        ]
    )
    with patch("core.memory.priming.channel_g.UnifiedMemorySearch", return_value=searcher):
        result = await channel_g.collect_recent_facts(anima_dir, lambda: None, ["memory"], budget_tokens=2000)

    lines = result.splitlines()[1:]
    assert len(lines[0]) <= channel_g._MAX_FACT_CHARS + 2
    assert lines[1] == "- second fact"
