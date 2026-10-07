"""Regression tests for bounded, retryable daily episode summarization."""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import core.anima.lifecycle as lifecycle_module
from core.anima.lifecycle import (
    LifecycleMixin,
    _complete_episode_prompt,
    _episode_summary_model_configs,
    _split_episode_prompt_to_limit,
)
from core.config.models import AnimaWorksConfig, ConsolidationConfig, CredentialConfig
from core.memory.maintenance.consolidation import ConsolidationEngine
from core.schemas import ModelConfig


def test_large_activity_payload_is_truncated_at_utf8_boundary() -> None:
    clipped = ConsolidationEngine._truncate_utf8("日本語" * 100, 80)
    formatted = ConsolidationEngine._format_entry_full(
        SimpleNamespace(
            ts="2026-09-27T09:00:00+00:00",
            type="tool_result",
            tool="Bash",
            content="貼り付け出力" * 100,
            summary="",
            from_person="",
            to_person="",
            channel="",
            meta={},
        ),
        max_content_bytes=80,
    )

    assert len(clipped.encode("utf-8")) <= 80
    assert clipped.endswith("... (truncated)")
    assert "... (truncated)" in formatted


def test_episode_summary_candidates_use_configured_fallbacks() -> None:
    config = AnimaWorksConfig(
        credentials={
            "anthropic": CredentialConfig(api_key="primary"),
            "openai": CredentialConfig(api_key="fallback"),
        },
        consolidation=ConsolidationConfig(
            llm_model="anthropic/claude-sonnet-4-6",
            llm_credential="anthropic",
            llm_fallback_model="openai/gpt-4.1",
            llm_fallback_credential="openai",
        ),
    )
    base = ModelConfig(
        model="chat-model",
        fallback_models=["a:openai/gpt-4.1-mini"],
    )

    candidates = _episode_summary_model_configs(base, config.consolidation.llm_model, config)

    assert [(candidate.model, candidate.credential) for candidate in candidates] == [
        ("anthropic/claude-sonnet-4-6", "anthropic"),
        ("openai/gpt-4.1", "openai"),
    ]


def test_episode_summary_candidates_skip_cli_only_fallbacks() -> None:
    config = AnimaWorksConfig(
        credentials={
            "anthropic": CredentialConfig(api_key="primary"),
            "openai": CredentialConfig(api_key="fallback"),
        },
        consolidation=ConsolidationConfig(
            llm_model="anthropic/claude-sonnet-4-6",
            llm_credential="anthropic",
        ),
        helper_models={
            "episode_summary": {
                "fallbacks": [
                    {"model": "grok/grok-4.7"},
                    {"model": "cursor/composer-2"},
                    {"model": "gemini/gemini-3-pro"},
                    {"model": "openai/gpt-4.1"},
                ]
            }
        },
    )
    base = ModelConfig(
        model="chat-model",
        fallback_models=["x:grok/grok-4.7", "d:cursor/composer-2", "g:gemini/gemini-3-pro", "a:openai/gpt-4.1-mini"],
    )

    candidates = _episode_summary_model_configs(base, config.consolidation.llm_model, config)

    assert [candidate.model for candidate in candidates] == ["anthropic/claude-sonnet-4-6", "openai/gpt-4.1"]


def test_episode_prompt_is_split_to_exact_utf8_byte_limit() -> None:
    activity = ("出来事と詳細\n" * 1000).strip()
    prompts, error = _split_episode_prompt_to_limit(activity, lambda part: f"instructions\n{part}", 1024)

    assert not error
    assert len(prompts) > 1
    assert all(len(prompt.encode("utf-8")) <= 1024 for _, prompt in prompts)
    assert "".join(part for part, _ in prompts) == activity


