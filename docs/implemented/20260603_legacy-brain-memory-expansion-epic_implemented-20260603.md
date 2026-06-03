---
parent: 20260522_legacy-memory-enhancement-epic.md
supersedes_scope:
  - 20260522_legacy-atomic-fact-extraction.md
  - 20260522_legacy-entity-index-boost.md
  - 20260522_legacy-ingest-contradiction-invalidation.md
  - 20260522_legacy-priming-search-unification.md
children:
  - 20260603_legacy-atomic-facts-mvp.md
  - 20260603_legacy-entity-index-boost.md
  - 20260603_legacy-fact-invalidation-valid-until.md
  - 20260603_legacy-unified-memory-search.md
  - 20260603_legacy-entity-aware-graph.md
---

# Legacy Brain Memory Expansion Epic — legacy を主系にした fact/entity/graph 記憶拡張

## Overview

Legacy memory は LoCoMo で Neo4j full より高い recall を示しているため、本 Epic では Legacy を主系として維持し、Neo4j 的な構造化記憶の考え方だけを Legacy に移植する。対象は atomic facts、entity index、valid_until invalidation、unified retrieval、entity-aware NetworkX graph であり、Neo4j backend の拡張や runtime bridge は行わない。

この Epic は `docs/issues/20260522_legacy-memory-enhancement-epic.md` の Wave 2/3 を 2026-06-03 時点の実装状態に合わせて改訂する。Wave 1 の shared retrieval/RRF/rerank/confidence gate は実装済みとして扱う。

## Problem / Background

### Current State

- Wave 1 は承認済みで、`core/memory/retrieval/` の shared pipeline、Legacy `scope=all` rerank、confidence gate、LoCoMo smoke harness は実装済みである — `docs/issues/20260523_review_wave1_legacy-retrieval_APPROVED.md:1`。
- Legacy `scope=all` は vector、graph episodes、activity_log BM25、keyword fallback を `RetrievalPipeline` で統合している — `core/memory/rag_search.py:406`。
- Legacy の vector search scope には `facts` が含まれていない — `core/memory/rag_search.py:684`。
- `search_memory` tool schema に `facts` scope がない — `core/tooling/schemas/memory.py:27`。
- Neo4j 用に DB 非依存の `FactExtractor` と ontology model は存在する — `core/memory/extraction/extractor.py:35`、`core/memory/ontology/default.py:207`。
- Legacy graph は Markdown file node と vector similarity edge を扱うが、entity/fact/co-mention edge は扱わない — `core/memory/rag/graph.py:49`。
- `LegacyRAGBackend.get_recent_facts()` は実 fact ではなく activity_log BM25 proxy を返している — `core/memory/backend/legacy.py:381`。

### Root Cause

