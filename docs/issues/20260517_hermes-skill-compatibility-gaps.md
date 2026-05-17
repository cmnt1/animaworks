# Hermes Skill Compatibility Gaps — Fix legacy flat skill loading and skill-creator guidance

## Overview

The Hermes skill management implementation mostly works after server restart and focused execution checks, but two compatibility gaps remain. This issue fixes both gaps so Issue `20260506_01_hermes-skill-loader-index` and the skill-creator specification are actually satisfied.

## Problem / Background

### Current State

- `load_skill_metadata()` can parse a legacy personal flat skill file such as `skills/foo.md`, but `SkillIndex` does not include it in the catalog.
- `read_memory_file(path="skills/foo.md")` can read the file, but the skill access gate and view usage tracking do not run because `_is_skill_path()` only recognizes paths containing `SKILL.md`.
- Japanese `skill-creator` template mentions `write_memory_file`, but the regression test expects it to explicitly say the flat `skills/foo.md` creation path is deprecated or cannot be referenced through the canonical `skills/foo/SKILL.md` path.

### Root Cause

1. Personal skill indexing only scans directory-format skills: `core/skills/index.py:95`.
2. Memory tool skill detection and view tracking only treat `skills/*/SKILL.md`, `common_skills/**/SKILL.md`, and `procedures/*.md` as skill-like paths: `core/tooling/handler_memory.py:538`.
3. The Japanese skill-creator template describes the limitation, but does not include the required explicit Japanese wording checked by `tests/test_skill_creator_spec_fixes.py:250`.

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/skills/index.py` | Direct | Legacy `skills/*.md` personal skills are omitted from catalog, search, routing, cron/goal skill reference resolution, and curator views. |
| `core/tooling/handler_memory.py` | Direct | Reading `skills/foo.md` bypasses skill access decisions and does not record `SkillUsageEventType.view`. |
| `templates/ja/common_skills/skill-creator/SKILL.md` | Direct | Existing regression test fails and the template guidance is less explicit than intended. |
| `tests/unit/test_skills_index.py` | Direct | Needs coverage for flat personal skill indexing and blocked/quarantine exclusion. |
| `tests/unit/test_skill_curator.py` or handler tests | Direct | Needs coverage that flat personal skills are gated and view-tracked. |

## Decided Approach / 確定方針

### Design Decision

確定: legacy support is limited to direct-child personal files matching `skills/*.md`. The canonical and newly-created format remains `skills/{name}/SKILL.md`. This keeps backward compatibility for existing flat skills while avoiding accidental indexing of nested support Markdown files such as `skills/foo/references/bar.md`.

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| A: Convert flat files to directories automatically | Cleans the runtime shape | Mutates user memory files unexpectedly and can break links or history | **Rejected**: migration must be explicit, not hidden in a loader. |
| B: Index every Markdown file under `skills/` recursively | Simple implementation | Would treat references/templates/docs as runnable skills | **Rejected**: too broad and unsafe. |
| **C: Direct-child `skills/*.md` only (Adopted)** | Satisfies documented compatibility without broad false positives | Leaves nested support Markdown non-skill, by design | **Adopted**: precise compatibility boundary and low regression risk. |

### Key Decisions

1. **Flat personal skills are loadable/indexed**: `SkillIndex` scans `skills/*.md` in addition to `skills/*/SKILL.md` — Reason: Issue 01 acceptance criterion requires legacy flat skill compatibility.
2. **Flat personal skills are gated on read**: `read_memory_file("skills/foo.md")` must call `skill_access_decision()` — Reason: blocked/quarantine/dangerous policy must not be bypassed.
3. **Flat personal skill view events use `Path(rel).stem`**: reading `skills/foo.md` records usage for `foo` — Reason: the file stem is the inferred legacy skill name.
4. **No recursive Markdown skill detection**: nested files under skill directories are not skill entries unless they are canonical `SKILL.md` — Reason: references/templates are Level 3 material, not separate skills.
5. **Template wording is explicit**: add `非推奨` to the Japanese `write_memory_file` flat skill note — Reason: it documents the chosen canonical path and satisfies the regression test.

### Changes by Module

| Module | Change Type | Description |
|--------|-------------|-------------|
| `core/skills/index.py` | Modify | Add direct-child `skills/*.md` scanning before/after directory `SKILL.md` scanning with existing dedupe. Mark as personal non-procedure. |
| `core/tooling/handler_memory.py` | Modify | Recognize exactly `skills/*.md` as skill path, apply access gate, and record view events using the file stem. |
| `templates/ja/common_skills/skill-creator/SKILL.md` | Modify | Mark `write_memory_file` flat skill creation as `非推奨` while preserving `create_skill` as canonical. |
| `tests/unit/test_skills_index.py` | Modify | Add tests for direct-child flat personal skill indexing and blocked/quarantine exclusion. |
| `tests/unit/test_skill_curator.py` or `tests/unit/core/tooling/test_handler_skills_task.py` | Modify | Add coverage for flat personal skill read gating and view usage. |

### Edge Cases

| Case | Handling |
|------|----------|
| `skills/foo.md` has no frontmatter | Name inferred as `foo`; description falls back to `## 概要` as `load_skill_metadata()` already does. |
| `skills/foo.md` has `trust_level: blocked` | Excluded from `SkillIndex` and blocked by `read_memory_file`. |
| `skills/foo.md` has `trust_level: quarantine` | Excluded from `SkillIndex` and blocked by `read_memory_file`. |
| `skills/foo/references/bar.md` | Not treated as a skill; no skill access gate or usage event. |
| `skills/foo/SKILL.md` | Existing behavior unchanged. |
| Common skills | Existing `common_skills/*/SKILL.md` and `common_skills/*/*/SKILL.md` behavior unchanged. |

## Implementation Plan

### Phase 1: Loader/index compatibility

| # | Task | Target |
|---|------|--------|
| 1-1 | Add `skills/*.md` scanning to personal `SkillIndex` path collection. | `core/skills/index.py` |
| 1-2 | Add unit tests for indexed flat skills and blocked/quarantine exclusion. | `tests/unit/test_skills_index.py` |

**Completion condition**: `SkillIndex(...).all_skills` includes safe flat personal skills and excludes blocked/quarantine flat personal skills.

### Phase 2: Access gate and usage tracking

| # | Task | Target |
|---|------|--------|
| 2-1 | Add exact direct-child flat personal skill path detection. | `core/tooling/handler_memory.py` |
| 2-2 | Record view usage for `skills/foo.md` as `foo`. | `core/tooling/handler_memory.py` |
| 2-3 | Add regression test for read gate and view tracking. | `tests/unit/test_skill_curator.py` or a focused handler test |

**Completion condition**: `read_memory_file("skills/foo.md")` blocks unloadable flat skills and records one debounced view for loadable flat skills.

### Phase 3: Template wording and regression tests

| # | Task | Target |
|---|------|--------|
| 3-1 | Add explicit `非推奨` wording to Japanese skill-creator flat `write_memory_file` warning. | `templates/ja/common_skills/skill-creator/SKILL.md` |
| 3-2 | Run the prior failing spec test and Hermes skill focused tests. | tests |

**Completion condition**: `tests/test_skill_creator_spec_fixes.py::TestJapaneseSkillCreatorContent::test_write_memory_file_deprecated` passes.

## Scope

### In Scope

- Legacy direct-child personal `skills/*.md` indexing.
- Legacy direct-child personal `skills/*.md` read access gate.
- View usage tracking for direct-child personal `skills/*.md`.
- Japanese skill-creator wording fix.
- Focused unit/E2E regression tests.

### Out of Scope

- Automatic migration from `skills/foo.md` to `skills/foo/SKILL.md` — Reason: this mutates user memory and should be a separate explicit migration.
- Recursive indexing of nested Markdown under skill directories — Reason: references/templates are not skills.
- Changing canonical `create_skill` output — Reason: directory-format `SKILL.md` remains the standard.
- Common flat Markdown skills — Reason: documented common layout is `common_skills/{category?}/{name}/SKILL.md`, not direct `common_skills/foo.md`.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Accidental indexing of support Markdown | Medium | Only scan direct-child `skills/*.md`, not recursive Markdown. |
| Duplicate skill names between `skills/foo.md` and `skills/foo/SKILL.md` | Low | Existing path-level dedupe remains; catalog may contain both if both files exist. Do not silently choose one in this issue. |
| Access gate false positives | Low | Exact path shape check: `Path(rel).parts == ("skills", "<name>.md")`. |
| Template wording drift | Low | Keep wording minimal and test-backed. |

## Acceptance Criteria

- [ ] `SkillIndex` includes a safe legacy `skills/flat-skill.md` personal skill.
- [ ] `SkillIndex` excludes legacy flat personal skills with `trust_level: blocked` or `trust_level: quarantine`.
- [ ] `read_memory_file(path="skills/flat-skill.md")` applies the same `skill_access_decision()` gate as `skills/flat-skill/SKILL.md`.
- [ ] Reading an allowed `skills/flat-skill.md` records a debounced `view` event for `flat-skill`.
- [ ] Nested files like `skills/flat-skill/references/note.md` are not treated as separate skills.
- [ ] Japanese `skill-creator` template explicitly marks `write_memory_file` flat `skills/foo.md` creation as `非推奨` or otherwise states it cannot be referenced canonically.
- [ ] Focused Hermes skill tests and the previously failing skill-creator test pass.

## References

- `docs/implemented/20260506_01_hermes-skill-loader-index_implemented-20260508:191` — legacy `skills/*.md` compatibility requirement.
- `docs/implemented/20260506_01_hermes-skill-loader-index_implemented-20260508:218` — acceptance criterion for flat skill compatibility.
- `core/skills/index.py:95` — current personal scan only covers `*/SKILL.md`.
- `core/tooling/handler_memory.py:538` — current skill path detection only recognizes `SKILL.md`.
- `tests/test_skill_creator_spec_fixes.py:250` — failing wording assertion.
