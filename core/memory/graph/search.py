from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Hybrid search — BM25 + Vector + BFS + Cross-encoder reranking."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory.graph.driver import Neo4jDriver

logger = logging.getLogger(__name__)


# ── HybridSearch ──────────────────────────────────────────────────────────


class HybridSearch:
    """4-source hybrid search with RRF merge and cross-encoder reranking."""

    def __init__(
        self,
        driver: Neo4jDriver,
        group_id: str,
        *,
        cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
        max_depth: int = 2,
        rrf_k: int = 60,
    ) -> None:
        self._driver = driver
        self._group_id = group_id
        self._ce_model = cross_encoder_model
        self._max_depth = max_depth
        self._rrf_k = rrf_k

    # ── Public API ────────────────────────────────────────────────────────

    @staticmethod
    def _tag_results(rows: list[dict], result_type: str) -> list[dict]:
        """Return result rows with an explicit graph result type."""
        return [{**row, "type": row.get("type", result_type)} for row in rows]

    @staticmethod
    def _rerank_text(item: dict) -> str:
        """Resolve searchable text for mixed graph result rows."""
        result_type = item.get("type")
        if result_type == "episode":
            return str(item.get("content", ""))
        if result_type == "entity":
            return " ".join(str(item.get(k, "")) for k in ("name", "summary")).strip()
        return str(item.get("fact", ""))

    async def search(
        self,
        query: str,
        *,
        scope: str = "fact",
        limit: int = 10,
        as_of_time: str | None = None,
        time_start: str | None = None,
        time_end: str | None = None,
        query_embedding: list[float] | None = None,
        edge_type_filter: str | None = None,
    ) -> list[dict]:
        """Execute hybrid search across 4 sources.

        Args:
            query: Natural language query.
            scope: "fact", "entity", or "episode".
            limit: Max results to return.
            as_of_time: ISO datetime for temporal filter (default: now).
            time_start: Optional ISO lower ``valid_at`` bound for episode vector search.
            time_end: Optional ISO upper ``valid_at`` bound for episode vector search.
            query_embedding: Pre-computed query embedding for vector search.
            edge_type_filter: If set, only return facts with this edge_type.
                Only applies when scope is "fact" or "all".

        Returns:
            List of result dicts sorted by relevance.
        """
        if not query or not query.strip():
            raise ValueError("Search query must not be empty")

        if as_of_time is None:
            as_of_time = datetime.now(tz=UTC).isoformat()

        results = await asyncio.gather(
            self._vector_search(
                query,
                scope,
                as_of_time,
                query_embedding,
                time_start=time_start,
                time_end=time_end,
            ),
            self._fulltext_search(
                query,
                scope,
                as_of_time,
                time_start=time_start,
                time_end=time_end,
            ),
            self._bfs_search(
                query,
                scope,
                as_of_time,
                query_embedding,
                time_start=time_start,
                time_end=time_end,
            ),
            return_exceptions=True,
        )

        result_lists: list[list[dict]] = []
        source_names = ["vector", "fulltext", "bfs"]
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning("Search source %s failed: %s", source_names[i], r)
                continue
            if r:
                result_lists.append(r)

        if not result_lists:
            return []

        from core.memory.graph.rrf import rrf_merge

        merged = rrf_merge(result_lists, top_k=min(30, limit * 3), k=self._rrf_k)

        if not merged:
            return []

        if edge_type_filter and scope in ("fact", "all"):
            merged = [
                r
                for r in merged
                if r.get("type", "fact") == "fact" and r.get("edge_type", "RELATES_TO") == edge_type_filter
            ]

        try:
            from core.memory.graph.reranker import get_reranker

            reranker = get_reranker(self._ce_model)
            text_field = (
                self._rerank_text
                if scope == "all"
                else "fact"
                if scope == "fact"
                else "content"
                if scope == "episode"
                else "name"
            )
            return await reranker.rerank(query, merged, text_field=text_field, top_k=limit)
        except Exception:
            logger.warning("Cross-encoder rerank failed, using RRF order", exc_info=True)
            return merged[:limit]

    # ── Private search sources ────────────────────────────────────────────

    async def _vector_search(
        self,
        query: str,
        scope: str,
        as_of_time: str,
        embedding: list[float] | None,
        *,
        time_start: str | None = None,
        time_end: str | None = None,
    ) -> list[dict]:
        """Vector similarity search on fact/entity embeddings."""
        if not embedding:
            return []

        from core.memory.graph.queries import VECTOR_SEARCH_ENTITIES, VECTOR_SEARCH_FACTS

        if scope == "all":
            from core.memory.graph.queries import VECTOR_SEARCH_EPISODES, VECTOR_SEARCH_EPISODES_TEMPORAL

            use_temporal_window = time_start is not None or time_end is not None
            episode_query = VECTOR_SEARCH_EPISODES_TEMPORAL if use_temporal_window else VECTOR_SEARCH_EPISODES
            episode_params = {
                "embedding": embedding,
                "group_id": self._group_id,
                "as_of_time": as_of_time,
                "top_k": 20,
            }
            if use_temporal_window:
                episode_params.update({"time_start": time_start, "time_end": time_end})

            rows_by_type = await asyncio.gather(
                self._driver.execute_query(
                    VECTOR_SEARCH_FACTS,
                    {
                        "embedding": embedding,
                        "group_id": self._group_id,
                        "as_of_time": as_of_time,
                        "top_k": 20,
                    },
                ),
                self._driver.execute_query(
                    VECTOR_SEARCH_ENTITIES,
                    {
                        "embedding": embedding,
                        "group_id": self._group_id,
                        "top_k": 20,
                    },
                ),
                self._driver.execute_query(
                    episode_query,
                    episode_params,
                ),
                return_exceptions=True,
            )
            result_types = ("fact", "entity", "episode")
            results: list[dict] = []
            for result_type, rows in zip(result_types, rows_by_type, strict=True):
                if isinstance(rows, Exception):
                    logger.debug("Vector search on %s failed: %s", result_type, rows)
                    continue
                results.extend(self._tag_results(rows, result_type))
            return results
        if scope == "fact":
            rows = await self._driver.execute_query(
                VECTOR_SEARCH_FACTS,
                {
                    "embedding": embedding,
                    "group_id": self._group_id,
                    "as_of_time": as_of_time,
                    "top_k": 20,
                },
            )
            return self._tag_results(rows, "fact")
        if scope == "entity":
            rows = await self._driver.execute_query(
                VECTOR_SEARCH_ENTITIES,
                {
                    "embedding": embedding,
                    "group_id": self._group_id,
                    "top_k": 20,
                },
            )
            return self._tag_results(rows, "entity")
        if scope == "episode":
            from core.memory.graph.queries import VECTOR_SEARCH_EPISODES, VECTOR_SEARCH_EPISODES_TEMPORAL

            use_temporal_window = time_start is not None or time_end is not None
            if use_temporal_window:
                rows = await self._driver.execute_query(
                    VECTOR_SEARCH_EPISODES_TEMPORAL,
                    {
                        "embedding": embedding,
                        "group_id": self._group_id,
                        "as_of_time": as_of_time,
                        "time_start": time_start,
                        "time_end": time_end,
                        "top_k": 20,
                    },
                )
                return self._tag_results(rows, "episode")
            rows = await self._driver.execute_query(
                VECTOR_SEARCH_EPISODES,
                {
                    "embedding": embedding,
                    "group_id": self._group_id,
                    "as_of_time": as_of_time,
                    "top_k": 20,
                },
            )
            return self._tag_results(rows, "episode")
        return []

    async def _fulltext_search(
        self,
        query: str,
        scope: str,
        as_of_time: str,
        *,
        time_start: str | None = None,
        time_end: str | None = None,
    ) -> list[dict]:
        """BM25 fulltext search."""
        if time_start is not None or time_end is not None:
            pass  # Episode ``valid_at`` window is applied in ``_vector_search`` only.
        from core.memory.graph.queries import FULLTEXT_SEARCH_ENTITIES, FULLTEXT_SEARCH_FACTS

        if scope == "all":
            results: list[dict] = []
            try:
                fact_rows = await self._driver.execute_query(
                    FULLTEXT_SEARCH_FACTS,
                    {
                        "query": query,
                        "group_id": self._group_id,
                        "as_of_time": as_of_time,
                        "top_k": 20,
                    },
                )
                results.extend(self._tag_results(fact_rows, "fact"))
            except Exception:
                logger.debug("Fulltext search on facts failed (index may not exist)", exc_info=True)
            try:
                entity_rows = await self._driver.execute_query(
                    FULLTEXT_SEARCH_ENTITIES,
                    {
                        "query": query,
                        "group_id": self._group_id,
                        "top_k": 20,
                    },
                )
                results.extend(self._tag_results(entity_rows, "entity"))
            except Exception:
                logger.debug("Fulltext search on entities failed", exc_info=True)
            return results
        if scope == "fact":
            try:
                rows = await self._driver.execute_query(
                    FULLTEXT_SEARCH_FACTS,
                    {
                        "query": query,
                        "group_id": self._group_id,
                        "as_of_time": as_of_time,
                        "top_k": 20,
                    },
                )
                return self._tag_results(rows, "fact")
            except Exception:
                logger.debug("Fulltext search on facts failed (index may not exist)", exc_info=True)
                return []
        if scope == "entity":
            try:
                rows = await self._driver.execute_query(
                    FULLTEXT_SEARCH_ENTITIES,
                    {
                        "query": query,
                        "group_id": self._group_id,
                        "top_k": 20,
                    },
                )
                return self._tag_results(rows, "entity")
            except Exception:
                logger.debug("Fulltext search on entities failed", exc_info=True)
                return []
        return []

    async def _bfs_search(
        self,
        query: str,
        scope: str,
        as_of_time: str,
        embedding: list[float] | None,
        *,
        time_start: str | None = None,
        time_end: str | None = None,
    ) -> list[dict]:
        """Graph BFS from seed entities."""
        if time_start is not None or time_end is not None:
            pass  # Episode ``valid_at`` window is applied in ``_vector_search`` only.
        if scope not in ("fact", "all"):
            return []
        if not embedding:
            return []

        from core.memory.graph.queries import FIND_ENTITIES_BY_VECTOR, bfs_facts_query

        try:
            seeds = await self._driver.execute_query(
                FIND_ENTITIES_BY_VECTOR,
                {
                    "embedding": embedding,
                    "group_id": self._group_id,
                    "top_k": 5,
                    "min_score": 0.3,
                    "entity_type": "",
                },
            )

            if not seeds:
                return []

            all_facts: list[dict] = []
            for seed in seeds[:5]:
                seed_uuid = seed.get("uuid")
                if not seed_uuid:
                    continue
                facts = await self._driver.execute_query(
                    bfs_facts_query(self._max_depth),
                    {
                        "entity_uuid": seed_uuid,
                        "group_id": self._group_id,
                        "as_of_time": as_of_time,
                        "max_depth": 2,
                        "limit": 10,
                    },
                )
                all_facts.extend(facts)

            seen: set[str] = set()
            deduped: list[dict] = []
            for f in all_facts:
                uid = f.get("uuid", "")
                if uid and uid not in seen:
                    seen.add(uid)
                    deduped.append(f)

            return self._tag_results(deduped[:20], "fact")
        except Exception:
            logger.debug("BFS search failed", exc_info=True)
            return []
