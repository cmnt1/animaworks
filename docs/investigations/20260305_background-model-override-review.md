# Background Model Override — Code Review

**Date**: 2026-03-05  
**Scope**: Implementation review of `background_model` feature for heartbeat/cron cost reduction  
**Status**: Design review (implementation not yet in main)

---

## Executive Summary

The design is sound and opt-in is appropriate. Several issues require attention before merge:

- **Critical**: Model swap mutates shared `model_config`; concurrent chat can use the background model during heartbeat.
- **High**: `ConfigReader.read_model_config()` must be updated to pass `background_model`/`background_credential` (omitted in design).
- **Medium**: `_SENTINEL` type annotation is unconventional; consider a typed sentinel.
- **Low**: `update_status_model` should use atomic write (tmp + rename) like `save_config`.

---

## 1. Architecture and Design Patterns

### Strengths

- **Opt-in**: Unset = use main model; no behavior change for existing animas.
- **3-level resolution**: per-anima → `heartbeat.default_model` → None is clear.
- **Separation of concerns**: TaskExec stays on main model; only heartbeat/cron use background model.
- **Consistency**: Same swap/restore pattern for heartbeat and cron.

### Concerns

| Finding | Severity | Description |
|--------|----------|-------------|
| **Concurrent model_config mutation** | **Critical** | See Section 2 (Security/Concurrency). |
| **ConfigReader not in changed files** | **High** | `core/memory/config_reader.py` builds `ModelConfig` from `resolve_anima_config` but does not pass `background_model` or `background_credential`. `DigitalAnima` uses `memory.read_model_config()` → `ConfigReader`, so background fields would be missing unless ConfigReader is updated. |
| **Credential resolution for cross-provider** | Medium | When `background_model` uses a different provider (e.g. `openai/gpt-4.1-mini` vs main `claude-opus-4-6`), `background_credential` must resolve correctly. Ensure `resolve_anima_config` / credential lookup handles `background_credential` when present. |

---

## 2. Security and Concurrency

### Critical: Race Between Heartbeat and Chat

**Problem**: The model swap mutates `self.model_config` (shared state). Heartbeat holds `_background_lock`; chat holds `_conversation_lock`. These locks are independent, so chat and heartbeat can run concurrently.

**Scenario**:
1. Heartbeat starts, acquires `_background_lock`, swaps `model_config` to Sonnet.
2. Heartbeat calls `run_cycle_streaming` (async).
3. Event loop yields; chat request arrives.
4. Chat acquires `_conversation_lock`, calls `run_cycle_streaming` using `self.model_config`.
5. Chat uses Sonnet instead of Opus.

**Impact**: Chat sessions can incorrectly use the background model during heartbeat.

**Mitigation options**:

1. **Model lock (recommended)**: Introduce `_model_config_lock` acquired by:
   - Heartbeat: for the entire swap → cycle → restore block.
   - Chat/Inbox: at the start of `run_cycle` / `run_cycle_streaming`.
   This serializes chat and heartbeat when model is in use; acceptable for typical workloads.

2. **Override parameter**: Add `model_config_override: ModelConfig | None = None` to `run_cycle` / `run_cycle_streaming`. When set, use it for the cycle instead of mutating `model_config`. Requires plumbing through executor creation.

3. **Single lock**: Merge heartbeat and chat under one lock. Would be a larger behavioral change.

### Supervisor Tool Guarding

`set_subordinate_model` uses `_check_subordinate(target_name)`, which enforces `config.animas[target_name].supervisor == self._anima_name`. The new `set_subordinate_background_model` should follow the same pattern. **Verified**: Design states "same pattern as set_subordinate_model"; ensure `_check_subordinate` is called before any status.json write.

---

## 3. Performance

- **load_config()**: Cached with mtime check; multiple calls are cheap.
- **Double load_config in _resolve_background_config**: Not an issue; cache returns the same instance.
- **Executor rebuild**: `update_model_config()` rebuilds the executor; swap + restore causes two rebuilds per heartbeat/cron. Acceptable for 30‑minute heartbeat interval.

---

## 4. Python Best Practices and Maintainability

### `_SENTINEL = object()` Pattern

**Question**: Is it appropriate for `update_status_model`?

**Answer**: Yes, the pattern is valid. It distinguishes:
- `background_model=_SENTINEL` (default): do not touch the field.
- `background_model=None`: explicitly clear the field.
- `background_model="claude-sonnet-4-6"`: set the value.

**Type annotation**: `str | None | object` is unusual. Alternatives:

```python
# Option A: Typed sentinel (Python 3.10+)
from typing import Literal
_UNSET: Literal["__unset__"] = "__unset__"  # or use object() with type: ignore

# Option B: Explicit overloads (clearer for callers)
# Option C: Keep object() but document; add type: ignore on default
def update_status_model(
    anima_dir: Path,
    *,
    model: str | None = None,
    credential: str | None = None,
    background_model: str | None = _SENTINEL,  # type: ignore[assignment]
    background_credential: str | None = _SENTINEL,  # type: ignore[assignment]
) -> None:
```

