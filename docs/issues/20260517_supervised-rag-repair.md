# Supervised RAG Repair — Stop anima, rebuild vectordb out-of-process, then restart

## Overview

RAG corruption auto-repair must remain automatic, but destructive ChromaDB repair must not run inside an already-running HTTP/anima process. This issue changes RAG repair from in-process background repair to a supervised lifecycle: detect corruption, mark the anima as degraded, stop the target anima, run a separate repair CLI process, then restart the anima.

This is the project-side fix for the 2026-05-17 hhcpcserver incident where RAG repair held `rag_repair.lock`, left Chroma/SQLite handles open against an archived `vectordb`, and caused repeated HTTP freezes.

## Problem / Background

### Current State

- `RAGRepairService.record_chroma_error()` classifies Chroma/SQLite corruption and starts repair automatically after threshold or single-shot corruption reasons.
- `RAGRepairService.request_repair(background=True)` starts a daemon thread in the current process.
- `repair_anima()` calls `quarantine_vectordb()` and `full_reindex()` in that same process.
- `quarantine_vectordb()` moves the live `vectordb` directory after `reset_vector_store()` and `gc.collect()`, but `ChromaVectorStore` has no `close()` method.
- `reset_vector_store()` calls `close()` only when present, so local Chroma clients are dropped from the cache without an explicit Chroma close.
- `repair_enabled` defaults to `True`, so the unsafe background repair path is enabled by default.

Relevant code:

- `core/memory/rag/repair_service.py:87` — Chroma error recording and repair trigger path
- `core/memory/rag/repair_service.py:175` — `request_repair()` background repair entrypoint
- `core/memory/rag/repair_service.py:194` — daemon thread creation for repair
- `core/memory/rag/repair_service.py:275` — synchronous destructive `repair_anima()`
- `core/memory/rag/repair_service.py:312` — quarantine before reindex
- `core/memory/rag/repair_rebuild.py:17` — `quarantine_vectordb()` moves the live vectordb
- `core/memory/rag/singleton.py:222` — `reset_vector_store()` only closes stores with `close()`
- `core/memory/rag/store.py:142` — `ChromaVectorStore` lacks `close()`
- `core/config/schemas.py:214` — `repair_enabled` default is `True`
- `core/supervisor/_mgr_health.py:349` — supervisor already has a pre-restart RAG repair hook

### Root Cause

