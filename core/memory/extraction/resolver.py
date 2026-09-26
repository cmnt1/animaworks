# Copyright 2026 AnimaWorks
# Licensed under the Apache License, Version 2.0
"""Entity Resolution: Vector + MinHash candidate filtering, new-entity default."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory.graph.driver import Neo4jDriver

from core.memory.ontology.default import ExtractedEntity

logger = logging.getLogger(__name__)


# ── Data classes ───────────────────────────────────────────


@dataclass
class ResolvedEntity:
    """Result of entity resolution."""

    uuid: str
    name: str
    summary: str
    entity_type: str
    is_new: bool
    merged_with_uuid: str | None = None


# ── EntityResolver ─────────────────────────────────────────


class EntityResolver:
    """3-step entity resolver: Vector -> MinHash -> LLM."""

    def __init__(
        self,
        driver: Neo4jDriver,
        group_id: str,
        *,
        model: str = "claude-sonnet-4-6",
        locale: str = "ja",
        vector_top_k: int = 10,
        vector_min_score: float = 0.5,
        jaccard_threshold: float = 0.4,
        llm_extra: dict[str, object] | None = None,
        credential: str = "",
    ) -> None:
        self._driver = driver
        self._group_id = group_id
        self._model = model
        self._locale = locale
        self._vector_top_k = vector_top_k
        self._vector_min_score = vector_min_score
        self._jaccard_threshold = jaccard_threshold
        self._llm_extra = llm_extra or {}
        self._credential = credential
        self._session_cache: dict[str, ResolvedEntity] = {}

    def clear_cache(self) -> None:
        """Clear the session-level resolution cache."""
        self._session_cache.clear()

    async def resolve(
        self,
        entity: ExtractedEntity,
        *,
        name_embedding: list[float] | None = None,
    ) -> ResolvedEntity:
        """Resolve an entity against existing graph nodes.

        Args:
            entity: Newly extracted entity to resolve.
            name_embedding: Pre-computed embedding for vector search.

        Returns:
            ResolvedEntity with is_new=True for new entities,
            is_new=False with merged_with_uuid for duplicates.
        """
        cache_key = f"{entity.name.lower().strip()}::{entity.entity_type}"
        if cache_key in self._session_cache:
            logger.debug("Session cache hit: %s", cache_key)
            return self._session_cache[cache_key]

        from uuid import uuid4

        new_uuid = str(uuid4())
        result = ResolvedEntity(
            uuid=new_uuid,
            name=entity.name,
            summary=entity.summary,
            entity_type=entity.entity_type,
            is_new=True,
        )
        self._session_cache[cache_key] = result
        return result

    # ── Step 1: Vector search ──────────────────────────────

    async def _find_vector_candidates(
        self,
        entity: ExtractedEntity,
        name_embedding: list[float] | None,
    ) -> list[dict]:
        """Find candidate entities using vector similarity search."""
        if not name_embedding:
            from core.memory.graph.queries import FIND_ENTITIES_BY_NAME

            results = await self._driver.execute_query(
                FIND_ENTITIES_BY_NAME,
                {
                    "group_id": self._group_id,
                    "name_pattern": f"(?i).*{entity.name}.*",
                    "limit": self._vector_top_k,
                },
            )
            return results

        from core.memory.graph.queries import FIND_ENTITIES_BY_VECTOR

        results = await self._driver.execute_query(
            FIND_ENTITIES_BY_VECTOR,
            {
                "group_id": self._group_id,
                "entity_type": entity.entity_type,
                "embedding": name_embedding,
                "top_k": self._vector_top_k,
                "min_score": self._vector_min_score,
            },
        )
        return results

    # ── Step 2: MinHash filter ─────────────────────────────

    def _filter_by_jaccard(self, entity: ExtractedEntity, candidates: list[dict]) -> list[dict]:
        """Filter candidates by MinHash Jaccard similarity.

        High-confidence vector matches (score >= 0.70) bypass the Jaccard
        threshold so that cross-script duplicates (e.g. さくら vs sakura)
        are not lost when ranking candidate duplicates.  Resolution itself
        always creates a new entity; merging is handled weekly by the LLM.
        """
        from core.memory.extraction.minhash import text_similarity

        _VECTOR_BYPASS_SCORE = 0.70

        entity_text = f"{entity.name} {entity.summary}"
        entity_name_lower = entity.name.lower().strip()
        filtered = []
        for c in candidates:
            vector_score = float(c.get("score", 0.0))
            cand_name_lower = c.get("name", "").lower().strip()

            if cand_name_lower == entity_name_lower or vector_score >= _VECTOR_BYPASS_SCORE:
                c["jaccard_score"] = 1.0 if cand_name_lower == entity_name_lower else vector_score
                filtered.append(c)
                continue

            cand_text = f"{c.get('name', '')} {c.get('summary', '')}"
            sim = text_similarity(entity_text, cand_text)
            if sim >= self._jaccard_threshold:
                c["jaccard_score"] = sim
                filtered.append(c)

        filtered.sort(key=lambda x: x.get("jaccard_score", 0), reverse=True)
        return filtered