**Recommendation**: Use `object()` with a brief comment and `# type: ignore` if needed. Avoid `str | None | object` in the public signature.

### Finally Block Safety

**Question**: Is the model swap/restore via `finally` safe under all edge cases?

**Answer**: Yes for normal execution and exceptions. `finally` runs on:
- Normal completion
- Exception propagation
- `return` from the `try` block

**Edge cases**:
- **Session chaining**: If the cycle triggers session chaining (Mode A context overflow), the chained continuation uses the same executor, which was built from the swapped config. So the chained session correctly uses the background model. Restore still runs after the full cycle.
- **Cancellation**: If the task is cancelled (`asyncio.CancelledError`), `finally` runs. Restore will execute.
- **Process kill**: If the process is killed, restore does not run. On restart, `read_model_config()` reloads from status.json, which is unchanged. Safe.

### Atomic Writes

`update_status_model` currently does:
```python
tmp.write_text(...)
tmp.replace(status_path)
```
This is atomic. Ensure the same pattern is used when writing `background_model` / `background_credential` (i.e. no direct `status_path.write_text()` without tmp).

---

## 5. Regression Risk

### Existing Features

| Area | Risk | Notes |
|------|------|-------|
| Chat | **High** | Concurrent chat can use background model (see Section 2). |
| Inbox | **High** | Same as chat. |
| TaskExec | None | Correctly excluded; uses main model. |
| Consolidation | Low | Uses its own `llm_model` from `ConsolidationConfig`; not affected. |
| Config hot-reload | Low | `reload_config()` reads fresh config; if `background_model` is in status.json, it will be picked up. Ensure `ModelConfig.model_fields` includes new fields for the diff in `reload_config()`. |

### `resolve_anima_config` and `AnimaDefaults`

Adding `background_model` and `background_credential` to `AnimaDefaults` is backward compatible. Old configs omit these keys; Pydantic uses `None`. Ensure `_load_status_json` includes them in `field_mapping` and that `_nullable_fields` does not need to include them (they use empty-string / missing as "not set").

---

## 6. API / Interface Backward Compatibility

| Change | Compatible? |
|--------|-------------|
| `AnimaDefaults.background_model`, `background_credential` | Yes (default `None`) |
| `HeartbeatConfig.default_model` | Yes (default `None`) |
| `ModelConfig.background_model`, `background_credential` | Yes (default `None`) |
| `status.json` new keys | Yes (extra keys ignored by older code) |
| `update_status_model` new params | Yes (keyword-only, optional) |
| New supervisor tool | Yes (additive) |
| New CLI subcommand | Yes (additive) |

---

## 7. Specific Review Questions — Answers

### Q1: Is `_SENTINEL = object()` appropriate for `update_status_model`?

**Yes.** It correctly distinguishes "not provided" from "clear". Prefer a short comment and optional `# type: ignore` over `str | None | object` in the signature.

### Q2: Is the model swap/restore via `finally` safe under all edge cases?

**Yes** for exceptions, cancellation, and session chaining. **No** for concurrency: chat can run during heartbeat and see the swapped config. Add a model lock or use an override parameter.

### Q3: Could `_resolve_background_config` cause issues with double `load_config()` calls?

**No.** `load_config()` is cached; repeated calls return the cached instance. No performance or correctness issue.

### Q4: Is the new supervisor tool properly guarded against non-subordinate access?

**Yes**, if it follows `set_subordinate_model` and calls `_check_subordinate(target_name)` before any status.json write. Confirm the handler does this.

### Q5: Any backward compatibility concerns with AnimaDefaults/ModelConfig field additions?

**No.** Optional fields with default `None` are backward compatible. Existing config.json and status.json files continue to work.

---

## 8. Recommendations Summary

| Priority | Action |
|----------|--------|
| **Critical** | Add `_model_config_lock` (or equivalent) so chat and heartbeat do not run with inconsistent model_config, or implement `model_config_override` in `run_cycle` and avoid mutating shared state. |
| **High** | Update `ConfigReader.read_model_config()` to pass `background_model` and `background_credential` into `ModelConfig`, and ensure `mode_s_auth` is included if it is in `load_model_config`. |
| **Medium** | Document the `_SENTINEL` usage and consider a typed sentinel or overloads for clearer typing. |
| **Low** | Confirm `update_status_model` uses atomic write (tmp + rename) for all status.json updates. |
| **Low** | Add a unit test for the heartbeat+chat concurrency scenario (with model lock or override in place). |

---

## Appendix: Files to Update (Design Completeness)

The design lists 13 changed files. Ensure these are also updated:

- `core/memory/config_reader.py` — add `background_model`, `background_credential` (and `mode_s_auth` if missing) to `ModelConfig()` construction in `read_model_config()`.
