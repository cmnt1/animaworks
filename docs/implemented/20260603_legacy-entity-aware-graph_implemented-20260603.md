---
parent: 20260603_legacy-brain-memory-expansion-epic.md
depends_on:
  - 20260603_legacy-atomic-facts-mvp.md
  - 20260603_legacy-entity-index-boost.md
  - 20260603_legacy-fact-invalidation-valid-until.md
  - 20260603_legacy-unified-memory-search.md
blocks: []
---

# Legacy Entity-Aware Graph — NetworkX graph に facts/entities/co-mention edge を追加する

## Overview

Legacy の `KnowledgeGraph` を file-to-file association から fact/entity-aware association に拡張する。Neo4j を使わず、既存 NetworkX graph に fact node、entity node、co-mention edge、fact-source edge を追加し、spreading activation が raw episode/knowledge と semantic fact/entity を横断できるようにする。

この Issue は graph拡張のみを扱う。facts、entity registry、valid_until filtering、UnifiedSearch が先に実装済みであることを前提とする。

## Problem / Background

### Current State

- `KnowledgeGraph` は memory files を node とし、Markdown `[[links]]` と vector similarity を edge とする — `core/memory/rag/graph.py:49`。
- Graph construction は Markdown files を recursive scanする — `core/memory/rag/graph.py:121`。
- Implicit links は vector similarity threshold によって追加される — `core/memory/rag/graph.py:166`。
- Personalized PageRank が spreading activation として使われる — `core/memory/rag/graph.py:599`。
- `MemoryRetriever` は `spreading_memory_types` に含まれる memory type で graph activation を使う — `core/memory/rag/retriever.py:128`、`core/config/schemas.py:206`。
- Neuroscience mapping docs は spreading activation、fan effect mitigation、recency-weighted activationを改善案として挙げている — `docs/investigations/20260305_animaworks-memory-neuroscience-mapping.md:86`、`docs/investigations/20260305_animaworks-memory-neuroscience-mapping.md:348`。

### Root Cause

1. **Graph node が file中心** — fact/entity単位の relation を PageRank に使えない。
2. **Entity co-mention edge がない** — 同じ人物/場所/概念を共有する episode/fact の連想が弱い。
3. **Fan effect 対策がない** — 多数のedgeを持つ一般 entity が activation を過剰に広げる可能性がある。
4. **Recency weighting がない** — 最近のfact/episodeが graph edge weight に反映されない。
5. **valid_until awareness がない** — expired facts を graph activation に使わない保証が必要。

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/rag/graph.py` | Direct | Node/edge types and PageRank weighting extension。 |
| `core/memory/rag/retriever.py` | Direct | Graph result expansion must map fact/entity nodes back to retrievable memory chunks。 |
| `core/config/schemas.py` | Direct | Entity-aware graph config fields。 |
| `core/memory/entity_index.py` | Indirect | Entity registry used as graph source。 |
| `core/memory/facts.py` | Indirect | Active facts used as graph source。 |
| `core/memory/retrieval/unified_search.py` | Indirect | UnifiedSearch consumes graph-expanded candidates。 |

## Decided Approach / 確定方針

### Design Decision

**確定**: Existing `KnowledgeGraph` を拡張し、NetworkX内に node_type を持つ heterogeneous graph を構築する。Node types は `memory_file`, `fact`, `entity` の3種類。Edges は existing `explicit`, `implicit` に加えて `mentions_entity`, `fact_source`, `fact_entity`, `co_mention` を追加する。PageRank edge weight は base weightに inverse-fan weighting と recency weight を掛ける。Neo4j は使わない。

### Node and Edge Model

| Node Type | Node ID | Source |
|-----------|---------|--------|
| `memory_file` | `knowledge:path`, `episodes:path` | Existing Markdown files |
| `fact` | `fact:{fact_id}` | Active `FactRecord` |
| `entity` | `entity:{normalized_name}` | `state/entity_registry.json` |

| Edge Type | Direction | Weight |
|-----------|-----------|--------|
| `explicit` | memory -> memory | 1.0 |
| `implicit` | memory -> memory | vector similarity |
| `mentions_entity` | memory -> entity and entity -> memory | 0.45 |
| `fact_source` | fact -> memory and memory -> fact | 0.65 |
| `fact_entity` | fact -> entity and entity -> fact | 0.75 |
| `co_mention` | memory/fact -> memory/fact | 0.25 capped |

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Move graph to Neo4j | Rich graph queries | Runtime bridge/default化に近く、Legacy-firstに反する | **Rejected**: NetworkX Legacy graphを拡張 |
| Entity nodes only, fact nodesなし | 実装が小さい | fact-source/validityをgraphに反映できない | **Rejected**: fact node必須 |
| Fully connect same-entity memories | Recallが増える | dense graph化しfan effect/noiseが大きい | **Rejected**: co-mention capとinverse-fanを使う |
| Recency boost only in retriever score | 実装が小さい | graph activation自体は古いedgeに偏る | **Rejected**: edge weightにも入れる |
| **Heterogeneous NetworkX graph (Adopted)** | Neo4j不要でfact/entity連想を追加できる | Graph構築が複雑化 | **Adopted**: Legacy方針と脳科学mappingに合う |

### Key Decisions from Discussion

1. **Graph拡張は最後** — Reason: fact/entity/validity/unified retrieval が安定してから連想ネットワークに入れる。
2. **Expired factsはgraph sourceにしない** — Reason: invalidated memoryをspreading activationで蘇らせない。
3. **Inverse-fan weightingを入れる** — Reason: 高degree entity の過剰activationを抑える。
4. **Recency-weighted activationを入れる** — Reason: hippocampal recency効果をLegacy graphに反映する。
5. **Entity/fact nodesはretrieval出力に直接出しすぎない** — Reason: User-facing outputは読み取り可能な fact/episode/knowledge chunk に戻す。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/rag/graph.py` | Modify | Heterogeneous node/edge construction、fact/entity source loading、edge weighting。 |
| `core/memory/rag/retriever.py` | Modify | Graph expansion results from fact/entity nodes map to fact or source memory chunks。 |
| `core/config/schemas.py` | Modify | `entity_aware_graph_enabled`, `graph_entity_edge_cap`, `graph_inverse_fan_enabled`, `graph_recency_weight_enabled`。 |
| `core/memory/entity_index.py` | Modify | Provide registry iterator for graph builder。 |
| `core/memory/facts.py` | Modify | Provide active facts iterator with as-of filtering。 |
| `tests/unit/core/memory/test_entity_aware_graph.py` | New | Graph construction and PageRank behavior tests。 |
| `tests/unit/core/memory/test_retriever_entity_aware_graph.py` | New | Retriever expansion mapping tests。 |

