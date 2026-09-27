"""E2E coverage for Sakura Neo4j memory recovery behavior."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_llm_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_custom_endpoint_entity_extraction_routes_through_openai_provider() -> None:
    """A bare model id with api_base should reach LiteLLM as openai/<model>."""
    from core.memory.facts.extractor import FactExtractor

    payload = {
        "entities": [
            {"name": "ExampleOrg", "entity_type": "Organization", "summary": "A company"},
        ]
    }
    cfg = MagicMock()
    cfg.consolidation.llm_model = "anthropic/claude-sonnet-4-6"
    cfg.credentials = {}

    extractor = FactExtractor(
        model="deepseek-v4-flash",
        max_retries=1,
        llm_extra={
            "api_base": "http://localhost:4000/v1",
            "api_key": "dummy",
            "timeout": 120,
        },
    )

    with (
        patch("core.memory._llm_utils.ensure_credentials_in_env"),
        patch("core.config.load_config", return_value=cfg),
        patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
    ):
        mock_acompletion.return_value = _make_llm_response(json.dumps(payload, ensure_ascii=False))
        entities = await extractor.extract_entities("ExampleOrgについて")

    assert [entity.name for entity in entities] == ["ExampleOrg"]
    kwargs = mock_acompletion.call_args.kwargs
    assert kwargs["model"] == "openai/deepseek-v4-flash"
    assert kwargs["api_base"] == "http://localhost:4000/v1"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_per_anima_fact_edge_ontology_drives_extraction_e2e(tmp_path) -> None:
    """status.json edge ontology should appear in prompts and canonicalize LLM facts."""
    from core.memory.facts.extractor import FactExtractor
    from core.memory.facts.ontology import ExtractedEntity

    anima_dir = tmp_path / "sakura"
    anima_dir.mkdir()
    (anima_dir / "status.json").write_text(
        json.dumps(
            {
                "fact_edge_types": [
                    {"name": "mentors", "description": "Mentorship relationship"},
                ]
            }
        ),
        encoding="utf-8",
    )

    cfg = MagicMock()
    cfg.memory.fact_edge_types = [
        {"name": "advises", "description": "Advice relationship"},
    ]
    extractor = FactExtractor(model="test-model", max_retries=1, anima_dir=anima_dir)
    captured_prompts: list[str] = []

    async def _mock_llm(_system: str, user: str) -> str:
        captured_prompts.append(user)
        return json.dumps(
            {
                "facts": [
                    {
                        "source_entity": "Alice",
                        "target_entity": "Bob",
                        "fact": "Alice mentors Bob",
                        "edge_type": "mentors",
                    }
                ]
            }
        )

    with (
        patch("core.config.models.load_config", return_value=cfg),
        patch.object(extractor, "_call_llm", side_effect=_mock_llm),
    ):
        facts = await extractor.extract_facts(
            "Alice mentors Bob",
            [
                ExtractedEntity(name="Alice", entity_type="Person"),
                ExtractedEntity(name="Bob", entity_type="Person"),
            ],
        )

    assert "`ADVISES`" in captured_prompts[0]
    assert "`MENTORS`" in captured_prompts[0]
    assert facts[0].edge_type == "MENTORS"
    assert facts[0].raw_edge_type is None
