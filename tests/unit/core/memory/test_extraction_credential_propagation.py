"""Credential propagation from extraction classes to LLM kwargs (#240 M-2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fact_extractor_passes_credential():
    from core.memory.facts.extractor import FactExtractor

    ext = FactExtractor(
        model="qwen-model",
        credential="vllm-lb",
        max_retries=1,
    )

    with patch(
        "core.memory._llm_utils.one_shot_completion",
        new_callable=AsyncMock,
        return_value='{"entities": []}',
    ) as mock_one_shot:
        await ext._call_llm("system", "user")

    assert mock_one_shot.call_args.kwargs["credential"] == "vllm-lb"
    assert mock_one_shot.call_args.kwargs["model"] == "qwen-model"
    assert mock_one_shot.call_args.kwargs["llm_extra"] == {}
