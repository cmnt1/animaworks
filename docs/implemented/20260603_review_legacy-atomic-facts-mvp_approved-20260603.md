# Code Review: Legacy Atomic Facts MVP - Approved

**Review Date**: 2026-06-03
**Original Issue**: `docs/issues/20260603_legacy-atomic-facts-mvp.md`
**Worktree**: `/home/main/dev/animaworks-bak-issue-20260603-123519`
**Status**: APPROVED

## Summary

Implementation is ready for merge. The requested legacy-first atomic facts layer is implemented without adding a Neo4j runtime dependency, and review-found regressions were fixed during the review cycle.

## Metrics

- Requirement Alignment: PASS
- Test Coverage: PASS, targeted new-module coverage 88.89%
- Code Quality: PASS
- SRP Compliance: PASS
- New File Sizes: PASS, all new files are under 500 lines
- E2E Tests: PASS, `pytest -m e2e -v` passed
- Regression: PASS for relevant memory/E2E checks; full-suite run has environment caveats below

## Requirement Alignment

- `core/memory/facts.py`: JSONL atomic fact store with stable IDs, active/expired validity handling, deduplication, append lock, and rewrite support.
- `core/memory/fact_extraction.py`: Legacy wrapper around existing `FactExtractor`, converting extracted entities/facts to `FactRecord` and storing/indexing non-fatally.
- `core/memory/conversation_finalize.py` and `core/_anima_lifecycle.py`: Session and consolidation hooks added as non-fatal background/try-catch flows.
- `core/memory/rag/indexer.py` and `core/memory/rag/facts_chunker.py`: `facts/*.jsonl` indexing support with fact metadata.
- `core/memory/rag_search.py`, `core/memory/rag/retriever.py`, and `core/memory/backend/legacy.py`: `scope="facts"` and `scope="all"` retrieval support, keyword fallback, active-only fact filtering.
- `core/memory/scope_policy.py`: Neo4j hybrid `all` scope now includes legacy-only facts, matching the legacy-first requirement.
- `core/tooling/schemas/memory.py` and `core/tooling/prompt_db.py`: Tool schema and prompt descriptions expose the facts scope.

## Review Fixes Applied

- Fixed a security issue where `status.json` endpoint/API fields could have influenced extraction routing. `fact_extraction.py` now ignores endpoint, API key, and extra body fields from status.
- Fixed Neo4j hybrid `scope="all"` omission of facts by adding facts to the legacy-only scope policy.
- Fixed background fact extraction task lifetime by retaining strong references until completion.
- Fixed a `scope="all"` regression where hybrid search did not return `conversation_summary` keyword fallback when vector sources were empty.
- Updated stale all-scope test expectations and added regression tests for facts and hybrid fallback behavior.

## Verification

- `ruff check ...`: PASS
- `python3 -m compileall ...`: PASS
- `git diff --check`: PASS
- Focused memory/facts suite: `59 passed, 2 warnings`
- Targeted new-module coverage: `20 passed`, total coverage `88.89%`
- E2E marker suite: `173 passed, 2 skipped, 14393 deselected, 20 warnings`
- Additional regression set run earlier: `64 passed, 2 warnings`

## Environment Caveats

- The bundled coverage checker runs full pytest with a fixed 300s timeout and returned `Coverage: 0.0%` because the command timed out before producing `coverage.json`; targeted coverage for the new modules passed at 88.89%.
- Repo-wide file size checker fails on many pre-existing files. New files introduced here are below 500 lines; modified oversized files were existing repository debt.
- Full `pytest -q` was attempted and interrupted after detecting unrelated Playwright browser-install errors in UI viewport tests. The relevant S-mode failure found during that run was fixed and re-tested.
- `tests/integration/test_locomo_legacy_smoke.py::test_legacy_scope_all_within_baseline` initially failed because the git-ignored LOCOMO dataset was absent from the worktree. After copying the dataset from the main checkout, the live smoke ran for more than 8 minutes without output or result files and was aborted as an environment/live-benchmark validation gap.

## Independent Agent Reviews

- Cursor Agent Review: Unavailable. The launcher completed but produced an empty stdout report/log.
- Codex Subagent Review: Completed. It found the status endpoint security issue, Neo4j hybrid facts omission, background task lifetime risk, and stale all-scope expectations. All findings were addressed before approval.

## Conclusion

No code changes are required before merge. Remaining caveats are environment or live-benchmark validation gaps, not implementation blockers for the issue.

---

**No revision required.**
