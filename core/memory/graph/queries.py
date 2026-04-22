from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Reusable Cypher query templates for the Neo4j graph backend."""

# ── Node operations ──────────

DELETE_ALL_BY_GROUP = "MATCH (n) WHERE n.group_id = $group_id DETACH DELETE n"

COUNT_NODES_BY_GROUP = """
MATCH (n)
WHERE n.group_id = $group_id
RETURN labels(n)[0] AS label, count(n) AS cnt
"""

COUNT_EDGES_BY_GROUP = """
MATCH ()-[r]->()
WHERE r.group_id = $group_id OR (EXISTS(r.group_id) = false)
RETURN type(r) AS rel_type, count(r) AS cnt
"""

# ── Episode ──────────

CREATE_EPISODE = """
CREATE (e:Episode {
  uuid: $uuid,
  content: $content,
  source: $source,
  source_description: $source_description,
  group_id: $group_id,
  created_at: datetime($created_at),
  valid_at: datetime($valid_at)
})
RETURN e.uuid AS uuid
"""

# ── Entity ──────────

CREATE_ENTITY = """
CREATE (e:Entity {
  uuid: $uuid,
  name: $name,
  summary: $summary,
  group_id: $group_id,
  created_at: datetime($created_at),
  name_embedding: $name_embedding
})
RETURN e.uuid AS uuid
"""

UPDATE_ENTITY_SUMMARY = """
MATCH (e:Entity {uuid: $uuid})
SET e.summary = $summary
RETURN e.uuid AS uuid
"""

# ── RELATES_TO (Fact) ──────────

CREATE_FACT = """
MATCH (s:Entity {uuid: $source_uuid}), (t:Entity {uuid: $target_uuid})
CREATE (s)-[r:RELATES_TO {
  uuid: $uuid,
  fact: $fact,
  fact_embedding: $fact_embedding,
  group_id: $group_id,
  created_at: datetime($created_at),
  valid_at: datetime($valid_at),
  invalid_at: null,
  expired_at: null,
  source_episode_uuids: $source_episode_uuids
}]->(t)
RETURN r.uuid AS uuid
"""

# ── MENTIONS ──────────

CREATE_MENTION = """
MATCH (ep:Episode {uuid: $episode_uuid}), (en:Entity {uuid: $entity_uuid})
CREATE (ep)-[r:MENTIONS {uuid: $uuid, created_at: datetime($created_at)}]->(en)
RETURN r.uuid AS uuid
"""

# ── Entity Resolution ──────────

FIND_ENTITIES_BY_NAME = """
MATCH (e:Entity)
WHERE e.group_id = $group_id
  AND e.name =~ $name_pattern
RETURN e.uuid AS uuid, e.name AS name, e.summary AS summary, e.entity_type AS entity_type
LIMIT $limit
"""

FIND_ENTITIES_BY_VECTOR = """
CALL db.index.vector.queryNodes('entity_name_embedding', $top_k, $embedding)
YIELD node, score
WHERE node.group_id = $group_id
  AND score >= $min_score
RETURN node.uuid AS uuid, node.name AS name, node.summary AS summary, node.entity_type AS entity_type, score
"""

UPDATE_ENTITY_SUMMARY = """
MATCH (e:Entity {uuid: $uuid})
SET e.summary = $summary
"""

REDIRECT_MENTIONS = """
MATCH (ep:Episode)-[old:MENTIONS]->(old_entity:Entity {uuid: $old_uuid})
MATCH (new_entity:Entity {uuid: $new_uuid})
CREATE (ep)-[:MENTIONS {uuid: old.uuid, created_at: old.created_at}]->(new_entity)
DELETE old
"""

REDIRECT_OUTGOING_FACTS = """
MATCH (old_entity:Entity {uuid: $old_uuid})-[old:RELATES_TO]->(target:Entity)
MATCH (new_entity:Entity {uuid: $new_uuid})
CREATE (new_entity)-[r:RELATES_TO {
  uuid: old.uuid, fact: old.fact, fact_embedding: old.fact_embedding,
  group_id: old.group_id, created_at: old.created_at, valid_at: old.valid_at,
  invalid_at: old.invalid_at, expired_at: old.expired_at,
  source_episode_uuids: old.source_episode_uuids
}]->(target)
DELETE old
"""

REDIRECT_INCOMING_FACTS = """
MATCH (source:Entity)-[old:RELATES_TO]->(old_entity:Entity {uuid: $old_uuid})
MATCH (new_entity:Entity {uuid: $new_uuid})
CREATE (source)-[r:RELATES_TO {
  uuid: old.uuid, fact: old.fact, fact_embedding: old.fact_embedding,
  group_id: old.group_id, created_at: old.created_at, valid_at: old.valid_at,
  invalid_at: old.invalid_at, expired_at: old.expired_at,
  source_episode_uuids: old.source_episode_uuids
}]->(new_entity)
DELETE old
"""

DELETE_ENTITY = """
MATCH (e:Entity {uuid: $uuid})
DETACH DELETE e
"""