1. **Legacy の符号化粒度が episode/knowledge chunk 中心で粗い** — fact 単位の semanticized memory が production Legacy にない。
2. **Entity が first-class store ではない** — retrieval pipeline の entity boost helper は存在するが、production Legacy の entity registry / collection / query wiring がない。
3. **valid_until が knowledge frontmatter 中心** — fact の contradiction / duplicate / complement handling がない。
4. **検索経路が分散している** — `RAGMemorySearch`、`LegacyRAGBackend`、Priming C/F/G、LoCoMo adapter が完全には同じ retrieval policy を共有していない。
5. **Legacy graph が fact/entity を持たない** — spreading activation が file-to-file association に留まり、Neo4j 的な multi-hop relation signal を Legacy 内で表現できない。

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/rag_search.py` | Direct | `scope=facts` と `scope=all` fact統合がない。 |
| `core/memory/rag/indexer.py` | Direct | JSONL fact を fact単位 chunk として索引できない。 |
| `core/memory/retrieval/` | Direct | entity boost受け口はあるが production config/store 接続がない。 |
| `core/memory/backend/legacy.py` | Direct | `facts` scope と real recent facts がない。 |
| `core/memory/priming/` | Direct | automatic recall が unified retrieval と未統一。 |
| `core/memory/rag/graph.py` | Direct | entity/fact/co-mention edge がない。 |
| Neo4j backend | None | 既存挙動を維持し、default 切替や runtime bridge は行わない。 |

## Decided Approach / 確定方針

### Design Decision

**確定**: Legacy を主系にして、Epic + 5 child issues に分割する。Atomic Facts MVP で `facts/{date}.jsonl` と `scope=facts` / `scope=all` 統合を作り、続いて Entity Index Boost、Fact Invalidation、Unified Memory Search、Entity-aware Legacy Graph の順に実装する。Neo4j backend は runtime 依存にせず、既存の DB 非依存 extractor / ontology / retrieval helpers だけを Legacy-compatible module として再利用する。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| 1つの巨大 Issue にまとめる | 全体像は見える | fact store、search、entity、invalidation、priming、graph が混ざりレビュー不能 | **Rejected**: regression原因を分離できない |
| Neo4j backend を伸ばして Legacy と runtime bridge する | Neo4j の構造化検索を使える | ユーザー方針と異なり、Legacy の LoCoMo recall優位を主系にできない | **Rejected**: 本 Epic は Legacy 拡張である |
| LoCoMo deterministic fact index を production に流用 | 実装が小さい | benchmark専用の sentence split で、production の semantic consolidation ではない | **Rejected**: production は LLM FactExtractor + JSONL store |
| 既存 C4-C7 をそのまま実装 | 既存文書を再利用できる | 現在の実装状態とずれがある。`FactExtractor`/entity boost helper が既に存在する | **Rejected**: 2026-06-03 改訂版 Issue を作る |
| **Epic + 5 child issues (Adopted)** | レビュー可能、評価可能、順序依存を明確にできる | Issue数は増える | **Adopted**: 実装とLoCoMo回帰を段階的に管理できる |

### Key Decisions from Discussion

1. **Legacy-first**: Neo4j を拡張せず、Legacy を脳科学ベースで発展させる — Reason: Legacy の方が現状能力が高いというユーザー判断に合う。
2. **Atomic facts と search integration は同一 child Issue** — Reason: fact store だけでは評価できず、`scope=facts` / `scope=all` まで必要。
3. **Production facts は JSONL** — Reason: `facts/{date}.jsonl` は append に強く、専用 chunker で fact単位粒度を保てる。
4. **FactExtractor を再利用** — Reason: `core/memory/extraction/extractor.py` と ontology prompt は既に DB 非依存で存在する。
5. **Entity-aware graph は最後** — Reason: fact/entity/validity が安定してから graph edge に取り込む必要がある。
6. **Neo4j default化なし** — Reason: Legacy recall優位と運用単純性を維持する。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/facts.py` | New | `FactRecord`、JSONL read/write、dedup、file lock を提供する。 |
| `core/memory/fact_extraction.py` | New | `FactExtractor` を Legacy fact record に変換し、session/consolidation hook から呼ぶ。 |
| `core/memory/rag/indexer.py` | Modify | `memory_type="facts"` の JSONL chunker を追加する。 |
| `core/memory/rag_search.py` | Modify | `scope=facts` と `scope=all` fact統合を追加する。 |
| `core/tooling/schemas/memory.py` | Modify | `search_memory.scope` enum に `facts` を追加する。 |
| `core/memory/entity_index.py` | New | registry / collection / production boost wiring を提供する。 |
| `core/memory/fact_invalidation.py` | New | ADD/SKIP/INVALIDATE/UPDATE reconciliation を提供する。 |
| `core/memory/retrieval/unified_search.py` | New | Legacy retrieval entrypoint を統一する。 |
| `core/memory/rag/graph.py` | Modify | fact/entity/co-mention edge と graph scoring policy を追加する。 |

### Child Issues

| # | Issue | Dependency | Summary |
|---|-------|------------|---------|
| 1 | `20260603_legacy-atomic-facts-mvp.md` | Wave 1 retrieval | `facts` store/index/search integration |
| 2 | `20260603_legacy-entity-index-boost.md` | 1 | entity registry + production search boost |
| 3 | `20260603_legacy-fact-invalidation-valid-until.md` | 1 | contradiction / duplicate / valid_until |
| 4 | `20260603_legacy-unified-memory-search.md` | 1,2,3 | search_memory / backend / priming / LoCoMo route unification |
| 5 | `20260603_legacy-entity-aware-graph.md` | 1,2,3,4 | NetworkX graph fact/entity expansion |

### Edge Cases

| Case | Handling |
|------|----------|
| LLM fact extraction fails | Episode indexing continues; facts are skipped with warning. |
| ChromaDB unavailable | JSONL write remains durable; `scope=facts` falls back to keyword JSONL scan. |
| Existing Neo4j backend selected | Neo4j path keeps existing behavior; new modules are Legacy-only unless explicitly reused later. |
| Fact/entity causes noisy candidates | Child issues must keep episode/knowledge retrieval intact and run LoCoMo regression/ablation. |
| Old C4-C7 still exist | New issues supersede their implementation scope; old docs remain historical references. |

