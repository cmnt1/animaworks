# Review: Shadow Skill Router Evaluation

Status: APPROVED
Date: 2026-05-14
Worktree: `/home/main/dev/animaworks-bak-issue-20260514-170354`
Issue: `docs/issues/20260514_shadow-skill-router-evaluation.md`
Commit: `64297418`

## Summary

The implementation satisfies the issue scope: it adds a shadow-only skill router, routing metadata schema, offline evaluation CLI, gold fixture, and focused tests without changing production prompt builder behavior.

## Review Dimensions

| Dimension | Status | Notes |
|-----------|--------|-------|
| Requirement alignment | Pass | `SkillRouter`, metadata schema, `--cases` CLI alias, JSON/text metrics, metadata gap details, and no-skill metrics are implemented. |
| Test coverage | Pass | Focused coverage run reached 86.77% total over `core.skills.models`, `core.skills.router`, and `scripts.evaluate_skill_router`. |
| Code quality | Pass | Router is self-contained, dependency-light, shadow-only, and returns pointer/reason structures. |
| SRP | Pass | Router, evaluation CLI, fixture, and tests are separated. |
| File size | Pass | Largest changed file: `core/skills/router.py` at 485 lines / 17.0 KB. |
| E2E | Pass with environment note | Focused prompt/skill E2E passed. Full `pytest -m e2e` collection is blocked by missing optional `botocore`, also reproducible on `main`. |
| Regression | Pass | Existing skill loader/model, prompt builder, skill injection E2E, and legacy skill matcher tests passed. |

## Independent Reviews

- Cursor Agent: launched, process exited, but `.worktree-review/cursor_review_20260514_171547.md` and log were empty. Recorded as unavailable.
- Codex subagent: found 1 high, 2 medium, and 1 low issue. All were addressed:
  - Added real `no_skill_precision`.
  - Added metadata gap detail categories including `matched_by_fallback_only` and `no_matching_signal`.
  - Capped lexical-only high confidence.
  - Prevented dense score name lookup from attaching to duplicate skill names.

## Validation

Commands run:

```bash
ruff check core/skills/models.py core/skills/router.py scripts/evaluate_skill_router.py tests/unit/test_skill_router.py
python3 -m py_compile core/skills/models.py core/skills/router.py scripts/evaluate_skill_router.py tests/unit/test_skill_router.py
pytest tests/unit/test_skill_router.py tests/unit/test_skills_models.py tests/unit/test_skills_loader.py tests/unit/core/prompt/test_builder.py tests/e2e/test_skill_injection_e2e.py tests/unit/core/memory/test_skill_meta.py -q
/tmp/animaworks-skill-router-cov/bin/python -m pytest tests/unit/test_skill_router.py tests/unit/test_skills_models.py tests/unit/test_skills_loader.py --cov=core.skills.models --cov=core.skills.router --cov=scripts.evaluate_skill_router --cov-report=term-missing --cov-fail-under=80 -q
python3 scripts/evaluate_skill_router.py --anima mei --cases tests/fixtures/skill_routing_cases.yaml --json
```

Results:

- Focused regression: 124 passed, 1 unrelated deprecation warning.
- Coverage: 86.77%.
- Evaluation: Hit@1 5/7, Hit@3 7/7, no-skill precision 2/2, false-positive rate 0.0%.
- Full suite and full E2E collection: blocked by missing optional `botocore`; confirmed same import error on `main`.

## Residual Risks

- Hit@1 remains 5/7 because most existing mei skills lack explicit routing metadata. The evaluation now reports this as metadata gap data for the next iteration.
- Formal production integration remains out of scope; `build_system_prompt()` behavior is intentionally unchanged.
