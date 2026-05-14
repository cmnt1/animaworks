from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Opt-in live smoke tests for the Neo4j memory backend."""

import os
from pathlib import Path
from uuid import uuid4

import pytest

from core.memory.ontology.default import ExtractedEntity, ExtractedFact

pytestmark = [pytest.mark.integration, pytest.mark.neo4j, pytest.mark.asyncio]


class _StubExtractor:
    async def extract_entities(self, content: str) -> list[ExtractedEntity]:
        return [
            ExtractedEntity(
                name="AnimaWorks",
                entity_type="Organization",
                summary="Digital Anima Framework",
            ),
            ExtractedEntity(
                name="Neo4j",
                entity_type="Concept",
                summary="Graph database used for memory",
            ),
        ]

    async def extract_facts(
        self,
        content: str,
        entities: list[ExtractedEntity],
        *,
        reference_time: str | None = None,
    ) -> list[ExtractedFact]:
        return [
            ExtractedFact(
                source_entity="AnimaWorks",
                target_entity="Neo4j",
                fact="AnimaWorks uses Neo4j for graph memory smoke testing",
                valid_at=reference_time,
                edge_type="RELATES_TO",
            )
        ]


class _StubInvalidator:
    async def find_and_invalidate(self, **kwargs: object) -> list[dict]:
        return []


def _require_live_neo4j() -> None:
    if os.environ.get("ANIMAWORKS_TEST_NEO4J") != "1":
        pytest.skip("Set ANIMAWORKS_TEST_NEO4J=1 to run live Neo4j tests")


async def test_neo4j_backend_live_ingest_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_live_neo4j()

    from core.memory.backend.neo4j_graph import Neo4jGraphBackend

    group_id = f"test-neo4j-{uuid4()}"
    backend = Neo4jGraphBackend(
        tmp_path,
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "animaworks"),
        database=os.environ.get("NEO4J_DATABASE", "neo4j"),
        group_id=group_id,
    )

    async def _empty_embeddings(texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]

    monkeypatch.setattr(backend, "_get_extractor", lambda: _StubExtractor())
    monkeypatch.setattr(backend, "_get_invalidator", lambda: _StubInvalidator())
    monkeypatch.setattr(backend, "_embed_texts", _empty_embeddings)

    try:
        await backend.reset()
        ingested = await backend.ingest_text(
            "AnimaWorks stores memory in Neo4j.",
            source="integration-test",
            metadata={"episode_uuid": f"{group_id}:episode"},
        )

        stats = await backend.stats()

        assert ingested == 4
        assert stats["nodes_Episode"] == 1
        assert stats["nodes_Entity"] == 2
        assert stats["edges_RELATES_TO"] >= 1
    finally:
        await backend.reset()
        await backend.close()
