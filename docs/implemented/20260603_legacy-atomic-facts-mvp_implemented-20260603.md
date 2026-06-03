---
parent: 20260603_legacy-brain-memory-expansion-epic.md
supersedes_scope:
  - 20260522_legacy-atomic-fact-extraction.md
depends_on:
  - 20260523_review_wave1_legacy-retrieval_APPROVED.md
blocks:
  - 20260603_legacy-entity-index-boost.md
  - 20260603_legacy-fact-invalidation-valid-until.md
  - 20260603_legacy-unified-memory-search.md
---

# Legacy Atomic Facts MVP — facts JSONL を Legacy search に統合する

## Overview

Legacy に atomic fact layer を追加し、episode を置き換えずに semanticized memory を併用できるようにする。`facts/{date}.jsonl` に append-only で保存し、1 JSONL 行を 1 fact chunk として ChromaDB に `memory_type="facts"` で索引し、`search_memory scope=facts` と `scope=all` から検索できるようにする。

この Issue は fact store と検索統合を同時に扱う。fact store だけでは評価できないため、`scope=facts` / `scope=all` までを MVP の完了条件とする。

## Problem / Background

### Current State

- `RAGMemorySearch.search_memory_text()` は `scope=all` のとき shared `RetrievalPipeline` を使う — `core/memory/rag_search.py:293`、`core/memory/rag_search.py:406`。
- `_resolve_search_types()` は `facts` を返さない — `core/memory/rag_search.py:684`。
- Keyword fallback は `knowledge`、`episodes`、`procedures`、`common_knowledge`、conversation summary を対象にするが `facts` を対象にしない — `core/memory/rag_search.py:602`。
- Indexer は memory_type ごとの chunk strategy を持つが、`facts` JSONL 専用 chunker はない — `core/memory/rag/indexer.py:573`。
- `search_memory` schema の enum に `facts` がない — `core/tooling/schemas/memory.py:27`。
- Existing `FactExtractor` は entities/facts を LLM で抽出できる — `core/memory/extraction/extractor.py:35`、`core/memory/extraction/extractor.py:107`。
- Session finalization は episode write hook を持つ — `core/memory/conversation_finalize.py:161`、`core/memory/manager.py:367`。

### Root Cause

