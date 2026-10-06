from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from core.anima.lifecycle import LifecycleMixin
from core.config.models import AnimaWorksConfig, ConsolidationConfig, CredentialConfig
from core.schemas import ModelConfig


def test_episode_extraction_templates_reduce_tool_output_in_all_locales() -> None:
    root = Path(__file__).resolve().parents[3] / "templates"

    for locale in ("ja", "en", "ko"):
        prompt = (root / locale / "prompts/memory/episode_extraction.md").read_text(encoding="utf-8")
        assert "do not copy" in prompt.lower() or "転記しない" in prompt
        assert "one line" in prompt.lower() or "1行" in prompt


@pytest.mark.asyncio
async def test_daily_episode_extracts_facts_per_chunk_and_continues_after_failure() -> None:
    target = date(2026, 10, 2)
    reference = datetime(2026, 10, 3, 2, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    config = AnimaWorksConfig(
        credentials={"anthropic": CredentialConfig(api_key="test")},
        consolidation=ConsolidationConfig(
            llm_model="anthropic/claude-sonnet-4-6",
            llm_credential="anthropic",
            episode_summary_backfill_days=1,
            episode_summary_max_input_bytes=4096,
            episode_summary_max_output_tokens=1234,
        ),
    )

    class FakeEngine:
        def __init__(self) -> None:
            self.anima_dir = Path("/nonexistent/test-anima")
            self.record_calls: list[dict] = []
            self.write_calls: list[tuple[date, str]] = []
            self.extract_facts_from_text_outcome = AsyncMock(
                side_effect=[
                    RuntimeError("first chunk extraction failed"),
                    SimpleNamespace(facts_extracted=2, facts_failed=0),
                ]
            )

        @staticmethod
        def previous_local_day_window(_now=None):
            return target, None, None

        @staticmethod
        def collect_pending_activity_chunks(_day, **_kwargs):
            return ["activity chunk one", "activity chunk two"], False

        @staticmethod
        def resolve_input_profile_for_date(_day, requested_profile):
            return requested_profile

        @staticmethod
        def read_episode_for_date(_day):
            return ""

        @staticmethod
        def _truncate_utf8(text, _max_bytes):
            return text

        @staticmethod
        def _sanitize_llm_output(text):
            return text

        @staticmethod
        def merge_timeline_parts(parts):
            return "\n\n".join(parts)

        def write_consolidated_episode(self, day, content):
            self.write_calls.append((day, content))
            return Path(f"{day}.md")

        def record_consolidated_chunks(self, day, chunks, **kwargs):
            self.record_calls.append({"day": day, "chunks": chunks, **kwargs})

    class FakeAnima(LifecycleMixin):
        pass

    owner = FakeAnima.__new__(FakeAnima)
    owner.name = "test-anima"
    owner.memory = MagicMock()
    owner.memory.read_model_config.return_value = ModelConfig(
        model="anthropic/claude-sonnet-4-6",
        credential="anthropic",
        resolved_mode="A",
    )
    engine = FakeEngine()
    completion = AsyncMock(side_effect=["summary one", "summary two"])
    info = MagicMock()
    background_extractor = object()

    with (
        patch("core.anima.lifecycle.now_local", return_value=reference),
        patch(
            "core.anima.lifecycle.load_prompt",
            side_effect=lambda _name, **kwargs: kwargs["activity_chunk"],
        ),
        patch("core.config.load_config", return_value=config),
        patch("core.llm.oneshot.one_shot_completion", new=completion),
        patch("core.memory.facts.observability.warn_rate_limited"),
        patch("core.anima.lifecycle.logger.info", new=info),
        patch(
            "core.memory.facts.live.build_background_fact_extractor",
            return_value=background_extractor,
        ) as build_extractor,
    ):
        result = await LifecycleMixin._run_daily_episode_summaries(
            owner,
            engine,
            cfg=config,
            model=config.consolidation.llm_model,
            start_mono=0.0,
        )

    assert result.action == "completed"
    assert completion.await_count == 2
    assert all(call.kwargs["max_tokens"] == 1234 for call in completion.await_args_list)
    assert engine.extract_facts_from_text_outcome.await_count == 2
    fact_calls = engine.extract_facts_from_text_outcome.await_args_list
    assert [call.args[0] for call in fact_calls] == ["summary one", "summary two"]
    assert all(call.kwargs["source_episode"] == f"episodes/{target}.md" for call in fact_calls)
    assert all(call.kwargs["source_session_id"] == "consolidation:daily" for call in fact_calls)
    assert all(call.kwargs["extractor"] is background_extractor for call in fact_calls)
    assert all(call.args == (engine.anima_dir,) for call in build_extractor.call_args_list)
    assert engine.write_calls[0][1] == "summary one\n\nsummary two"
    assert engine.record_calls[0]["input_profile"] == "compact"
    complete_logs = [call for call in info.call_args_list if "Phase A complete" in call.args[0]]
    assert len(complete_logs) == 1
    assert complete_logs[0].args[-2:] == (2, 1)


@pytest.mark.asyncio
async def test_daily_episode_summarises_next_chunk_while_facts_are_extracted() -> None:
    import asyncio

    target = date(2026, 10, 2)
    reference = datetime(2026, 10, 3, 2, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    config = AnimaWorksConfig(
        credentials={"anthropic": CredentialConfig(api_key="test")},
        consolidation=ConsolidationConfig(
            llm_model="anthropic/claude-sonnet-4-6",
            llm_credential="anthropic",
            episode_summary_backfill_days=1,
            episode_summary_max_input_bytes=4096,
        ),
    )
    events: list[str] = []
    second_summary_started = asyncio.Event()

    async def extract(text, **_kwargs):
        events.append(f"extract-start:{text}")
        if text == "summary one":
            await asyncio.wait_for(second_summary_started.wait(), timeout=5)
        events.append(f"extract-end:{text}")
        return SimpleNamespace(facts_extracted=1, facts_failed=0)

    async def complete(prompt, **_kwargs):
        if prompt == "activity chunk two":
            second_summary_started.set()
            events.append("summary-two")
            return "summary two"
        events.append("summary-one")
        return "summary one"

    engine = MagicMock()
    engine.anima_dir = Path("/nonexistent/test-anima")
    engine.previous_local_day_window.return_value = (target, None, None)
    engine.collect_pending_activity_chunks.return_value = (["activity chunk one", "activity chunk two"], False)
    engine.resolve_input_profile_for_date.side_effect = lambda _day, requested: requested
    engine.read_episode_for_date.return_value = ""
    engine._truncate_utf8.side_effect = lambda text, _limit: text
    engine._sanitize_llm_output.side_effect = lambda text: text
    engine.merge_timeline_parts.side_effect = lambda parts: "\n\n".join(parts)
    engine.write_consolidated_episode.return_value = Path(f"{target}.md")
    engine.extract_facts_from_text_outcome = AsyncMock(side_effect=extract)

    class FakeAnima(LifecycleMixin):
        pass

    owner = FakeAnima.__new__(FakeAnima)
    owner.name = "test-anima"
    owner.memory = MagicMock()
    owner.memory.read_model_config.return_value = ModelConfig(
        model="anthropic/claude-sonnet-4-6",
        credential="anthropic",
        resolved_mode="A",
    )

    with (
        patch("core.anima.lifecycle.now_local", return_value=reference),
        patch(
            "core.anima.lifecycle.load_prompt",
            side_effect=lambda _name, **kwargs: kwargs["activity_chunk"],
        ),
        patch("core.config.load_config", return_value=config),
        patch("core.llm.oneshot.one_shot_completion", new=AsyncMock(side_effect=complete)),
        patch("core.memory.facts.live.build_background_fact_extractor", return_value=object()),
    ):
        result = await LifecycleMixin._run_daily_episode_summaries(
            owner,
            engine,
            cfg=config,
            model=config.consolidation.llm_model,
            start_mono=0.0,
        )

    assert result.action == "completed"
    assert events.index("summary-two") < events.index("extract-end:summary one")
    assert events.index("extract-end:summary one") < events.index("extract-start:summary two")
