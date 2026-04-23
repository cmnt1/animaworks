"""Unit tests for Entity Resolution (resolver + minhash)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.memory.extraction.minhash import (
    jaccard_similarity,
    minhash_signature,
    text_similarity,
)
from core.memory.extraction.resolver import EntityResolver, ResolvedEntity
from core.memory.ontology.default import ExtractedEntity

# ── TestMinHash ─────────────────────────────────────────────


class TestMinHash:
    def test_minhash_signature_returns_object(self):
        sig = minhash_signature("hello")
        assert sig is not None

    def test_minhash_identical_text_high_similarity(self):
        sig_a = minhash_signature("the quick brown fox jumps over the lazy dog")
        sig_b = minhash_signature("the quick brown fox jumps over the lazy dog")
        sim = jaccard_similarity(sig_a, sig_b)
        assert sim == pytest.approx(1.0)

    def test_minhash_different_text_low_similarity(self):
        sig_a = minhash_signature("quantum physics nuclear reactor engineering")
        sig_b = minhash_signature("chocolate cake recipe baking dessert")
        sim = jaccard_similarity(sig_a, sig_b)
        assert sim < 0.5

    def test_text_similarity_convenience(self):
        sim = text_similarity("ab cd ef", "ab cd ef")
        assert sim > 0.9

    def test_empty_text(self):
        sig = minhash_signature("")
        assert sig is not None


# ── TestResolvedEntity ──────────────────────────────────────


class TestResolvedEntity:
    def test_new_entity(self):
        r = ResolvedEntity(
            uuid="u1",
            name="Taro",
            summary="A person",
            entity_type="Person",
            is_new=True,
        )
        assert r.is_new is True
        assert r.merged_with_uuid is None

    def test_merged_entity(self):
        r = ResolvedEntity(
            uuid="u2",
            name="Taro",
            summary="merged",
            entity_type="Person",
            is_new=False,
            merged_with_uuid="abc",
        )
        assert r.is_new is False
        assert r.merged_with_uuid == "abc"


# ── TestEntityResolverInit ──────────────────────────────────


class TestEntityResolverInit:
    def test_creates_with_driver(self):
        driver = AsyncMock()
        resolver = EntityResolver(driver, "group")
        assert resolver is not None

    def test_session_cache_initially_empty(self):
        driver = AsyncMock()
        resolver = EntityResolver(driver, "group")
        assert resolver._session_cache == {}


# ── TestEntityResolverResolve ───────────────────────────────


class TestEntityResolverResolve:
    @pytest.fixture()
    def mock_driver(self):
        d = AsyncMock()
        d.execute_query = AsyncMock(return_value=[])
        return d

    @pytest.fixture()
    def entity(self):
        return ExtractedEntity(name="田中", entity_type="Person", summary="A person named Tanaka")

    @pytest.mark.asyncio
    async def test_resolve_no_candidates_creates_new(self, mock_driver, entity):
        resolver = EntityResolver(mock_driver, "test_group", model="test-model")
        result = await resolver.resolve(entity)
        assert result.is_new is True
        assert result.name == "田中"

    @pytest.mark.asyncio
    async def test_resolve_session_cache_hit(self, mock_driver, entity):
        resolver = EntityResolver(mock_driver, "test_group", model="test-model")

        r1 = await resolver.resolve(entity)
        mock_driver.execute_query.reset_mock()

        r2 = await resolver.resolve(entity)
        assert r2 is r1
        mock_driver.execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_cache_cleared(self, mock_driver, entity):
        resolver = EntityResolver(mock_driver, "test_group", model="test-model")

        await resolver.resolve(entity)
        mock_driver.execute_query.reset_mock()

        resolver.clear_cache()
        await resolver.resolve(entity)
        mock_driver.execute_query.assert_called()

    @pytest.mark.asyncio
    async def test_resolve_jaccard_filters_all(self, mock_driver, entity):
        mock_driver.execute_query = AsyncMock(
            return_value=[
                {
                    "uuid": "c1",
                    "name": "completely unrelated xyz",
                    "summary": "nothing similar",
                    "entity_type": "Person",
                },
            ]
        )
        resolver = EntityResolver(mock_driver, "test_group", model="test-model")
        result = await resolver.resolve(entity)
        assert result.is_new is True

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_resolve_llm_says_duplicate(self, mock_acompletion, mock_driver, entity):
        mock_driver.execute_query = AsyncMock(
            return_value=[
                {
                    "uuid": "existing-uuid",
                    "name": "田中太郎",
                    "summary": "A person named Tanaka Taro",
                    "entity_type": "Person",
                },
            ]
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"duplicate_of_uuid": "existing-uuid", "merged_summary": "merged"}'
        mock_acompletion.return_value = mock_response

        resolver = EntityResolver(mock_driver, "test_group", model="test-model", jaccard_threshold=0.0)
        result = await resolver.resolve(entity)

        assert result.is_new is False
        assert result.merged_with_uuid == "existing-uuid"

    @pytest.mark.asyncio
    @patch("litellm.acompletion")
    async def test_resolve_llm_says_not_duplicate(self, mock_acompletion, mock_driver, entity):
        mock_driver.execute_query = AsyncMock(
            return_value=[
                {"uuid": "c1", "name": "田中花子", "summary": "A different Tanaka", "entity_type": "Person"},
            ]
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"duplicate_of_uuid": null}'
        mock_acompletion.return_value = mock_response

        resolver = EntityResolver(mock_driver, "test_group", model="test-model", jaccard_threshold=0.0)
        result = await resolver.resolve(entity)

        assert result.is_new is True

    @pytest.mark.asyncio
    @patch("litellm.acompletion", side_effect=RuntimeError("API error"))
    async def test_resolve_llm_failure_creates_new(self, _mock, mock_driver, entity):
        mock_driver.execute_query = AsyncMock(
            return_value=[
                {"uuid": "c1", "name": "田中太郎", "summary": "Tanaka person", "entity_type": "Person"},
            ]
        )
        resolver = EntityResolver(mock_driver, "test_group", model="test-model", jaccard_threshold=0.0)
        result = await resolver.resolve(entity)

        assert result.is_new is True

    @pytest.mark.asyncio
    async def test_resolve_entity_type_filtered(self, mock_driver):
        mock_driver.execute_query = AsyncMock(return_value=[])

        entity = ExtractedEntity(name="Tokyo", entity_type="Place", summary="Capital city")
        embedding = [0.1] * 384

        resolver = EntityResolver(mock_driver, "test_group", model="test-model")
        result = await resolver.resolve(entity, name_embedding=embedding)

        assert result.is_new is True
        call_args = mock_driver.execute_query.call_args
        params = call_args[0][1]
        assert params["entity_type"] == "Place"


# ── TestParseDedupeResponse ─────────────────────────────────


class TestParseDedupeResponse:
    def test_parse_valid_json(self):
        result = EntityResolver._parse_dedupe_response('{"duplicate_of_uuid": "abc", "merged_summary": "x"}')
        assert result == {"duplicate_of_uuid": "abc", "merged_summary": "x"}

    def test_parse_json_in_code_fence(self):
        text = '```json\n{"duplicate_of_uuid": "abc", "merged_summary": "x"}\n```'
        result = EntityResolver._parse_dedupe_response(text)
        assert result is not None
        assert result["duplicate_of_uuid"] == "abc"

    def test_parse_null_duplicate(self):
        result = EntityResolver._parse_dedupe_response('{"duplicate_of_uuid": null}')
        assert result is not None
        assert result["duplicate_of_uuid"] is None

    def test_parse_invalid_json(self):
        result = EntityResolver._parse_dedupe_response("not json at all {{{")
        assert result is None

    def test_parse_empty(self):
        result = EntityResolver._parse_dedupe_response("")
        assert result is None
