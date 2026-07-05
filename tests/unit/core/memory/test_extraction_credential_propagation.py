"""Credential propagation from extraction classes to LLM kwargs (#240 M-2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _llm_response(text: str):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    return resp


def _capture_kwargs_resolver(captured: dict):
    def fake(model, llm_extra=None, *, credential=""):
        captured["model"] = model
        captured["credential"] = credential
        return {"model": f"openai/{model}", "api_base": "http://localhost:4000/v1"}

    return fake


@pytest.mark.unit
@pytest.mark.asyncio
async def test_entity_resolver_passes_credential():
    from core.memory.extraction.extractor import ExtractedEntity
    from core.memory.extraction.resolver import EntityResolver

    captured: dict = {}
    resolver = EntityResolver(
        AsyncMock(),
        "alice",
        model="qwen-model",
        credential="vllm-lb",
    )
    entity = ExtractedEntity(name="Tokyo", entity_type="Place", summary="capital")

    with (
        patch(
            "core.memory._llm_utils.get_memory_llm_kwargs_for_model",
            side_effect=_capture_kwargs_resolver(captured),
        ),
        patch("litellm.acompletion", new_callable=AsyncMock, return_value=_llm_response('{"duplicate": false}')),
    ):
        await resolver._llm_judge(entity, [{"uuid": "u1", "name": "Tokio", "summary": "x"}])

    assert captured["credential"] == "vllm-lb"
    assert captured["model"] == "qwen-model"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_edge_invalidator_passes_credential():
    from core.memory.extraction.invalidator import EdgeInvalidator

    captured: dict = {}
    invalidator = EdgeInvalidator(
        AsyncMock(),
        "alice",
        model="qwen-model",
        credential="vllm-lb",
    )

    with (
        patch(
            "core.memory._llm_utils.get_memory_llm_kwargs_for_model",
            side_effect=_capture_kwargs_resolver(captured),
        ),
        patch("litellm.acompletion", new_callable=AsyncMock, return_value=_llm_response("[]")),
    ):
        await invalidator._judge_contradictions(
            "new fact",
            [{"uuid": "f1", "fact_text": "old fact", "valid_at": "2026-01-01"}],
        )

    assert captured["credential"] == "vllm-lb"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_community_detector_passes_credential():
    from core.memory.graph.community import CommunityDetector

    captured: dict = {}
    detector = CommunityDetector(
        AsyncMock(),
        "alice",
        model="qwen-model",
        credential="vllm-lb",
    )

    with (
        patch(
            "core.memory._llm_utils.get_memory_llm_kwargs_for_model",
            side_effect=_capture_kwargs_resolver(captured),
        ),
        patch(
            "litellm.acompletion",
            new_callable=AsyncMock,
            return_value=_llm_response("NAME: devs\nSUMMARY: dev topics"),
        ) as mock_llm,
    ):
        await detector._summarize_community(["a", "b", "c"], ["s1", "s2", "s3"])

    assert captured["credential"] == "vllm-lb"
    # resolved kwargs (api_base) must reach the actual LLM call
    assert mock_llm.call_args.kwargs.get("api_base") == "http://localhost:4000/v1"
    assert mock_llm.call_args.kwargs.get("model") == "openai/qwen-model"
