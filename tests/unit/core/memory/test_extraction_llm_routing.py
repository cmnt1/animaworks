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
