# Code Review: Agent SDK Close Patch SDK Drift - Approved

**Review Date**: 2026-05-14
**Original Issue**: `docs/issues/20260514_agent-sdk-close-patch-sdk-drift.md`
**Worktree**: `/home/main/dev/animaworks-bak-issue-20260514-140032`
**Status**: APPROVED

## Summary

Implementation is approved. The diff is limited to `core/execution/_sdk_patch.py` and a focused new test module. It implements SDK close feature detection, skips the close monkey patch when the installed SDK already performs graceful teardown, keeps the guarded legacy patch for older SDK layouts, and gates the Windows query patch when the SDK method is absent.

## Metrics

- Requirement Alignment: Complete
- Code Quality: Pass
- SRP Compliance: Pass
- Changed File Sizes: Pass (`core/execution/_sdk_patch.py` 263 lines, `tests/unit/execution/test_sdk_patch.py` 270 lines)
- E2E Tests: Pass for marker-selected E2E set after excluding environment-missing `botocore` collection file
- Regression: No changed-diff regression found

## Verification

- `python3 -m compileall -q core/execution/_sdk_patch.py tests/unit/execution/test_sdk_patch.py`: pass
- `git diff --check main...HEAD`: pass
- `python3 -m pytest -q tests/unit/execution/test_sdk_patch.py`: 8 passed
- `python3 -m pytest -q tests/unit/execution/test_sdk_patch.py tests/unit/execution/test_agent_sdk.py tests/unit/execution/test_agent_sdk_resume_timeout.py tests/unit/test_sdk_process_cleanup.py`: 80 passed
- `python3 -m pytest -m e2e -v --tb=short --ignore=tests/unit/tools/test_aws_collector.py`: 149 passed, 2 skipped
- Fresh import check: `core.execution.agent_sdk` preserves SDK 0.1.81 native `SubprocessCLITransport.close`

## Environment Notes

- Full `python3 -m pytest --tb=short -q` cannot pass in the current environment because both main and the worktree fail collection on missing `botocore` in `tests/unit/tools/test_aws_collector.py`.
- Full suite with `--ignore=tests/unit/tools/test_aws_collector.py` completed with `13797 passed`, plus failures/errors in unrelated existing areas:
  - 30 Playwright browser setup errors because the Chromium headless shell is not installed.
  - 6 failures outside the changed files: asset reconciliation, skill creator content, common knowledge watcher, and watcher tests.
- `coverage_checker.py` could not produce valid coverage because `pytest-cov` is not installed in this runtime.
- Global file-size checker reports many pre-existing oversized files. The changed files are within the 500-line / 100KB review threshold.

## Independent Reviews

- Codex subagent review: Completed, no findings. Residual risks noted: legacy SDK is tested with fake SDK modules rather than a real SDK 0.1.44 environment; post-restart Sakura log verification is not exercised in unit tests.
- Cursor Agent review: Failed/unavailable; launcher created empty output/log files and produced no review body.

## Residual Risk

- The SDK graceful-close detector is source-string based. This is acceptable for this patch because a false negative falls back to the guarded legacy patch, and the installed SDK 0.1.81 path is explicitly tested.
- Sakura process restart/log verification remains an operational acceptance check after merge.

## Decision

APPROVED. No revision required.
