from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Neo4j schema management — constraints, indexes and vector indexes."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory.graph.driver import Neo4jDriver

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 4

# ── Constraints ──────────

CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Entity) REQUIRE n.uuid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Episode) REQUIRE n.uuid IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Community) REQUIRE n.uuid IS UNIQUE",
]

# ── Standard indexes ──────────

INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.group_id, n.name)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Episode) ON (n.group_id, n.valid_at)",
    # Temporal filter index for RELATES_TO edges
    "CREATE INDEX IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.valid_at)",
]

# ── Fulltext indexes (may fail on older Neo4j) ──────────

ADVANCED_INDEXES = [
    "CREATE FULLTEXT INDEX entity_name_fulltext IF NOT EXISTS FOR (n:Entity) ON EACH [n.name, n.summary]",
    "CREATE FULLTEXT INDEX fact_fulltext IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON EACH [r.fact]",
]

# ── Vector indexes (Neo4j 5.13+) ──────────

VECTOR_INDEXES = [
    {
        "name": "entity_name_embedding",
        "query": (
            "CREATE VECTOR INDEX entity_name_embedding IF NOT EXISTS "
            "FOR (n:Entity) ON n.name_embedding "
            "OPTIONS {indexConfig: {"
            "`vector.dimensions`: 384, "
            "`vector.similarity_function`: 'cosine'"
            "}}"
        ),
    },
    {
        "name": "fact_embedding",
        "query": (
            "CREATE VECTOR INDEX fact_embedding IF NOT EXISTS "
            "FOR ()-[r:RELATES_TO]-() ON r.fact_embedding "
            "OPTIONS {indexConfig: {"
            "`vector.dimensions`: 384, "
            "`vector.similarity_function`: 'cosine'"
            "}}"
        ),
    },
    {
        "name": "episode_content_embedding",
        "query": (
            "CREATE VECTOR INDEX episode_content_embedding IF NOT EXISTS "
            "FOR (n:Episode) ON n.content_embedding "
            "OPTIONS {indexConfig: {"
            "`vector.dimensions`: 384, "
            "`vector.similarity_function`: 'cosine'"
            "}}"
        ),
    },
]

# ── Migrations ──────────

MIGRATIONS = [
    # v4: Backfill temporal properties on existing data to suppress Neo4j warnings
    {
        "version": 4,
        "queries": [
            # RELATES_TO: ensure expired_at and invalid_at exist
            "MATCH ()-[r:RELATES_TO]->() WHERE r.expired_at IS NULL SET r.expired_at = null",
            "MATCH ()-[r:RELATES_TO]->() WHERE r.invalid_at IS NULL SET r.invalid_at = null",
            # Entity/Episode: ensure deleted_at exists
            "MATCH (n:Entity) WHERE n.deleted_at IS NULL SET n.deleted_at = null",
            "MATCH (n:Episode) WHERE n.deleted_at IS NULL SET n.deleted_at = null",
        ],
    },
]


async def _get_schema_version(driver: Neo4jDriver) -> dict[str, int]:
    """Read schema version from Neo4j meta node.

    Args:
        driver: Connected Neo4j driver wrapper.

    Returns:
        Dict with ``version`` key (0 if no meta node yet).
    """
    result = await driver.execute_query(
        "MATCH (m:_SchemaMeta) RETURN m.version AS version LIMIT 1",
    )
    if result:
        return {"version": result[0].get("version", 0)}
    return {"version": 0}


async def _set_schema_version(driver: Neo4jDriver, version: int) -> None:
    """Update schema version in Neo4j meta node.

    Args:
        driver: Connected Neo4j driver wrapper.
        version: Schema version to persist.
    """
    await driver.execute_write(
        "MERGE (m:_SchemaMeta) SET m.version = $version",
        {"version": version},
    )


# ── ensure_schema ──────────


async def ensure_schema(driver: Neo4jDriver) -> dict[str, int]:
    """Create all constraints and indexes idempotently.

    Returns:
        Dict with counts: ``{"constraints", "indexes", "advanced",
        "vector", "errors"}``.
    """
    counts: dict[str, int] = {
        "constraints": 0,
        "indexes": 0,
        "advanced": 0,
        "vector": 0,
        "errors": 0,
    }

    async def _run(statements: list[str], key: str) -> None:
        for stmt in statements:
            try:
                await driver.execute_write(stmt)
                counts[key] += 1
            except Exception:
                counts["errors"] += 1
                logger.warning("Schema statement failed (key=%s): %s", key, stmt, exc_info=True)

    await _run(CONSTRAINTS, "constraints")
    await _run(INDEXES, "indexes")
    await _run(ADVANCED_INDEXES, "advanced")

    for vi in VECTOR_INDEXES:
        try:
            await driver.execute_write(vi["query"])
            counts["vector"] += 1
        except Exception:
            counts["errors"] += 1
            logger.warning(
                "Vector index %r failed (requires Neo4j 5.13+): %s",
                vi["name"],
                vi["query"],
                exc_info=True,
            )

    # Run migrations
    schema_meta = await _get_schema_version(driver)
    current_version = schema_meta.get("version", 0)
    for migration in MIGRATIONS:
        if migration["version"] > current_version:
            for q in migration["queries"]:
                try:
                    await driver.execute_write(q)
                except Exception:
                    counts["errors"] += 1
                    logger.warning(
                        "Migration v%d failed: %s",
                        migration["version"],
                        q,
                        exc_info=True,
                    )
            await _set_schema_version(driver, migration["version"])
            logger.info("Applied migration v%d", migration["version"])

    logger.info("ensure_schema done: %s", counts)
    return counts