1. **Fact persistence layer がない** — Legacy は episode/knowledge/procedure file中心で、atomic fact を durableに保存するAPIがない。
2. **Fact chunking がない** — `facts/{date}.jsonl` を1行1chunkとして索引できない。
3. **Search scope がない** — tool schema、RAG search、Legacy backend に `facts` が未登録。
4. **Extraction wrapper がない** — 既存 `FactExtractor` はあるが、Legacy fact record形式への変換、dedup、source episode記録がない。

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/facts.py` | Direct | New durable JSONL store が必要。 |
| `core/memory/fact_extraction.py` | Direct | Existing extractor から Legacy fact record に変換する。 |
| `core/memory/rag/indexer.py` | Direct | JSONL fact chunker と metadata extraction が必要。 |
| `core/memory/rag_search.py` | Direct | `scope=facts` と `scope=all` 統合が必要。 |
| `core/tooling/schemas/memory.py` | Direct | Tool schema に `facts` scope を追加する。 |
| `core/memory/backend/legacy.py` | Direct | Backend scope/rebuild/recent facts に `facts` を追加する。 |
| `core/memory/conversation_finalize.py` | Indirect | Session boundary fact extraction hook。 |
| `core/memory/consolidation.py` | Indirect | Consolidation-time fact extraction hook。 |

## Decided Approach / 確定方針

### Design Decision

**確定**: Production Legacy facts は `animas/{name}/facts/{YYYY-MM-DD}.jsonl` に保存する。1 JSONL 行を 1 `FactRecord` とし、indexer は `memory_type="facts"` のとき JSONL を parse して fact単位 chunk を生成する。Fact extraction は既存 `core/memory/extraction/extractor.py` の `FactExtractor` と `core/memory/ontology/default.py` の model/prompt を再利用し、Legacy用 wrapperで `FactRecord` に変換する。MVP では invalidation は行わず `valid_until` は空文字のまま保存する。

### FactRecord Schema

```json
{
  "fact_id": "uuid-or-stable-hash",
  "text": "Caroline attended an LGBTQ support group on 2023-05-07.",
  "source_entity": "Caroline",
  "target_entity": "LGBTQ support group",
  "edge_type": "PARTICIPATED_IN",
  "raw_edge_type": "",
  "valid_at": "2023-05-07T00:00:00+00:00",
  "recorded_at": "2026-06-03T00:00:00+09:00",
  "valid_until": "",
  "entities": ["Caroline", "LGBTQ support group"],
  "source_episode": "episodes/2026-06-03.md",
  "source_session_id": "",
  "confidence": 0.85
}
```

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| fact 1件1 markdown file | Existing whole-file chunkerを使える | productionでファイル数が増えすぎる。LoCoMo専用Issueの測定実装に近い | **Rejected**: production は JSONL |
| facts を knowledge markdown に追記 | 実装が小さい | semantic factと curated knowledge が混ざり、valid_until/reindexが難しい | **Rejected**: fact layerを分離する |
| Neo4j ingest pipeline を runtime利用 | 構造化済み | Legacy-first方針に反する | **Rejected**: DB非依存 extractor のみ再利用 |
| 毎ターン realtime extraction | 鮮度が高い | LLM cost/latencyが高い | **Rejected**: MVPは session boundary + consolidation hook |
| **JSONL fact store + dedicated chunker (Adopted)** | Appendしやすくfact粒度を保てる | indexer追加が必要 | **Adopted**: production Legacyに合う |

### Key Decisions from Discussion

1. **1+2 は同一Issue**: Fact store と `scope=facts`/`scope=all` をまとめる — Reason: 検索できなければ評価できない。
2. **Episode を置換しない**: raw episode remains hippocampal store — Reason: Legacy の recall優位を維持する。
3. **Existing FactExtractor再利用** — Reason: prompt/ontology/edge canonicalization が既にある。
4. **MVPは ADD-only** — Reason: invalidation は次 Issue で独立検証する。
5. **LLM failureはnon-fatal** — Reason: episode memory writeを壊してはいけない。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/facts.py` | New | `FactRecord` dataclass/pydantic、JSONL append/read/rewrite、stable dedup key、file lock。 |
| `core/memory/fact_extraction.py` | New | Existing `FactExtractor` を呼び、entities/factsを `FactRecord` に変換して store に書く。 |
| `core/memory/conversation_finalize.py` | Modify | `append_episode()` 成功後、new_turns/episode_entry を使って background fact extraction を呼ぶ。失敗時は warning のみ。 |
| `core/memory/consolidation.py` | Modify | Daily consolidation hook から batch fact extraction を呼ぶ。 |
| `core/memory/rag/indexer.py` | Modify | `memory_type == "facts"` で JSONL lines を fact chunks にする。metadata に `fact_id`, `valid_at`, `valid_until`, `entities`, `edge_type`, `source_episode` を入れる。 |
| `core/memory/rag_search.py` | Modify | `_resolve_search_types("facts")`, `_resolve_search_types("all")`、keyword fallback に `facts` を追加する。 |
| `core/memory/rag/retriever.py` | Modify | MVPでは `memory_type == "facts"` にも `valid_until == ""` exact filter を適用する。日付比較は C3 で扱う。 |
| `core/tooling/schemas/memory.py` | Modify | `search_memory.scope` enum と description に `facts` を追加する。 |
| `core/tooling/prompt_db.py` | Modify | search_memory説明に `facts` を追加する。 |
| `core/memory/backend/legacy.py` | Modify | `_SCOPE_TO_MEMORY_TYPE`, `_PATH_PART_TO_MEMORY_TYPE`, `rebuild_index()`, `get_recent_facts()` を facts対応にする。 |
| `tests/unit/core/memory/test_facts.py` | New | FactRecord validation、JSONL append/dedup/read。 |
| `tests/unit/core/memory/test_fact_extraction_legacy.py` | New | extractor result to FactRecord conversion。 |
| `tests/unit/core/memory/test_rag_facts_scope.py` | New | indexer/search/backend scope behavior。 |