1. In-process destructive repair moves a live Chroma/SQLite directory while the process can still hold DB handles — `core/memory/rag/repair_service.py:194`, `core/memory/rag/repair_rebuild.py:17`.
2. `ChromaVectorStore` does not expose `close()`, so `reset_vector_store()` cannot explicitly release Chroma clients — `core/memory/rag/singleton.py:222`, `core/memory/rag/store.py:142`.
3. Repair state is too coarse for incident recovery. It records success/failure, but not enough stage, PID, or heartbeat information to distinguish a live repair from a stuck lock — `core/memory/rag/repair_service.py:301`.
4. Supervisor repair currently runs only as part of restart handling after process failure, not as the primary flow for live corruption detection — `core/supervisor/_mgr_health.py:304`.

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/rag/repair_service.py` | Direct | Starts repair in the current process and performs destructive DB operations. |
| `core/memory/rag/repair_rebuild.py` | Direct | Moves `vectordb` and reindexes without process-level isolation. |
| `core/memory/rag/store.py` | Direct | Missing Chroma close leaves reset behavior incomplete. |
| `core/memory/rag/singleton.py` | Direct | Cache reset cannot guarantee Chroma release without store close. |
| `core/supervisor/_mgr_health.py` | Direct | Must become the owner of automatic destructive repair lifecycle. |
| `cli/parser.py` / `cli/commands/` | Direct | Needs an explicit `repair-rag` command for out-of-process repair. |
| `cli/commands/index_cmd.py` | Indirect | Existing repair-lock skip behavior must remain intact during repair. |

## Decided Approach / 確定方針

### Design Decision

確定: RAG auto-repair remains enabled, but corruption detection only records a supervised repair request in the current process. The supervisor owns the destructive repair lifecycle: stop the target anima, run `animaworks repair-rag --anima <name> --full --shared` in a separate process, then restart the anima. `ChromaVectorStore.close()` is added to improve normal reset behavior, but safety depends on process isolation and supervised stop/restart, not on close alone.

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| A: Keep existing background repair and add `close()` | Small patch | Still performs destructive `vectordb` move inside a process that may have Chroma/SQLite handles or child clients alive | **Rejected**: insufficient recurrence prevention for the 2026-05-17 failure mode |
| B: Disable all automatic repair and require manual CLI | Simplest operationally safe path | Loses automatic recovery and leaves degraded RAG until an operator acts | **Rejected**: user confirmed automatic recovery should remain |
| C: Move Chroma to a dedicated server in this issue | Strong isolation | Large architecture change beyond the incident fix | **Rejected**: too broad for this recovery hardening issue |
| D: Supervised repair with out-of-process rebuild | Preserves automatic recovery and avoids live-process destructive repair | Requires supervisor flow and CLI command | **Adopted**: matches the confirmed requirement |

### Key Decisions from Discussion

1. **Automatic repair stays on**: `repair_enabled=True` keeps meaning "supervised automatic RAG repair is enabled" — Reason: automatic recovery is required.
2. **No destructive repair inside a live anima/HTTP process**: detection records state only — Reason: live Chroma/SQLite handles caused the incident.
3. **Supervisor stops only the affected anima**: HTTP server remains up — Reason: one anima RAG repair must not take down the whole dashboard/API.
4. **Repair runs as a separate CLI process**: the command is `animaworks repair-rag --anima <name> --full --shared` — Reason: process isolation gives a clean Chroma lifecycle for quarantine and rebuild.
5. **`ChromaVectorStore.close()` is still required**: reset paths should close clients when possible — Reason: this improves normal resource hygiene and testability.
6. **State must be operationally useful**: repair state includes status, stage, PID, timestamps, heartbeat, quarantine path, chunk count, and last error — Reason: stuck lock recovery needs concrete evidence.

### Changes by Module

| Module | Change Type | Description |
|--------|-------------|-------------|
| `core/memory/rag/repair_service.py` | Modify | Change `request_repair(background=True)` to record a supervised repair request instead of starting `_run_repair_guarded` thread. Keep synchronous `repair_anima_if_allowed()` for CLI use. |
| `core/memory/rag/repair_rebuild.py` | Modify | Keep quarantine and full reindex helpers, but document and enforce that destructive rebuild is called by CLI/supervisor repair flow. |
| `core/memory/rag/store.py` | Modify | Add idempotent `ChromaVectorStore.close()` that calls `self.client.close()` when available and clears the client reference/state safely. |
| `core/memory/rag/singleton.py` | Modify | Preserve reset behavior and add tests proving `close()` is called for cached Chroma stores. |
| `core/memory/rag/repair_types.py` | Modify | Extend `RepairResult` with optional `stage` and `state_path` fields if needed by CLI/supervisor reporting. |
| `core/supervisor/_mgr_health.py` | Modify | Add supervised repair runner: detect requested repair state, stop target anima, run CLI repair process with timeout, restart target anima, broadcast repair event. |
| `cli/commands/repair_rag_cmd.py` | New | Implement `repair-rag` command that runs synchronous `repair_anima_if_allowed()` and exits non-zero on failure. |
| `cli/parser.py` | Modify | Register top-level `repair-rag` command. |
| `core/config/schemas.py` | Modify | Keep `repair_enabled=True`; add `repair_timeout_seconds` default `1800` and `repair_poll_interval_seconds` default `5`. |
| `tests/unit/core/memory/test_rag_repair.py` | Modify | Update repair tests for request-only detection and CLI/synchronous repair behavior. |
| `tests/unit/core/supervisor/` | Modify | Add supervised repair flow tests. |
| `tests/unit/cli/` | Modify | Add `repair-rag` command tests. |

#### Change 1: Replace in-process background repair with request state

**Target**: `core/memory/rag/repair_service.py`

```python
# Before
if background:
    thread = threading.Thread(target=self._run_repair_guarded, ...)
    thread.start()
    return True

