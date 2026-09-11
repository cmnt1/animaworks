"""Unit tests for Entity Resolution (resolver + minhash)."""

from __future__ import annotations

from unittest.mock import AsyncMock

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
    async def test_resolve_always_creates_new(self, mock_driver, entity):
        # The LLM judgment step was removed: entities are always new.
        resolver = EntityResolver(mock_driver, "test_group", model="test-model")
        result = await resolver.resolve(entity)
        assert result.is_new is True
        assert result.merged_with_uuid is None
        assert result.name == "田中"

    @pytest.mark.asyncio
    async def test_resolve_session_cache_hit(self, mock_driver, entity):
        resolver = EntityResolver(mock_driver, "test_group", model="test-model")

        r1 = await resolver.resolve(entity)
        r2 = await resolver.resolve(entity)
        assert r2 is r1

        # Resolution is a pure in-memory compute; no driver interaction.
        mock_driver.execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_ignores_candidates(self, mock_driver, entity):
        # Even with candidate matches, resolution still creates a new entity.
        mock_driver.execute_query = AsyncMock(
            return_value=[
                {
                    "uuid": "c1",
                    "name": "田中太郎",
                    "summary": "A person named Tanaka Taro",
                    "entity_type": "Person",
                },
            ]
        )
        resolver = EntityResolver(mock_driver, "test_group", model="test-model", jaccard_threshold=0.0)
        result = await resolver.resolve(entity)
        assert result.is_new is True
        assert mock_driver.execute_query.call_count == 0


# ── TestEntityResolverFilters ───────────────────────────────


class TestEntityResolverFilters:
    """The vector + Jaccard candidate filters are retained as helpers."""

    def _candidate(self, uuid: str, name: str, summary: str, score: float = 0.0) -> dict:
        return {"uuid": uuid, "name": name, "summary": summary, "entity_type": "Person", "score": score}

    def test_filter_by_jaccard_keeps_similar_name(self):
        resolver = EntityResolver(AsyncMock(), "group")
        entity = ExtractedEntity(name="Tanaka", entity_type="Person", summary="A developer")
        candidates = [self._candidate("c1", "Tanaka", "A developer")]
        filtered = resolver._filter_by_jaccard(entity, candidates)
        assert len(filtered) == 1

    def test_filter_by_jaccard_drops_unrelated(self):
        resolver = EntityResolver(AsyncMock(), "group")
        entity = ExtractedEntity(name="Tanaka", entity_type="Person", summary="A developer")
        candidates = [self._candidate("c1", "Quantum physics", "Nuclear reactor engineering")]
        filtered = resolver._filter_by_jaccard(entity, candidates)
        assert filtered == []

    def test_filter_by_jaccard_keeps_high_scoring_vector_match(self):
        resolver = EntityResolver(AsyncMock(), "group")
        entity = ExtractedEntity(name="さくら", entity_type="Person", summary="A person")
        candidates = [self._candidate("c1", "sakura", "A person", score=0.95)]
        filtered = resolver._filter_by_jaccard(entity, candidates)
        assert len(filtered) == 1

    @pytest.mark.asyncio
    async def test_vector_candidates_by_name(self):
        driver = AsyncMock()
        driver.execute_query = AsyncMock(return_value=[])
        resolver = EntityResolver(driver, "group")
        entity = ExtractedEntity(name="Tanaka", entity_type="Person", summary="A developer")
        await resolver._find_vector_candidates(entity, name_embedding=None)
        args = driver.execute_query.call_args
        assert args[0][1]["name_pattern"] == "(?i).*Tanaka.*"