### Edge Cases

| Case | Handling |
|------|----------|
| JSONL line is invalid | Skip the line, log warning with file path and line number, continue indexing. |
| Fact has missing `valid_at` | Store empty string; metadata omits timestamp-like conversion; retrieval still works. |
| Fact text empty | Do not write or index the fact. |
| Duplicate fact in same anima | Dedup by normalized `(source_entity, edge_type, target_entity, text, valid_at)` stable hash; skip duplicate append. |
| LLM extraction fails | Return empty list, do not fail episode/consolidation flow. |
| ChromaDB unavailable | JSONL is still written; `search_memory scope=facts` uses keyword fallback over JSONL text. |
| `valid_until` non-empty in MVP | Exclude by exact `valid_until == ""` filter for vector search; keyword fallback also skips non-empty valid_until. |
| Entity list in Chroma metadata | Store `entities` as list; `ChromaVectorStore` serializes lists to JSON string. Search result consumers treat it as metadata only. |
| Existing LoCoMo deterministic fact index | Keep separate; do not import benchmark-only writer into production path. |

## Implementation Plan

### Phase 1: Fact Store and Extraction Wrapper

| # | Task | Target |
|---|------|--------|
| 1-1 | Add `FactRecord` model and JSONL store helpers | `core/memory/facts.py` |
| 1-2 | Add stable dedup key and append/read/rewrite functions | `core/memory/facts.py` |
| 1-3 | Add Legacy wrapper around existing `FactExtractor` | `core/memory/fact_extraction.py` |
| 1-4 | Add unit tests for record validation and JSONL behavior | `tests/unit/core/memory/test_facts.py` |

**Completion condition**: Fixed extracted entities/facts can be converted to stable `FactRecord` rows and written/read from `facts/{date}.jsonl`.

### Phase 2: Ingest Hooks

| # | Task | Target |
|---|------|--------|
| 2-1 | Hook session boundary extraction after successful episode append | `core/memory/conversation_finalize.py` |
| 2-2 | Hook consolidation batch extraction | `core/memory/consolidation.py` |
| 2-3 | Ensure all extraction failures are non-fatal | `core/memory/fact_extraction.py` |

**Completion condition**: Session finalization still writes episodes when fact extraction fails, and successful extraction writes facts.

### Phase 3: Indexer and Search Scope

| # | Task | Target |
|---|------|--------|
| 3-1 | Add JSONL fact chunker | `core/memory/rag/indexer.py` |
| 3-2 | Add `scope=facts` and include facts in `scope=all` vector search | `core/memory/rag_search.py` |
| 3-3 | Add facts keyword fallback | `core/memory/rag_search.py` |
| 3-4 | Add `valid_until == ""` filtering for facts | `core/memory/rag/retriever.py` |

**Completion condition**: Indexed facts appear as `memory_type="facts"` results from `search_memory_text(scope="facts")` and participate in `scope="all"` RRF.

### Phase 4: Tooling, Backend, and Regression

| # | Task | Target |
|---|------|--------|
| 4-1 | Add `facts` to tool schema and prompt descriptions | `core/tooling/schemas/memory.py`, `core/tooling/prompt_db.py` |
| 4-2 | Add Legacy backend scope/rebuild/recent facts support | `core/memory/backend/legacy.py` |
| 4-3 | Add focused tests and one LoCoMo retrieval smoke/diagnostic where feasible | `tests/`, `benchmarks/locomo/` |