# After
if background:
    self._write_repair_request_state(
        anima_name,
        reason=reason,
        collection=collection,
        source=source,
        include_shared=include_shared,
    )
    return True
```

Required state fields for a request:

```json
{
  "status": "requested",
  "stage": "detect",
  "requested_at": "<iso8601>",
  "updated_at": "<iso8601>",
  "reason": "sqlite_malformed",
  "collection": "midori_knowledge",
  "source": "query",
  "include_shared": true,
  "last_error": null
}
```

#### Change 2: Add explicit Chroma close

**Target**: `core/memory/rag/store.py`

```python
def close(self) -> None:
    close = getattr(self.client, "close", None)
    if callable(close):
        close()
```

The method must be idempotent. A second call returns without raising.

#### Change 3: Add CLI repair command

**Target**: `cli/commands/repair_rag_cmd.py`

Command contract:

```bash
animaworks repair-rag --anima midori --full --shared
```

Behavior:

- `--anima` is required.
- `--full` is accepted and required for destructive quarantine/rebuild.
- `--shared` sets `include_shared=True`.
- On success, print status, chunks indexed, and quarantine path.
- On failure, print status and error to stderr, then exit with code `1`.

#### Change 4: Supervisor-owned repair lifecycle

**Target**: `core/supervisor/_mgr_health.py`

Flow:

1. Read target anima `state/rag_repair.json`.
2. If `status == "requested"`, transition to `status="stopping"`, `stage="stop_anima"`.
3. Stop the target anima process using existing supervisor process handle controls.
4. Run CLI repair subprocess with timeout from config:
   `python -m cli repair-rag --anima <name> --full --shared`
5. On CLI success, transition to `status="success"`, `stage="restart_anima"`, then restart anima.
6. On restart success, transition to `status="healthy"`, `stage="complete"`.
7. On repair failure, keep anima stopped only when the old DB has already been quarantined and no valid active DB exists; otherwise restart anima in degraded mode.

### Repair State Contract

The JSON file at `<anima>/state/rag_repair.json` must use these fields:

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `status` | string | yes | `healthy`, `requested`, `stopping`, `repairing`, `success`, `failed`, `repair_success_restart_failed`, `disabled`, `cooldown`, `locked` |
| `stage` | string | yes | `detect`, `stop_anima`, `close_clients`, `quarantine`, `reindex`, `reset_store`, `restart_anima`, `complete`, `failed` |
| `pid` | integer/null | yes | Process currently performing repair |
| `started_at` | string/null | yes | Repair start timestamp |
| `requested_at` | string/null | yes | Detection/request timestamp |
| `updated_at` | string | yes | Last state update timestamp |
| `heartbeat_at` | string/null | yes | Last repair progress heartbeat |
| `reason` | string/null | yes | Corruption reason |
| `collection` | string/null | yes | Collection that produced the signal |
| `source` | string/null | yes | Source operation that produced the signal |
| `include_shared` | bool | yes | Whether shared collections are rebuilt |
| `last_error` | string/null | yes | Last failure message |
| `last_quarantine_path` | string/null | yes | Quarantined vectordb path |
| `last_chunks_indexed` | integer | yes | Number of chunks indexed by last successful repair |

### Edge Cases

| Case | Handling |
|------|----------|
| Target anima stop fails | Do not run repair CLI. Set `status="failed"`, `stage="stop_anima"`, `last_error` to the stop failure. |
| Repair CLI times out | Kill the repair subprocess. Set `status="failed"`, keep `stage` at the active stage, set `last_error` to timeout message. |
| Repair succeeds but restart fails | Set `status="repair_success_restart_failed"`, `stage="restart_anima"`, record restart error, broadcast event. |
| Repair lock already held | Do not start another repair. Set or preserve `status="locked"` with current state details. |
| New corruption signals arrive while repair is requested | Append to `recent_signals`, keep a single repair request active. |
| Daily/shared indexing runs during repair | Existing `is_repair_locked()` skip behavior remains; no local vector store is opened for the locked anima. |
| Chroma `close()` is unavailable | `ChromaVectorStore.close()` returns without raising after logging at debug level. |
| Active DB missing after failed quarantine | Leave anima stopped and set `status="failed"` with `stage` and `last_quarantine_path`; operator can restore from archive. |

## Implementation Plan

### Phase 1: Repair State and Request Semantics

| # | Task | Target |
|---|------|--------|
| 1-1 | Add helper to write request state with required fields | `core/memory/rag/repair_service.py` |
| 1-2 | Change background repair path to request-only state write | `core/memory/rag/repair_service.py` |
| 1-3 | Keep synchronous `repair_anima_if_allowed()` for CLI execution | `core/memory/rag/repair_service.py` |
| 1-4 | Extend state updates with `status`, `stage`, `pid`, timestamps, heartbeat, error, quarantine path, chunk count | `core/memory/rag/repair_service.py` |

**Completion condition**: Chroma corruption detection creates `rag_repair.json` with `status="requested"` and no repair thread is started.

### Phase 2: Resource Close and CLI Repair

| # | Task | Target |
|---|------|--------|
| 2-1 | Add idempotent `ChromaVectorStore.close()` | `core/memory/rag/store.py` |
| 2-2 | Add tests proving `reset_vector_store()` calls Chroma close | `tests/unit/core/memory/` |
| 2-3 | Add top-level `repair-rag` parser registration | `cli/parser.py` |
| 2-4 | Implement `repair-rag --anima <name> --full --shared` | `cli/commands/repair_rag_cmd.py` |
| 2-5 | Add CLI success and failure tests | `tests/unit/cli/` |

**Completion condition**: `python -m cli repair-rag --anima test --full --shared` calls synchronous repair and returns the correct exit code in tests.

### Phase 3: Supervisor Repair Lifecycle

| # | Task | Target |
|---|------|--------|
| 3-1 | Add config values for repair timeout and polling interval | `core/config/schemas.py` |
| 3-2 | Add supervisor scanner for requested RAG repair state | `core/supervisor/_mgr_health.py` |
| 3-3 | Stop target anima before repair subprocess starts | `core/supervisor/_mgr_health.py` |
| 3-4 | Run repair CLI subprocess with timeout | `core/supervisor/_mgr_health.py` |
| 3-5 | Restart target anima after successful repair | `core/supervisor/_mgr_health.py` |
| 3-6 | Broadcast repair lifecycle events | `core/supervisor/_mgr_health.py` |
| 3-7 | Add unit tests for success, stop failure, repair timeout, restart failure | `tests/unit/core/supervisor/` |

**Completion condition**: A requested repair state triggers stop -> CLI repair -> restart in tests, with correct state transitions.

### Phase 4: Regression Coverage

| # | Task | Target |
|---|------|--------|
| 4-1 | Update existing RAG repair tests to expect request-only background behavior | `tests/unit/core/memory/test_rag_repair.py` |
| 4-2 | Keep index skip tests passing under repair lock | `tests/unit/cli/test_index_shared.py` |
| 4-3 | Keep daily indexing skip tests passing under repair lock | `tests/unit/core/supervisor/test_daily_indexing.py` |

**Completion condition**: RAG repair, CLI, supervisor repair, and indexing lock tests all pass.

## Scope

### In Scope

- Convert automatic RAG repair from in-process background repair to supervisor-managed stop/repair/restart.
- Add explicit `ChromaVectorStore.close()`.
- Add `repair-rag` CLI command for synchronous out-of-process repair.
- Add repair state fields needed for incident diagnosis.
- Add tests for request state, CLI repair, supervisor flow, Chroma close, timeout, and failure states.
- Preserve automatic repair behavior at the user-visible level.

### Out of Scope

- Chroma server externalization — excluded because it is a larger architecture migration.
- RAG retrieval quality changes — excluded because the issue concerns repair lifecycle safety.
- submit_tasks hook wording — excluded because it is unrelated to RAG DB repair.
- Codex CLI discovery fix — excluded because it is a separate already-identified runtime issue.
- Dashboard UI redesign — excluded because API/state correctness is the required base.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Supervisor stop/restart path mishandles an active anima | User-facing response gap for that anima | Limit stop to target anima, broadcast status, test success and failure paths. |
| Repair CLI times out after moving DB | RAG stays unavailable for that anima | Record quarantine path and stage, leave clear state for manual restore, avoid repeated repair loop. |
| State machine gets stuck in `requested` | Repair does not run | Add supervisor scanner tests and `updated_at` changes for each transition. |
| Duplicate signals start duplicate repairs | DB corruption risk | Preserve file lock and `_active_repairs`; request path keeps one active repair state. |
| `close()` behavior differs across Chroma versions | Reset may not release every resource | Treat close as best-effort hygiene; process stop and CLI isolation are the safety guarantee. |

## Acceptance Criteria

- [ ] Chroma corruption detection writes `status="requested"` to `rag_repair.json` and does not start a background repair thread.
- [ ] `request_repair(background=True)` does not call `quarantine_vectordb()` or `full_reindex()` in the current process.
- [ ] `animaworks repair-rag --anima <name> --full --shared` runs synchronous repair and returns exit code `0` on success.
- [ ] `animaworks repair-rag --anima <name> --full --shared` returns exit code `1` on repair failure and writes the error to stderr.
- [ ] Supervisor detects a requested repair, stops only the target anima, runs the repair CLI in a separate process, then restarts that anima after success.
- [ ] Repair state records `status`, `stage`, `pid`, `started_at`, `requested_at`, `updated_at`, `heartbeat_at`, `last_error`, `last_quarantine_path`, and `last_chunks_indexed`.
- [ ] `ChromaVectorStore.close()` is implemented and idempotent.
- [ ] `reset_vector_store()` closes cached `ChromaVectorStore` instances in unit tests.
- [ ] Repair lock still prevents normal indexing from opening a local vector store for the locked anima.
- [ ] Tests cover supervisor stop failure, repair CLI timeout, repair success with restart failure, and duplicate repair request suppression.

## References

- `core/memory/rag/repair_service.py:87` — Chroma error detection and repair trigger.
- `core/memory/rag/repair_service.py:175` — current request repair entrypoint.
- `core/memory/rag/repair_service.py:194` — unsafe background thread repair creation.
- `core/memory/rag/repair_service.py:275` — synchronous destructive repair method to keep for CLI.
- `core/memory/rag/repair_service.py:312` — quarantine and rebuild call site.
- `core/memory/rag/repair_rebuild.py:17` — live vectordb quarantine helper.
- `core/memory/rag/singleton.py:222` — vector store reset and optional close.
- `core/memory/rag/store.py:142` — Chroma store class requiring `close()`.
- `core/memory/rag/repair_types.py:12` — repair result type.
- `core/supervisor/_mgr_health.py:304` — restart flow already calls RAG repair before restart.
- `core/supervisor/_mgr_health.py:349` — existing supervisor RAG repair hook.
- `core/config/schemas.py:214` — current RAG repair config defaults.
- `cli/parser.py:253` — top-level command registration location.
- `cli/commands/index_cmd.py:268` — indexing skip behavior while repair lock is held.
- `tests/unit/core/memory/test_rag_repair.py:43` — repair trigger tests to update.
- `tests/unit/cli/test_index_shared.py:204` — repair-lock indexing skip regression test.
- `tests/unit/core/supervisor/test_daily_indexing.py:104` — daily indexing repair-lock skip regression test.
