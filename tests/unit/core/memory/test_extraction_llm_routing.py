# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for memory-extraction LLM routing.

The fact/entity extraction pipeline (extractor / resolver / invalidator)
calls LiteLLM directly.  ``codex/*`` models have no LiteLLM provider, so
they must be routed through the Codex CLI one-shot transport instead of
failing with BadRequestError on every daily consolidation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.memory.extraction.extractor import FactExtractor
from core.memory.extraction.invalidator import EdgeInvalidator
from core.memory.extraction.resolver import EntityResolver


class TestExtractorCodexRouting:
    @pytest.mark.asyncio
    async def test_codex_model_uses_one_shot_completion(self) -> None:
        extractor = FactExtractor("codex/gpt-5.4-mini", credential="openai")
        with (
            patch(
                "core.memory._llm_utils.one_shot_completion",
                new=AsyncMock(return_value='{"entities": []}'),
            ) as mock_one_shot,
            patch("litellm.acompletion", new=AsyncMock()) as mock_acompletion,
        ):
            text = await extractor._call_llm("system", "user")
        assert text == '{"entities": []}'
        mock_one_shot.assert_awaited_once()
        assert mock_one_shot.await_args.kwargs["model"] == "codex/gpt-5.4-mini"
        assert mock_one_shot.await_args.kwargs["credential"] == "openai"
        mock_acompletion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_codex_one_shot_failure_raises(self) -> None:
        extractor = FactExtractor("codex/gpt-5.4-mini")
        with (
            patch(
                "core.memory._llm_utils.one_shot_completion",
                new=AsyncMock(return_value=None),
            ),
            pytest.raises(RuntimeError, match="Codex one-shot"),
        ):
            await extractor._call_llm("system", "user")

    @pytest.mark.asyncio
    async def test_non_codex_model_still_uses_litellm(self) -> None:
        extractor = FactExtractor("anthropic/claude-haiku-4-5")
        response = MagicMock()
        response.choices[0].message.content = "ok"
        with (
            patch("core.memory._llm_utils.one_shot_completion", new=AsyncMock()) as mock_one_shot,
            patch("litellm.acompletion", new=AsyncMock(return_value=response)) as mock_acompletion,
            patch(
                "core.memory._llm_utils.get_memory_llm_kwargs_for_model",
                return_value={"model": "anthropic/claude-haiku-4-5"},
            ),
        ):
            text = await extractor._call_llm("system", "user")
        assert text == "ok"
        mock_acompletion.assert_awaited_once()
        mock_one_shot.assert_not_awaited()


def _make_entity() -> MagicMock:
    entity = MagicMock()
    entity.name = "Alice"
    entity.entity_type = "person"
    entity.summary = "test"
    return entity


def _make_resolver(model: str = "codex/gpt-5.4-mini") -> EntityResolver:
    resolver = EntityResolver.__new__(EntityResolver)
    resolver._model = model
    resolver._llm_extra = {}
    resolver._credential = ""
    resolver._locale = "ja"
    return resolver


def _make_invalidator(model: str = "codex/gpt-5.4-mini") -> EdgeInvalidator:
    invalidator = EdgeInvalidator.__new__(EdgeInvalidator)
    invalidator._model = model
    invalidator._llm_extra = {}
    invalidator._credential = ""
    invalidator._locale = "ja"
    return invalidator


class TestResolverCodexRouting:
    @pytest.mark.asyncio
    async def test_codex_model_uses_one_shot_completion(self) -> None:
        resolver = _make_resolver()
        with (
            patch(
                "core.memory._llm_utils.one_shot_completion",
                new=AsyncMock(return_value='{"duplicate_uuid": null}'),
            ) as mock_one_shot,
            patch("litellm.acompletion", new=AsyncMock()) as mock_acompletion,
        ):
            result = await resolver._llm_judge(_make_entity(), [{"uuid": "u1", "name": "Alice"}])
        assert result == {"duplicate_uuid": None}
        mock_one_shot.assert_awaited_once()
        mock_acompletion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_codex_one_shot_none_returns_none(self) -> None:
        resolver = _make_resolver()
        with patch(
            "core.memory._llm_utils.one_shot_completion",
            new=AsyncMock(return_value=None),
        ):
            result = await resolver._llm_judge(_make_entity(), [{"uuid": "u1"}])
        assert result is None


class TestInvalidatorCodexRouting:
    @pytest.mark.asyncio
    async def test_codex_model_uses_one_shot_completion(self) -> None:
        invalidator = _make_invalidator()
        with (
            patch(
                "core.memory._llm_utils.one_shot_completion",
                new=AsyncMock(return_value='{"contradicted_uuids": ["u1"]}'),
            ) as mock_one_shot,
            patch("litellm.acompletion", new=AsyncMock()) as mock_acompletion,
        ):
            result = await invalidator._judge_contradictions("new fact", [{"uuid": "u1", "fact": "old fact"}])
        assert result == ["u1"]
        mock_one_shot.assert_awaited_once()
        mock_acompletion.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_codex_one_shot_none_returns_empty(self) -> None:
        invalidator = _make_invalidator()
        with patch(
            "core.memory._llm_utils.one_shot_completion",
            new=AsyncMock(return_value=None),
        ):
            result = await invalidator._judge_contradictions("new fact", [{"uuid": "u1"}])
        assert result == []