**Completion condition**: User-facing `search_memory` accepts `scope=facts`, and Legacy backend returns actual recent facts instead of activity_log proxy when facts exist.

## Scope

### In Scope

- Production Legacy fact store in `facts/{date}.jsonl`.
- Reuse of DB-independent `FactExtractor` and ontology models.
- Session boundary and consolidation hooks with non-fatal failure.
- `memory_type="facts"` indexing and retrieval.
- `search_memory scope=facts` and `scope=all` fact integration.
- Unit tests and focused regression diagnostics.

### Out of Scope

- Fact contradiction/invalidation beyond exact `valid_until == ""` filtering — Reason: next child issue.
- Entity registry and entity boost — Reason: separate child issue.
- Entity-aware graph edges — Reason: later child issue after facts/entity are stable.
- Neo4j sync or bridge — Reason: Legacy-first scope.
- LoCoMo deterministic fact writer reuse — Reason: benchmark-only measurement path.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Fact extraction adds noisy memories | `scope=all` quality regression | Keep raw episode retrieval unchanged; add facts as one RRF list, test regression. |
| JSONL parsing/indexing bugs | Missing facts or failed indexing | Dedicated parser tests, invalid-line skip behavior. |
| LLM extraction cost | Slow session finalization | Use background model, non-fatal hook, and add `facts_extraction_enabled` config defaulting to true for session/consolidation extraction. |
| Chroma metadata list handling | Entity metadata may serialize unexpectedly | Treat `entities` as diagnostics/boost metadata only; test returned metadata shape. |
| Tool schema change affects clients | Unexpected scope handling | Add enum tests and fallback to existing scopes. |

## Acceptance Criteria

- [ ] `core/memory/facts.py` provides `FactRecord` and durable JSONL read/write with dedup.
- [ ] Existing `FactExtractor` is reused through a Legacy wrapper; no Neo4j runtime dependency is introduced.
- [ ] Session boundary and consolidation hooks write facts when extraction succeeds and do not fail episode/consolidation when extraction fails.
- [ ] `MemoryIndexer` indexes `facts/{date}.jsonl` as one chunk per valid JSONL row.
- [ ] `search_memory_text(scope="facts")` returns fact results with `memory_type="facts"`.
- [ ] `search_memory_text(scope="all")` includes facts in the RRF candidate lists while preserving episode/knowledge/procedure search.
- [ ] `search_memory` tool schema accepts `facts`.
- [ ] `LegacyRAGBackend.retrieve(scope="facts")` works.
- [ ] Expired facts with non-empty `valid_until` are not returned by vector or keyword fact search in MVP.
- [ ] Unit tests cover JSONL store, chunking, scope mapping, keyword fallback, and tool schema.
- [ ] A focused LoCoMo/diagnostic run or smoke test confirms facts can be retrieved without increasing retrieval errors.

## References

- `docs/issues/20260603_legacy-brain-memory-expansion-epic.md` — Parent Epic.
- `docs/issues/20260522_legacy-atomic-fact-extraction.md:1` — Earlier C4 superseded by this revised issue.
- `core/memory/extraction/extractor.py:35` — Existing `FactExtractor`.
- `core/memory/extraction/extractor.py:107` — Existing `extract_facts`.
- `core/memory/ontology/default.py:207` — `ExtractedEntity`.
- `core/memory/ontology/default.py:215` — `ExtractedFact`.
- `core/memory/conversation_finalize.py:161` — Session finalization hook.
- `core/memory/manager.py:367` — Episode append and indexing.
- `core/memory/rag/indexer.py:573` — Chunking strategy switch.
- `core/memory/rag_search.py:293` — `search_memory_text`.
- `core/memory/rag_search.py:684` — Current scope mapping.
- `core/tooling/schemas/memory.py:27` — Current tool scope enum.
- `core/memory/backend/legacy.py:169` — Legacy retrieve entrypoint.