### Edge Cases

| Case | Handling |
|------|----------|
| Entity registry missing | Build existing file-only graph and log debug. |
| Facts directory missing | Build existing file-only graph. |
| Fact source_episode file missing | Add fact/entity edges, but skip fact_source edge. |
| Fact expired | Do not add fact node or fact edges. |
| Entity has too many linked memories | Apply edge cap per entity and inverse-fan weight. |
| Graph cache from old schema | Store graph schema version; rebuild when schema version changes. |
| PageRank returns entity nodes in top results | Map entity node to its top linked active fact/memory candidates; do not output bare entity as memory result. |
| Recency timestamp missing | Use neutral multiplier 1.0. |
| Config disabled | Existing graph behavior remains unchanged. |

## Implementation Plan

### Phase 1: Graph Schema and Source Loading

| # | Task | Target |
|---|------|--------|
| 1-1 | Add graph schema version and node_type conventions | `core/memory/rag/graph.py` |
| 1-2 | Add active fact loader integration | `core/memory/rag/graph.py`, `core/memory/facts.py` |
| 1-3 | Add entity registry iterator integration | `core/memory/rag/graph.py`, `core/memory/entity_index.py` |
| 1-4 | Add config fields with default disabled | `core/config/schemas.py` |

**Completion condition**: With config enabled, graph can include memory_file, fact, and entity nodes; with config disabled, graph is byte-for-byte behaviorally equivalent for existing file nodes.

### Phase 2: Edge Construction and Weighting

| # | Task | Target |
|---|------|--------|
| 2-1 | Add `mentions_entity`, `fact_source`, `fact_entity`, `co_mention` edges | `core/memory/rag/graph.py` |
| 2-2 | Add inverse-fan edge weighting | `core/memory/rag/graph.py` |
| 2-3 | Add recency weight multiplier | `core/memory/rag/graph.py` |
| 2-4 | Add edge cap per entity | `core/memory/rag/graph.py` |

**Completion condition**: Unit graph fixtures show expected edge types, capped degree, lower weight for high-degree entities, and higher weight for recent facts.

