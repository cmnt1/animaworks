# Code Review: Neo4j ToolHandler Loop Isolation - Approved

**Review Date**: 2026-05-14
**Original Issue**: `docs/issues/20260514_neo4j-toolhandler-loop-isolation.md`
**Worktree**: `/home/main/dev/animaworks-bak-issue-20260514-131338`
**Status**: APPROVED

## Summary

Implementation passed review. `_search_via_neo4j()` now creates a fresh Neo4j backend per ToolHandler search, executes `retrieve()`, and closes the backend within the same async lifecycle. Legacy-only scopes and fallback behavior are preserved.

## Metrics

- Requirement Alignment: Complete
- Test Coverage: Targeted ToolHandler lifecycle tests added; global coverage tool unavailable because `pytest-cov` is not installed
- Code Quality: No blocking issues
- SRP Compliance: Changes scoped to ToolHandler Neo4j lifecycle and its focused tests
- File Sizes: Existing repository-wide file-size check fails on many pre-existing large files; touched test file is within limit, touched handler file was already over 500 lines
- E2E Tests: `tests/e2e/test_sakura_neo4j_memory_recovery_e2e.py` passed
- Regression: Targeted tests passed; full suite collection fails on main and worktree due to missing `botocore`

## Verification

- `python3 -m pytest -q tests/unit/core/memory/test_search_memory_neo4j.py` -> 20 passed
- `python3 -m pytest -q tests/unit/core/memory/test_search_memory_neo4j.py tests/e2e/test_sakura_neo4j_memory_recovery_e2e.py` -> 22 passed
- `python3 -m pytest -m e2e -q tests/e2e/test_sakura_neo4j_memory_recovery_e2e.py` -> 2 passed
- Sakura live read-only check: two consecutive ToolHandler Neo4j graph searches returned graph results without event-loop Future errors
- `git diff --check` -> passed
- `python3 -m compileall -q core/tooling/handler_memory.py tests/unit/core/memory/test_search_memory_neo4j.py` -> passed

## Independent Reviews

- Cursor Agent Review: APPROVED
  - Medium note: `_should_use_neo4j()` now calls `resolve_backend_type()` and may add small per-search file I/O.
  - Medium note: defensive close handling is slightly more complex than `await backend.close()`.
- Codex Subagent Review: APPROVED
  - Residual note: active-event-loop threadpool branch is not directly covered by a dedicated test.
  - Residual note: per-search backend creation can add connection latency, which the issue accepted as a tradeoff.

## Residual Risks

- Full repository pytest cannot complete in the current environment because `botocore` is missing; the same collection error reproduces on `main`.
- Repository-wide file-size and coverage gate results are not actionable for this focused change because they fail on pre-existing project state.

---

No revision required.
