# Neo4j ToolHandler Loop Isolation — Fix search_memory async driver loop reuse

## Overview

Sakura uses the per-anima Neo4j memory backend while the global backend remains legacy. Runtime checks confirmed Neo4j itself is healthy and direct `Neo4jGraphBackend.retrieve()` calls return graph results, but the synchronous `search_memory` ToolHandler path can reuse a cached async Neo4j driver across separate event loops and emit `Future attached to a different loop`. This issue fixes the ToolHandler Neo4j search lifecycle so graph search remains reliable for repeated tool calls.

## Problem / Background

### Current State

- `sakura/status.json` sets `memory_backend=neo4j`, so eligible `search_memory` scopes route to graph search.
- `MemoryManager.memory_backend` lazily creates and caches one backend instance for the manager lifetime — `core/memory/manager.py:194`.
- `_search_via_neo4j()` retrieves that cached backend and runs `backend.retrieve()` via `asyncio.run()` or a one-off thread pool — `core/tooling/handler_memory.py:194`.
- `Neo4jGraphBackend` caches an async `Neo4jDriver` after `_ensure_driver()` — `core/memory/backend/neo4j_graph.py:63`.
- Repeated ToolHandler graph searches can log: `got Future <Future pending> attached to a different loop`, then lose the vector source or fall back to legacy retrieval.

### Root Cause