### Phase 3: Retrieval Expansion Mapping

| # | Task | Target |
|---|------|--------|
| 3-1 | Map fact nodes to fact chunks | `core/memory/rag/retriever.py` |
| 3-2 | Map entity nodes to top linked active fact/memory chunks | `core/memory/rag/retriever.py` |
| 3-3 | Preserve source metadata and search_method | `core/memory/rag/retriever.py` |
| 3-4 | Add retriever tests | `tests/unit/core/memory/test_retriever_entity_aware_graph.py` |

**Completion condition**: Graph activation can introduce relevant fact/episode candidates through entity paths without outputting bare entity nodes.

### Phase 4: Diagnostics

| # | Task | Target |
|---|------|--------|
| 4-1 | Add graph diagnostics counters | `core/memory/rag/graph.py` |
| 4-2 | Add `--entity-aware-graph-ablation` LoCoMo retrieval diagnostic toggle | `benchmarks/locomo/retrieval_diagnostics.py` |
| 4-3 | Run focused graph expansion regression | CLI/tests |

**Completion condition**: Entity-aware graph can be enabled in diagnostics and disabled by default in production config.

## Scope

### In Scope

- Legacy NetworkX graph only.
- Active facts and entity registry as graph sources.
- New node/edge types, inverse-fan weighting, recency weighting.
- Retriever mapping from graph nodes to memory results.
- Default-disabled config and unit tests.

### Out of Scope

- Neo4j graph use or sync — Reason: Legacy-first scope.
- Community detection — Reason: this Issue implements retrieval graph edges only; community detection is excluded from this Epic.
- LLM-based graph summarization — Reason: this Issue is graph retrieval structure only.
- Entity registry merge policy changes — Reason: handled by entity issue.
- Fact invalidation policy changes — Reason: handled by invalidation issue.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Graph becomes too dense | Slow PageRank/noisy recall | Edge caps, inverse-fan weighting, default disabled. |
| Entity nodes dominate PageRank | Irrelevant results | Do not output bare entities; map to top linked facts/memories with caps. |
| Expired facts reappear | Incorrect temporal recall | Active fact iterator filters expired facts before graph construction. |
| Cache incompatibility | Stale graph behavior | Graph schema version and rebuild on mismatch. |
| Regression in existing spreading activation | Existing search quality drops | Config disabled preserves current behavior; tests cover old path. |

## Acceptance Criteria

- [ ] Config disabled path preserves existing file-only graph behavior.
- [ ] Config enabled path adds `fact` and `entity` nodes from active facts/entity registry.
- [ ] Expired facts are not added to graph.
- [ ] Graph includes `mentions_entity`, `fact_source`, `fact_entity`, and capped `co_mention` edges.
- [ ] Inverse-fan weighting reduces edge influence from high-degree entities.
- [ ] Recency weighting increases edge influence for recent facts/episodes when timestamps exist.
- [ ] Personalized PageRank handles heterogeneous nodes without errors.
- [ ] Retriever maps fact/entity activation back to readable fact/episode/knowledge candidates.
- [ ] Bare entity nodes are never returned directly as user-facing memory results.
- [ ] Unit tests cover graph construction, edge caps, cache schema versioning, and retriever mapping.
- [ ] Focused diagnostics show entity-aware graph can be enabled without retrieval errors.

## References

- `docs/issues/20260603_legacy-atomic-facts-mvp.md` — Fact dependency.
- `docs/issues/20260603_legacy-entity-index-boost.md` — Entity registry dependency.
- `docs/issues/20260603_legacy-fact-invalidation-valid-until.md` — Active fact dependency.
- `docs/issues/20260603_legacy-unified-memory-search.md` — Retrieval integration dependency.
- `core/memory/rag/graph.py:49` — Current `KnowledgeGraph`.
- `core/memory/rag/graph.py:121` — Current file node scan.
- `core/memory/rag/graph.py:166` — Current implicit link construction.
- `core/memory/rag/graph.py:599` — Current Personalized PageRank.
- `core/memory/rag/retriever.py:128` — Current spreading activation config loading.
- `core/config/schemas.py:206` — Current graph RAG config.
- `docs/investigations/20260305_animaworks-memory-neuroscience-mapping.md:86` — Fan effect improvement note.
- `docs/investigations/20260305_animaworks-memory-neuroscience-mapping.md:348` — Recency-weighted activation improvement note.