## Implementation Plan

### Phase 1: Atomic Facts MVP

| # | Task | Target |
|---|------|--------|
| 1-1 | Create fact record/store and extraction wrapper | `core/memory/facts.py`, `core/memory/fact_extraction.py` |
| 1-2 | Add JSONL fact indexing and search scope | `core/memory/rag/indexer.py`, `core/memory/rag_search.py` |
| 1-3 | Add tool schema and backend scope support | `core/tooling/schemas/memory.py`, `core/memory/backend/legacy.py` |

**Completion condition**: `search_memory scope=facts` and `scope=all` return fact chunks without removing episode retrieval.

### Phase 2: Entity and Validity

| # | Task | Target |
|---|------|--------|
| 2-1 | Add production entity registry and boost | `core/memory/entity_index.py`, `core/memory/retrieval/pipeline.py` |
| 2-2 | Add fact invalidation and expired filtering | `core/memory/fact_invalidation.py`, `core/memory/rag/retriever.py` |

**Completion condition**: Entity boost and fact invalidation are independently tested and default-safe.

### Phase 3: Unified Recall and Graph Expansion

| # | Task | Target |
|---|------|--------|
| 3-1 | Unify Legacy retrieval entrypoints | `core/memory/retrieval/unified_search.py` |
| 3-2 | Add entity-aware graph edges | `core/memory/rag/graph.py` |

**Completion condition**: Priming/search_memory/Legacy backend share the same Legacy retrieval policy, and graph expansion uses fact/entity edges.

## Scope

### In Scope

- Legacy filesystem + ChromaDB memory system.
- DB-independent extraction/ontology modules already in `core/memory/extraction/` and `core/memory/ontology/`.
- `facts`, entity registry, invalidation, unified search, and NetworkX graph extension.
- LoCoMo retrieval diagnostics/smoke guardrails for each child issue.

### Out of Scope

- Neo4j backend default化 — Reason: Legacy-first 方針に反する。
- Neo4j runtime bridge — Reason: Legacy単体で発展させる。
- Production use of LoCoMo deterministic sentence fact index — Reason: benchmark-only measurement implementation。
- New embedding/reranker model migration — Reason: retrieval structureの後に別Issueで扱う。
- Community detection migration — Reason: entity-aware graph後の別Epic。

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Facts add noisy recall | F1 regression, prompt pollution | `scope=all` keeps episode/knowledge lists; child issue requires LoCoMo regression and fallback. |
| JSONL update complexity | invalidation rewrite bugs | Fact store module owns atomic rewrite/file lock; tests cover same-file updates. |
| Entity boost overfits | adversarial regression | Production boost cap/config and LoCoMo category/regression checks. |
| Unified search broad change | Priming/search behavior regression | Implement after fact/entity/invalidation; compare top-k set for search vs Priming. |
| Graph expansion cost | slow startup/search | Gate with config, cache graph, add edge caps and inverse-fan weighting. |

## Acceptance Criteria

- [ ] Five child Issue files exist and include implementation-ready scope, risks, edge cases, and acceptance criteria.
- [ ] Legacy `scope=facts` works after child issue 1.
- [ ] Legacy `scope=all` includes facts while preserving episode/knowledge retrieval.
- [ ] Entity boost and fact invalidation are independently testable and configurable.
- [ ] Priming and `search_memory` share one Legacy retrieval entrypoint after child issue 4.
- [ ] Entity-aware graph is implemented without requiring Neo4j.
- [ ] LoCoMo Legacy baseline is guarded for each child issue.

## References

- `docs/issues/20260522_legacy-memory-enhancement-epic.md:1` — Earlier Epic.
- `docs/issues/20260523_review_wave1_legacy-retrieval_APPROVED.md:1` — Wave 1 implemented baseline.
- `core/memory/rag_search.py:406` — Current Legacy hybrid `scope=all`.
- `core/memory/rag_search.py:684` — Current scope mapping without `facts`.
- `core/tooling/schemas/memory.py:27` — Current `search_memory` scope enum.
- `core/memory/extraction/extractor.py:35` — Existing DB-independent `FactExtractor`.
- `core/memory/ontology/default.py:207` — Existing entity/fact models.
- `core/memory/rag/graph.py:49` — Current file-based KnowledgeGraph.
