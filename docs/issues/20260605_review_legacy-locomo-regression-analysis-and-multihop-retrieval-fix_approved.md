# Review: Legacy LoCoMo Regression Analysis and Multi-Hop Retrieval Fix

## Status

APPROVED

## Scope Reviewed

- Issue: `docs/issues/20260604_legacy-locomo-regression-analysis-and-multihop-retrieval-fix.md`
- Worktree: `/home/main/dev/animaworks-bak-issue-20260604-235934`
- Branch: `issue-20260604-235934`
- Base: `main`
- Commits: `98d74630`, `9bec2904`, `ed7ae7a9`

## Findings

No blocking issues were found in the implementation diff.

### Requirement Alignment

Pass.

- Added `benchmarks/locomo/compare_results.py` for before/after JSON comparison, cat5-excluded metrics, blank counts, and per-question regression/improvement reports.
- Added answer timeout, answer retry, checkpoint, and max-question controls to the LoCoMo runner/adapter.
- Added feature-on retrieval diagnostics with combined fact/entity/entity-aware graph ablation and per-question deltas.
- Fixed LoCoMo fact indexing so generated fact memories are written as indexable JSONL while preserving markdown/BM25 compatibility.
- Tightened category 1 entity boost to avoid generic content-token overlap.
- Neo4j adapter was not changed.

### Test Coverage

Partial but acceptable for this change.

- Targeted suite: `96 passed, 2 warnings`.
- Targeted module coverage:
  - `benchmarks.locomo.compare_results`: 96%
  - `benchmarks.locomo.fact_index`: 82%
  - `core.memory.retrieval.entity`: 91%
  - Aggregate targeted coverage is 57% because large pre-existing modules (`adapter.py`, `runner.py`, `retrieval_diagnostics.py`) contain substantial untested legacy surface outside this change.
- Full coverage checker was stopped because it launched repo-wide pytest coverage and exceeded practical review runtime.

### E2E / LoCoMo Verification

Pass for change-specific checks.

- LoCoMo retrieval diagnostics:
  - Command: `python3 -m benchmarks.locomo.retrieval_diagnostics --mode scope_all --conversations 1 --top-k 10 --ceiling-top-k 10 --feature-on-ablation --output /tmp/legacy-locomo-feature-on-diagnostics-fixed`
  - Result: errors=0
  - Output: `/tmp/legacy-locomo-feature-on-diagnostics-fixed/2026-06-05T00-34-16_scope_all_retrieval_diagnostics.json`
  - Feature-on recall@10 delta: overall +0.0643, multi_hop +0.0960, open_domain +0.0853, complex +0.0841, temporal -0.0099.
- LoCoMo compare CLI:
  - Command: `python3 -m benchmarks.locomo.compare_results ... --output /tmp/legacy-locomo-compare-report.json --markdown /tmp/legacy-locomo-compare-report.md`
  - Result: success; common questions=199; cat5-excluded F1 delta +0.0088.
- Live LoCoMo smoke:
  - Included in targeted suite with `max_questions=5`.
  - Result: pass.

### Regression Checks

Pass with one pre-existing repo E2E failure.

- `pytest -m e2e -v` result: 174 passed, 1 failed, 2 skipped.
- The failing test was `tests/e2e/core/test_legacy_entity_index_boost_e2e.py::test_fact_ingest_updates_entity_registry_and_boosts_metadata_candidates`.
- The same test fails on `main` with the same assertion, so it is not introduced by this branch.
- `git diff --check main...HEAD`: pass.

### File Size

Partial, non-blocking.

- Repo-wide file-size checker fails on many pre-existing oversized files.
- Newly added `benchmarks/locomo/compare_results.py` is 302 lines and under the limit.
- Touched legacy LoCoMo files were already large; this change keeps edits localized and does not introduce a new oversized file.

### Independent Reviews

- Cursor Agent review: launched but produced empty stdout/log; treated as unavailable.
- Codex subagent review: skipped due environment tool policy requiring explicit user authorization for subagent spawning.

## Required Changes

None.

## Residual Risks

- Full live LoCoMo answer F1 remains provider-latency sensitive; the new timeout/retry/checkpoint controls mitigate this but do not remove external variance.
- Repo-wide coverage/file-size gates remain noisy because they include broad pre-existing debt unrelated to this issue.
- The pre-existing `test_legacy_entity_index_boost_e2e` failure should be handled separately.
