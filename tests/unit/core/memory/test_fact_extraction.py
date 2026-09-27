"""Unit tests for fact ontology models and the extraction pipeline."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from core.memory.facts.observability import reset_warning_rate_limits
from core.memory.facts.ontology import (
    EntityExtractionResult,
    ExtractedEntity,
    ExtractedFact,
    FactExtractionResult,
)

# ── Helpers ────────────────────────────────────────────────────────────────


# ── TestExtractedModels ────────────────────────────────────────────────────


class TestExtractedModels:
    def test_entity_default_type(self):
        ent = ExtractedEntity(name="foo")
        assert ent.entity_type == "Concept"

    def test_entity_all_fields(self):
        ent = ExtractedEntity(name="Alice", entity_type="Person", summary="An engineer")
        assert ent.name == "Alice"
        assert ent.entity_type == "Person"
        assert ent.summary == "An engineer"

    def test_fact_valid_at_optional(self):
        fact = ExtractedFact(source_entity="A", target_entity="B", fact="knows")
        assert fact.valid_at is None

    def test_extraction_result_empty(self):
        result = EntityExtractionResult()
        assert result.entities == []

    def test_fact_extraction_result_empty(self):
        result = FactExtractionResult()
        assert result.facts == []


# ── TestFactExtractorInit ──────────────────────────────────────────────────


class TestFactExtractorInit:
    def test_default_locale(self):
        from core.memory.facts.extractor import FactExtractor

        ext = FactExtractor(model="m")
        assert ext._locale == "ja"

    def test_custom_locale(self):
        from core.memory.facts.extractor import FactExtractor

        ext = FactExtractor(model="m", locale="en")
        assert ext._locale == "en"

    def test_model_stored(self):
        from core.memory.facts.extractor import FactExtractor

        ext = FactExtractor(model="claude-sonnet-4-6")
        assert ext._model == "claude-sonnet-4-6"


# ── TestFactExtractorExtractEntities ───────────────────────────────────────


class TestFactExtractorExtractEntities:
    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    async def test_extract_entities_success(self, mock_acompletion):
        from core.memory.facts.extractor import FactExtractor

        payload = {
            "entities": [
                {"name": "田中", "entity_type": "Person", "summary": "A person"},
                {"name": "東京", "entity_type": "Place", "summary": "A city"},
            ]
        }
        mock_acompletion.return_value = json.dumps(payload, ensure_ascii=False)

        ext = FactExtractor(model="test-model", max_retries=1)
        entities = await ext.extract_entities("田中さんは東京に住んでいる")

        assert len(entities) == 2
        assert entities[0].name == "田中"
        assert entities[0].entity_type == "Person"
        assert entities[1].name == "東京"
        assert entities[1].entity_type == "Place"

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    async def test_extract_entities_forwards_custom_endpoint_settings(self, mock_acompletion):
        from core.memory.facts.extractor import FactExtractor

        payload = {
            "entities": [
                {"name": "ExampleOrg", "entity_type": "Organization", "summary": "A company"},
            ]
        }
        mock_acompletion.return_value = json.dumps(payload, ensure_ascii=False)

        ext = FactExtractor(
            model="deepseek-v4-flash",
            max_retries=1,
            timeout=120,
            llm_extra={
                "api_base": "http://localhost:4000/v1",
                "api_key": "dummy",
                "timeout": 120,
            },
        )
        entities = await ext.extract_entities("ExampleOrgについて")

        assert len(entities) == 1
        kwargs = mock_acompletion.call_args.kwargs
        assert kwargs["model"] == "deepseek-v4-flash"
        assert kwargs["llm_extra"]["api_base"] == "http://localhost:4000/v1"
        assert kwargs["llm_extra"]["api_key"] == "dummy"
        assert kwargs["timeout"] == 120
        assert kwargs["temperature"] == 0.0
        assert kwargs["structured_output"] is True

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    async def test_extract_entities_empty_content(self, mock_acompletion):
        from core.memory.facts.extractor import FactExtractor

        mock_acompletion.return_value = ""

        ext = FactExtractor(model="test-model", max_retries=1)
        entities = await ext.extract_entities("テスト")
        assert entities == []

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    async def test_extract_entities_llm_failure(self, mock_acompletion):
        from core.memory.facts.extractor import FactExtractor

        mock_acompletion.side_effect = RuntimeError("API down")

        ext = FactExtractor(model="test-model", max_retries=1)
        entities = await ext.extract_entities("何かテキスト")
        assert entities == []

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    async def test_extract_entities_invalid_json(self, mock_acompletion, caplog):
        from core.memory.facts.extractor import FactExtractor

        reset_warning_rate_limits()
        mock_acompletion.return_value = "NOT VALID JSON {{{"

        ext = FactExtractor(model="test-model", max_retries=1)
        with caplog.at_level("WARNING", logger="core.memory.facts.extractor"):
            entities = await ext.extract_entities("テスト")

        assert entities == []
        assert ext.last_failure_stage == "entity_parse"
        assert "Failed to parse entity extraction LLM JSON response" in caplog.text

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    async def test_extract_entities_filters_empty_names(self, mock_acompletion):
        from core.memory.facts.extractor import FactExtractor

        payload = {
            "entities": [
                {"name": "", "entity_type": "Person", "summary": "empty"},
                {"name": "  ", "entity_type": "Person", "summary": "whitespace"},
                {"name": "Valid", "entity_type": "Concept", "summary": "ok"},
            ]
        }
        mock_acompletion.return_value = json.dumps(payload)

        ext = FactExtractor(model="test-model", max_retries=1)
        entities = await ext.extract_entities("テスト")

        assert len(entities) == 1
        assert entities[0].name == "Valid"

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    @patch("core.memory.facts.extractor.asyncio.sleep", new_callable=AsyncMock)
    async def test_call_llm_retries_none_until_exhausted(self, mock_sleep, mock_one_shot):
        from core.memory.facts.extractor import FactExtractor

        mock_one_shot.return_value = None
        ext = FactExtractor(model="test-model", max_retries=3)

        with pytest.raises(RuntimeError, match="LLM returned no content"):
            await ext._call_llm("system", "user")

        assert mock_one_shot.call_count == 3
        assert mock_sleep.await_count == 2

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    @patch("core.memory.facts.extractor.asyncio.sleep", new_callable=AsyncMock)
    async def test_call_llm_succeeds_after_none(self, mock_sleep, mock_one_shot):
        from core.memory.facts.extractor import FactExtractor

        mock_one_shot.side_effect = [None, "recovered response"]
        ext = FactExtractor(model="test-model", max_retries=3)

        assert await ext._call_llm("system", "user") == "recovered response"
        assert mock_one_shot.call_count == 2
        mock_sleep.assert_awaited_once_with(0.5)


# ── TestParseJsonResponse ──────────────────────────────────────────────
# Verifies the LLM JSON parser handles the three response forms:
# (a) raw JSON, (b) ```json fenced, (c) fence with explanation text around it.


class TestParseJsonResponse:
    _PAYLOAD = json.dumps({"entities": [{"name": "田中", "entity_type": "Person"}]}, ensure_ascii=False)

    def _parse(self, text: str) -> EntityExtractionResult:
        from core.memory.facts.extractor import FactExtractor

        ext = FactExtractor(model="test-model")
        result = ext._parse_json_response(text, EntityExtractionResult, stage="entity")
        assert isinstance(result, EntityExtractionResult)
        return result

    def test_parses_raw_json(self):
        result = self._parse(self._PAYLOAD)
        assert len(result.entities) == 1
        assert result.entities[0].name == "田中"

    def test_parses_code_fenced_json(self):
        result = self._parse(f"```json\n{self._PAYLOAD}\n```")
        assert len(result.entities) == 1
        assert result.entities[0].name == "田中"

    def test_parses_fence_with_surrounding_explanation(self):
        text = f"以下が抽出結果です。\n```json\n{self._PAYLOAD}\n```\n（以上）"
        result = self._parse(text)
        assert len(result.entities) == 1
        assert result.entities[0].name == "田中"

    def test_parses_unlabeled_fence(self):
        result = self._parse(f"```\n{self._PAYLOAD}\n```")
        assert len(result.entities) == 1


# ── TestFactExtractorExtractFacts ──────────────────────────────────────────


class TestFactExtractorExtractFacts:
    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    async def test_extract_facts_success(self, mock_acompletion):
        from core.memory.facts.extractor import FactExtractor

        payload = {
            "facts": [
                {
                    "source_entity": "田中",
                    "target_entity": "東京",
                    "fact": "田中は東京に住んでいる",
                    "valid_at": None,
                }
            ]
        }
        mock_acompletion.return_value = json.dumps(payload, ensure_ascii=False)

        ext = FactExtractor(model="test-model", max_retries=1)
        entities = [
            ExtractedEntity(name="田中", entity_type="Person", summary="person"),
            ExtractedEntity(name="東京", entity_type="Place", summary="city"),
        ]
        facts = await ext.extract_facts("田中さんは東京に住んでいる", entities)

        assert len(facts) == 1
        assert facts[0].source_entity == "田中"
        assert facts[0].target_entity == "東京"
        assert facts[0].fact == "田中は東京に住んでいる"

    @pytest.mark.asyncio
    async def test_extract_facts_no_entities(self):
        from core.memory.facts.extractor import FactExtractor

        ext = FactExtractor(model="test-model")
        facts = await ext.extract_facts("テスト", [])
        assert facts == []

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    async def test_extract_facts_filters_invalid_refs(self, mock_acompletion):
        from core.memory.facts.extractor import FactExtractor

        payload = {
            "facts": [
                {
                    "source_entity": "田中",
                    "target_entity": "大阪",
                    "fact": "visited",
                    "valid_at": None,
                },
                {
                    "source_entity": "田中",
                    "target_entity": "東京",
                    "fact": "lives in",
                    "valid_at": None,
                },
            ]
        }
        mock_acompletion.return_value = json.dumps(payload, ensure_ascii=False)

        ext = FactExtractor(model="test-model", max_retries=1)
        entities = [
            ExtractedEntity(name="田中", entity_type="Person", summary="person"),
            ExtractedEntity(name="東京", entity_type="Place", summary="city"),
        ]
        facts = await ext.extract_facts("テスト", entities)

        assert len(facts) == 1
        assert facts[0].target_entity == "東京"

    @pytest.mark.asyncio
    @patch("core.memory._llm_utils.one_shot_completion", new_callable=AsyncMock)
    async def test_extract_facts_llm_failure(self, mock_acompletion):
        from core.memory.facts.extractor import FactExtractor

        mock_acompletion.side_effect = RuntimeError("API down")

        ext = FactExtractor(model="test-model", max_retries=1)
        entities = [ExtractedEntity(name="X", entity_type="Concept", summary="x")]
        facts = await ext.extract_facts("テスト", entities)
        assert facts == []