@pytest.mark.asyncio
async def test_episode_summary_tries_configured_fallback_after_json_rpc_failure() -> None:
    configs = [ModelConfig(model="primary/model"), ModelConfig(model="fallback/model", credential="secondary")]
    completion = AsyncMock(side_effect=[RuntimeError("JSON-RPC error -32602: payload too large"), "summary output"])
    with patch("core.llm.oneshot.one_shot_completion", completion):
        result, reason = await _complete_episode_prompt("prompt", configs)

    assert result == "summary output"
    assert reason == ""
    assert [call.kwargs["model"] for call in completion.await_args_list] == ["primary/model", "fallback/model"]
    assert completion.await_args_list[1].kwargs["credential"] == "secondary"
    assert all(call.kwargs["allow_agent_sdk_fallback"] is False for call in completion.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("max_days", "deadline_in", "expected_offsets"),
    [
        # Yesterday plus the newest missing older day.
        (1, None, [0, 2]),
        # Older days go newest first.
        (3, None, [0, 2, 3]),
        # With the deadline already gone, no older day is started.
        (3, -1.0, [0]),
    ],
)
async def test_daily_episode_summary_backfills_bounded_older_days(max_days, deadline_in, expected_offsets) -> None:
    target = date(2026, 9, 27)
    reference = datetime(2026, 9, 28, 2, 0)
    config = AnimaWorksConfig(
        credentials={"anthropic": CredentialConfig(api_key="test")},
        consolidation=ConsolidationConfig(
            llm_model="anthropic/claude-sonnet-4-6",
            episode_summary_backfill_days=5,
            episode_summary_backfill_max_days_per_run=max_days,
            episode_summary_max_input_bytes=4096,
        ),
    )

    class FakeEngine:
        def __init__(self) -> None:
            self.written: list[date] = []
            self.recorded: list[date] = []

        @staticmethod
        def previous_local_day_window(_now=None):
            return target, None, None

        @staticmethod
        def local_day_window(day: date, _reference=None):
            return datetime.combine(day, datetime.min.time()), datetime.combine(
                day + timedelta(days=1), datetime.min.time()
            )

        @staticmethod
        def collect_activity_chunks(*, since, **_kwargs):
            day = since.date()
            return (
                [f"activity for {day}"]
                if day in {target, target - timedelta(days=2), target - timedelta(days=3)}
                else []
            )

        @staticmethod
        def collect_pending_activity_chunks(target_date, **_kwargs):
            day = target_date
            chunks = (
                [f"activity for {day}"]
                if day in {target, target - timedelta(days=2), target - timedelta(days=3)}
                else []
            )
            return chunks, False

        @staticmethod
        def unprocessed_activity_chunks(_day, chunks):
            return chunks

        @staticmethod
        def read_episode_for_date(_day):
            return ""

        _truncate_utf8 = staticmethod(ConsolidationEngine._truncate_utf8)

        @staticmethod
        def _sanitize_llm_output(text):
            return text

        @staticmethod
        def merge_timeline_parts(parts):
            return "\n\n".join(parts)

        def write_consolidated_episode(self, day, _content):
            self.written.append(day)
            return Path(f"{day}.md")

        def record_consolidated_chunks(
            self,
            day,
            _chunks,
            *,
            noop_cron_filtered=False,
            input_profile=None,
        ):
            self.recorded.append(day)

        extract_facts_from_text_outcome = AsyncMock(return_value=SimpleNamespace(facts_extracted=0, facts_failed=0))

    engine = FakeEngine()
    owner = SimpleNamespace(
        name="test-anima",
        memory=MagicMock(),
    )
    owner.memory.read_model_config.return_value = ModelConfig(model="chat-model")

    deadline_token = lifecycle_module._CONSOLIDATION_DEADLINE_AT.set(
        None if deadline_in is None else time.monotonic() + deadline_in
    )
    with (
        patch("core.anima.lifecycle.now_local", return_value=reference),
        patch(
            "core.anima.lifecycle.load_prompt",
            side_effect=lambda _name, **kw: f"{kw['time_range']}\n{kw['activity_chunk']}",
        ),
        patch("core.config.load_config", return_value=config),
        patch("core.llm.oneshot.one_shot_completion", new=AsyncMock(return_value="## 09:00 — Summary\n- recovered")),
    ):
        result = await LifecycleMixin._run_daily_episode_summaries(
            owner,
            engine,
            cfg=config,
            model=config.consolidation.llm_model,
            start_mono=0.0,
        )
    lifecycle_module._CONSOLIDATION_DEADLINE_AT.reset(deadline_token)

    assert engine.written == [target - timedelta(days=offset) for offset in expected_offsets]
    assert engine.recorded == engine.written
    assert result.action == "completed"


@pytest.mark.asyncio
async def test_daily_episode_failure_logs_date_and_reason() -> None:
    target = date(2026, 9, 27)
    reference = datetime(2026, 9, 28, 2, 0)
    config = AnimaWorksConfig(
        credentials={"anthropic": CredentialConfig(api_key="test")},
        consolidation=ConsolidationConfig(
            llm_model="anthropic/claude-sonnet-4-6",
            episode_summary_backfill_days=1,
            episode_summary_max_input_bytes=4096,
        ),
    )

    class FakeEngine:
        @staticmethod
        def previous_local_day_window(_now=None):
            return target, None, None

        @staticmethod
        def local_day_window(day, _reference=None):
            return datetime.combine(day, datetime.min.time()), datetime.combine(
                day + timedelta(days=1), datetime.min.time()
            )

        @staticmethod
        def collect_activity_chunks(**_kwargs):
            return ["activity"]

        @staticmethod
        def collect_pending_activity_chunks(target_date, **_kwargs):
            return ["activity"], False

        @staticmethod
        def unprocessed_activity_chunks(_day, chunks):
            return chunks

        @staticmethod
        def read_episode_for_date(_day):
            return ""

        _truncate_utf8 = staticmethod(ConsolidationEngine._truncate_utf8)

    owner = SimpleNamespace(name="test-anima", memory=MagicMock())
    owner.memory.read_model_config.return_value = ModelConfig(model="chat-model")
    with (
        patch("core.anima.lifecycle.now_local", return_value=reference),
        patch("core.anima.lifecycle.load_prompt", return_value="small prompt"),
        patch("core.config.load_config", return_value=config),
        patch("core.llm.oneshot.one_shot_completion", new=AsyncMock(return_value=None)),
        patch("core.anima.lifecycle.logger.warning") as warning,
    ):
        result = await LifecycleMixin._run_daily_episode_summaries(
            owner,
            FakeEngine(),
            cfg=config,
            model=config.consolidation.llm_model,
            start_mono=0.0,
        )

    assert result.action == "skipped"
    warning.assert_called_once()
    assert warning.call_args.args[0].startswith("[%s] Episode summary failed date=%s")
    assert target.isoformat() in warning.call_args.args
    assert "empty response" in warning.call_args.args[-1]