1. The ToolHandler sync boundary creates a fresh event loop for each `asyncio.run()` call while reusing the same cached `Neo4jGraphBackend` and driver — `core/tooling/handler_memory.py:211`.
2. `Neo4jGraphBackend.retrieve()` calls `_ensure_driver()` and then executes async Neo4j queries through the cached driver — `core/memory/backend/neo4j_graph.py:538`.
3. The async Neo4j driver and its pending futures are event-loop-bound, so sharing that driver across event loops is unsafe.

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/tooling/handler_memory.py` | Direct | `search_memory` graph routing can degrade or fallback after repeated calls. |
| `core/memory/backend/neo4j_graph.py` | Indirect | Backend is correct when used within one async lifecycle, but unsafe when cached across sync ToolHandler event loops. |
| `tests/unit/core/memory/test_search_memory_neo4j.py` | Direct | Existing tests mock a cached backend and do not cover loop isolation. |

## Decided Approach / 確定方針

### Design Decision

確定: ToolHandlerのNeo4j検索では、`MemoryManager.memory_backend` のcached `Neo4jGraphBackend`を使わず、1回の `_search_via_neo4j()` 呼び出し内でfresh backendを作成し、同じevent loop内で `retrieve()` から `close()` まで完結させる。これにより、sync ToolHandler呼び出しごとに作られるevent loopとasync Neo4j driverの生命周期が一致し、loopまたぎのfuture再利用を防ぐ。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| Cached backend reuse | 初期化回数が少ない | `Future attached to a different loop` を再発させる | **Rejected**: 現在の根本原因を残すため |
| Global single event loop | driver再利用は可能 | MCP/ToolHandler/pytestの同期境界が複雑化し、停止処理も難しくなる | **Rejected**: 変更範囲と運用リスクが過大 |
| Neo4j失敗時に即エラー | 障害が見えやすい | 既存のlegacy fallback挙動を壊し、検索不能になる | **Rejected**: 後方互換性を落とすため |
| **Fresh backend per ToolHandler search (Adopted)** | loop境界が明確で実装範囲が小さい | 検索ごとにdriver接続が作られる | **Adopted**: 正確性を優先し、ToolHandler固有の問題に閉じられるため |

### Key Decisions from Discussion

1. **Fresh backend lifecycle**: `_search_via_neo4j()` 内でbackend生成、検索、closeを行う — Reason: event loopごとにdriver lifecycleを閉じるため。
2. **Legacy-only scopes remain legacy**: `common_knowledge` / `skills` / `activity_log` はNeo4jへ流さない — Reason: 現行設計でこれらはlegacy RAG/BM25対象のため。
3. **Fallback remains**: Neo4j検索が例外を出した場合は `None` を返して既存legacy検索へfallbackする — Reason: 既存利用者向けの検索継続性を維持するため。

### Changes by Module

| Module | Change Type | Description |
|--------|-------------|-------------|
| `core/tooling/handler_memory.py` | Modify | Neo4j検索用のfresh backend生成ヘルパーを追加し、`_search_via_neo4j()` でcached backendを使わないようにする。 |
| `tests/unit/core/memory/test_search_memory_neo4j.py` | Modify | fresh backend生成、close、連続検索でのbackend分離、fallback挙動を検証する。 |
| `core/memory/backend/neo4j_graph.py` | No change | async backend自体は既存のasync利用経路で正しく使えるため、ToolHandler側でsync境界を隔離する。 |

### Edge Cases

| Case | Handling |
|------|----------|
| Neo4j backend creation fails | `_search_via_neo4j()` returns `None`; legacy search fallback runs. |
| `retrieve()` raises | Backend is closed in `finally`; legacy fallback runs. |
| `close()` raises | Log at debug level and still return/fallback based on retrieval result. |
| Empty Neo4j results | Return empty string so `_handle_search_memory()` can emit no-results plus anima hint when applicable. |
| Running inside an active event loop | Keep the existing thread-pool bridge, but create and close the backend inside the coroutine executed in that thread. |

## Implementation Plan

### Phase 1: ToolHandler lifecycle fix

| # | Task | Target |
|---|------|--------|
| 1-1 | Add a helper to create a fresh Neo4j backend using `get_backend("neo4j", self._anima_dir)`. | `core/tooling/handler_memory.py` |
| 1-2 | Move async retrieval into a coroutine that owns backend creation and `await backend.close()` in `finally`. | `core/tooling/handler_memory.py` |
| 1-3 | Preserve existing scope mapping, pagination, formatting, and fallback behavior. | `core/tooling/handler_memory.py` |

**Completion condition**: Repeated sync `search_memory` graph calls no longer reuse the same async driver across event loops.

### Phase 2: Regression tests

| # | Task | Target |
|---|------|--------|
| 2-1 | Update mocked tests so `_search_via_neo4j()` uses a fresh backend factory instead of `mock_memory.memory_backend`. | `tests/unit/core/memory/test_search_memory_neo4j.py` |
| 2-2 | Add test proving two consecutive searches create and close two separate backends. | `tests/unit/core/memory/test_search_memory_neo4j.py` |
| 2-3 | Run Sakura Neo4j E2E recovery test to keep all-scope retrieval covered. | `tests/e2e/test_sakura_neo4j_memory_recovery_e2e.py` |

**Completion condition**: Unit and Sakura E2E tests pass.

## Scope

### In Scope

- Fix `search_memory` ToolHandler Neo4j lifecycle isolation.
- Preserve graph output format and legacy fallback.
- Add focused unit regression coverage.
- Run the existing Sakura Neo4j recovery E2E test.

### Out of Scope

- New runtime conversation or direct ingest write test — Reason: It mutates live memory data.
- Neo4j `deleted_at` / `expired_at` warning cleanup — Reason: Search succeeds and this is a separate schema/noise issue.
- `core.tooling.handler` import cycle cleanup — Reason: Separate test collection issue outside runtime Neo4j search lifecycle.
- Global Neo4j connection pooling redesign — Reason: Larger architectural change not required for this bug.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Per-search Neo4j connection overhead | Search latency may increase slightly | Limit change to sync ToolHandler path; async priming/backend direct paths keep current lifecycle. |
| Test mocks diverge from real backend behavior | False confidence | Add assertions for factory call count, close call count, and fallback behavior. |
| Fallback behavior regression | Users may see empty/error results instead of legacy results | Preserve `None` return on exceptions and existing `_handle_search_memory()` fallback branch. |

## Acceptance Criteria

- [ ] `search_memory(scope="all")` uses graph search when the active backend is Neo4j.
- [ ] `search_memory(scope="knowledge"|"episodes"|"procedures")` maps to `fact` / `episode` / `fact` as before.
- [ ] Consecutive `_search_via_neo4j()` calls create separate backend instances and close each one.
- [ ] Neo4j failure still falls back to legacy `search_memory_text()`.
- [ ] `activity_log`, `common_knowledge`, and `skills` never route to Neo4j.
- [ ] `python3 -m pytest -q tests/unit/core/memory/test_search_memory_neo4j.py tests/e2e/test_sakura_neo4j_memory_recovery_e2e.py` passes.

## References

- `core/tooling/handler_memory.py:184` — Neo4j routing and ToolHandler search implementation.
- `core/memory/manager.py:194` — cached `memory_backend` property.
- `core/memory/backend/neo4j_graph.py:63` — cached async Neo4j driver lifecycle.
- `core/memory/backend/neo4j_graph.py:522` — graph `retrieve()` implementation.
- `tests/unit/core/memory/test_search_memory_neo4j.py:115` — current ToolHandler Neo4j tests.
- `tests/e2e/test_sakura_neo4j_memory_recovery_e2e.py:63` — all-scope Neo4j retrieval E2E coverage.
