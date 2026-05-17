# create_skill Usage Event Locale Bug — Record create events independent of localized text

## Overview

Hermes Issue 2 requires `create_skill` completion to append a `create` event to `{anima_dir}/state/skill_usage.jsonl`. The current handler tries to infer success from localized return text, so Japanese runtime output skips the usage event even though the skill is created successfully.

## Problem / Background

### Current State

- `create_skill` successfully creates `skills/{name}/SKILL.md`.
- `read_memory_file` records `view` events correctly.
- `report_procedure_outcome(path="skills/{name}/SKILL.md")` records `success` / `failure` events correctly.
- `create_skill` does **not** record `create` events under Japanese locale.

Observed with a temporary `hermes_probe` Anima:

```json
{
  "skill_name": "usage-probe",
  "view_count": 1,
  "success_count": 1,
  "create_count": 0
}
```

Relevant code:

- `core/tooling/handler_skills.py:294` calls `create_skill_directory()`.
- `core/tooling/handler_skills.py:309` records usage only when the localized result contains `"Created skill"` or `"スキル作成"`.
- `core/i18n/strings/misc.py:447` Japanese success text is `"スキル '{skill_name}' を作成しました..."`, which does not contain `"スキル作成"`.
- `docs/implemented/20260506_02_skill-usage-tracking_implemented-20260508.md:104` requires `create_skill` completion to record `create`.

### Root Cause

1. Success detection is string-based and locale-dependent in `core/tooling/handler_skills.py:309`.
2. The Japanese success string changed/exists in a grammatically natural form that the substring check does not match.

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/tooling/handler_skills.py` | Direct | `create_skill` skips `SkillUsageEventType.create` under Japanese output. |
| `core/skills/usage.py` | Indirect | Usage replay is correct, but it never receives the missing create event. |
| Skill Curator / promotion metrics | Indirect | Newly created skills can appear as never-created in usage stats. |

## Decided Approach / 確定方針

### Design Decision

確定: `create_skill` success must be determined structurally, not by localized output text. `_handle_create_skill()` already validates required fields before calling `create_skill_directory()`, and `create_skill_directory()` returns an error string only for invalid names. Therefore the handler will record `SkillUsageEventType.create` when the expected `SKILL.md` exists after `create_skill_directory()` returns, rather than matching English/Japanese text.

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| A: Add `"スキル '"` or `"作成しました"` to substring checks | Small diff | Still locale/text fragile and can break on future copy changes | **Rejected**: repeats the root cause. |
| B: Change i18n Japanese string to contain `"スキル作成"` | Makes current check pass | Degrades natural Japanese text and keeps logic coupled to presentation | **Rejected**: presentation text should not drive behavior. |
| **C: Check created `SKILL.md` existence (Adopted)** | Locale-independent, verifies actual filesystem side effect | Needs one small helper/local variable | **Adopted**: structural success is the correct signal. |

### Key Decisions

1. **Record create after filesystem success**: Use `base_dir / skill_name / "SKILL.md"` existence as the success condition — Reason: this is the artifact `create_skill` promises to create.
2. **Do not record create for invalid names**: If `create_skill_directory()` returns without creating `SKILL.md`, no create event is recorded — Reason: failed creation must not affect usage stats.
3. **Keep scan behavior unchanged**: Security scan remains after create-event recording, matching existing flow — Reason: this issue only fixes missing usage event recording.
4. **Add handler-level regression coverage**: Test through `ToolHandler.handle("create_skill", ...)`, not only direct `SkillUsageTracker` — Reason: the bug is in integration logic.

### Changes by Module

| Module | Change Type | Description |
|--------|-------------|-------------|
| `core/tooling/handler_skills.py` | Modify | Replace localized success-string check with `SKILL.md` existence check before recording `create`. |
| `tests/unit/test_skills_usage_integration.py` or focused handler test | Modify | Add regression test that `create_skill` records `create_count == 1` under current locale/output. |

## Edge Cases

| Case | Handling |
|------|----------|
| Valid personal skill | `skills/{name}/SKILL.md` exists; record `create` with `is_common=False`. |
| Valid common skill | `common_skills/{name}/SKILL.md` exists; record `create` with `is_common=True`. |
| Invalid skill name such as `../evil` | `SKILL.md` does not exist; no create event is recorded. |
| Security scanner later warns or blocks | Keep existing scan behavior; create event still reflects artifact creation if the skill file exists. |
| Localized output text changes | No behavioral impact because usage event no longer depends on output text. |

## Implementation Plan

### Phase 1: Fix create success detection

| # | Task | Target |
|---|------|--------|
| 1-1 | Compute `skill_dir` / `skill_md` from `base_dir` and `skill_name`. | `core/tooling/handler_skills.py` |
| 1-2 | Record `SkillUsageEventType.create` when `skill_md.exists()` is true. | `core/tooling/handler_skills.py` |
| 1-3 | Reuse `skill_dir` for `_scan_created_skill()` to avoid recomputing paths. | `core/tooling/handler_skills.py` |

**Completion condition**: `create_skill` records exactly one create event for a newly created skill in Japanese runtime output.

### Phase 2: Regression tests

| # | Task | Target |
|---|------|--------|
| 2-1 | Add a ToolHandler integration test for valid `create_skill` usage event recording. | tests |
| 2-2 | Add/verify invalid-name path does not record create. | tests |

**Completion condition**: Focused usage and skill-handler tests pass.

## Scope

### In Scope

- Locale-independent create usage event recording.
- Handler-level regression tests for `create_skill` usage tracking.
- Focused Hermes skill usage test execution.

### Out of Scope

- Adding `patch` event detection for skill overwrite — Reason: Issue 2 mentions it, but this bug report is specifically about the observed `create` event miss.
- Changing i18n copy — Reason: behavior should not depend on localized copy.
- Refactoring `create_skill_directory()` return type — Reason: filesystem success check is sufficient and lower risk.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Duplicate create events on overwrite | Low | Existing behavior already allows overwriting; this issue only preserves one event per successful `create_skill` call. |
| False create on partial write | Low | Require actual `SKILL.md` existence after helper returns. |
| Common skill path mismatch | Low | Use same `base_dir` chosen by existing location logic. |

## Acceptance Criteria

- [ ] `ToolHandler.handle("create_skill", ...)` creates `skills/{name}/SKILL.md`.
- [ ] The same call appends a `create` event to `state/skill_usage.jsonl`.
- [ ] `SkillUsageTracker(...).get_stats(name).create_count == 1` after valid `create_skill`.
- [ ] Invalid `skill_name` does not append a create event.
- [ ] Existing `view`, `success`, `failure`, and cron `use` usage tests still pass.
- [ ] Focused Hermes skill regression suite still passes.

## References

- `core/tooling/handler_skills.py:294` — create helper call.
- `core/tooling/handler_skills.py:309` — locale-dependent success check causing the bug.
- `core/i18n/strings/misc.py:447` — Japanese success string that does not match the check.
- `docs/implemented/20260506_02_skill-usage-tracking_implemented-20260508.md:104` — `create_skill` must record `create`.
