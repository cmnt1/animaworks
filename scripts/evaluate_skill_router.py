#!/usr/bin/env python3
from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate the shadow skill router against a small golden set.

This script is deliberately offline and read-only. It does not alter prompt
construction or write routing decisions back into skill files.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.paths import get_animas_dir, get_common_skills_dir  # noqa: E402
from core.skills.index import SkillIndex  # noqa: E402
from core.skills.router import SkillRouter  # noqa: E402

DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "skill_routing_cases.yaml"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = data.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError(f"{path} must contain a top-level cases list")
    return [case for case in cases if isinstance(case, dict)]


def _load_skills(anima: str) -> list:
    anima_dir = get_animas_dir() / anima
    index = SkillIndex(
        anima_dir / "skills",
        get_common_skills_dir(),
        anima_dir / "procedures",
        anima_dir=anima_dir,
    )
    return index.all_skills


def evaluate(
    *,
    anima: str,
    fixture: Path,
    top_k: int,
    min_score: float,
    include_body: bool,
) -> dict[str, Any]:
    skills = _load_skills(anima)
    router = SkillRouter(min_score=min_score, include_body=include_body)
    cases = _load_cases(fixture)
    gaps = router.metadata_gaps(skills)
    skill_names = {skill.name for skill in skills}

    evaluated: list[dict[str, Any]] = []
    actionable_total = 0
    hit_at_1 = 0
    hit_at_3 = 0
    no_skill_total = 0
    no_skill_correct = 0
    predicted_no_skill_total = 0
    predicted_no_skill_correct = 0
    false_positive = 0

    for case in cases:
        query = str(case.get("query", ""))
        expected_any = [str(name) for name in case.get("expected_any", [])]
        no_skill = bool(case.get("no_skill", False))
        candidates = router.route(query, skills, top_k=top_k)
        candidate_names = [candidate.name for candidate in candidates]
        predicted_no_skill = not candidates
        if predicted_no_skill:
            predicted_no_skill_total += 1

        if no_skill:
            no_skill_total += 1
            passed = predicted_no_skill
            if passed:
                no_skill_correct += 1
                predicted_no_skill_correct += 1
            else:
                false_positive += 1
        else:
            actionable_total += 1
            passed = any(name in candidate_names[:3] for name in expected_any)
            if candidate_names and candidate_names[0] in expected_any:
                hit_at_1 += 1
            if any(name in candidate_names[:3] for name in expected_any):
                hit_at_3 += 1

        expected_missing = [name for name in expected_any if name not in skill_names]
        expected_gaps = _expected_gap_details(expected_any, candidates, gaps)
        evaluated.append(
            {
                "id": case.get("id", ""),
                "query": query,
                "expected_any": expected_any,
                "no_skill": no_skill,
                "passed": passed,
                "candidates": [candidate.model_dump() for candidate in candidates],
                "expected_missing": expected_missing,
                "expected_metadata_gaps": expected_gaps,
            }
        )

    summary = {
        "anima": anima,
        "fixture": str(fixture),
        "skills_indexed": len(skills),
        "cases": len(evaluated),
        "actionable_cases": actionable_total,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "hit_at_1_rate": hit_at_1 / actionable_total if actionable_total else 1.0,
        "hit_at_3_rate": hit_at_3 / actionable_total if actionable_total else 1.0,
        "no_skill_cases": no_skill_total,
        "no_skill_correct": no_skill_correct,
        "no_skill_abstain_rate": no_skill_correct / no_skill_total if no_skill_total else 1.0,
        "predicted_no_skill": predicted_no_skill_total,
        "predicted_no_skill_correct": predicted_no_skill_correct,
        "no_skill_precision": (
            predicted_no_skill_correct / predicted_no_skill_total if predicted_no_skill_total else 1.0
        ),
        "false_positive_rate": false_positive / no_skill_total if no_skill_total else 0.0,
        "metadata_gap_skills": len(gaps),
    }
    return {"summary": summary, "cases": evaluated}


def _expected_gap_details(
    expected_any: list[str], candidates: list, gaps: dict[str, list[str]]
) -> dict[str, list[str]]:
    by_name = {candidate.name: candidate for candidate in candidates}
    details: dict[str, list[str]] = {}
    for name in expected_any:
        reasons: list[str] = []
        reasons.extend(gaps.get(name, []))
        candidate = by_name.get(name)
        if candidate is None:
            reasons.append("no_matching_signal")
        elif _fallback_only(candidate.reasons):
            reasons.append("matched_by_fallback_only")
        if reasons:
            details[name] = _dedupe(reasons)
    return details


def _fallback_only(reasons: list[str]) -> bool:
    strong_prefixes = ("trigger:", "use_when:", "tag:", "tool:", "platform:", "example:", "dense:")
    return not any(reason.startswith(strong_prefixes) for reason in reasons)


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _print_text(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("Shadow skill router evaluation")
    print(f"anima: {summary['anima']}")
    print(f"skills indexed: {summary['skills_indexed']}")
    print(
        "hit@1: {hit_at_1}/{actionable_cases} ({hit_at_1_rate:.1%}) | "
        "hit@3: {hit_at_3}/{actionable_cases} ({hit_at_3_rate:.1%})".format(**summary)
    )
    print(
        "no-skill abstain: {no_skill_correct}/{no_skill_cases} ({no_skill_abstain_rate:.1%}) | "
        "no-skill precision: {predicted_no_skill_correct}/{predicted_no_skill} ({no_skill_precision:.1%}) | "
        "false-positive: {false_positive_rate:.1%}".format(**summary)
    )
    print(f"skills with metadata gaps: {summary['metadata_gap_skills']}")
    print()

    for case in result["cases"]:
        status = "PASS" if case["passed"] else "FAIL"
        names = ", ".join(candidate["name"] for candidate in case["candidates"]) or "-"
        print(f"{status} {case['id']}: {names}")
        for candidate in case["candidates"]:
            print(
                "  - {name} score={score:.4f} confidence={confidence} path={path}".format(
                    **candidate,
                )
            )
            if candidate["reasons"]:
                print(f"    reasons: {'; '.join(candidate['reasons'][:3])}")
        if case["expected_missing"]:
            print(f"  missing expected skills: {', '.join(case['expected_missing'])}")
        if case["expected_metadata_gaps"]:
            print(f"  expected metadata gaps: {case['expected_metadata_gaps']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anima", default="mei", help="Anima name to evaluate")
    parser.add_argument("--fixture", "--cases", type=Path, default=DEFAULT_FIXTURE, help="YAML golden set")
    parser.add_argument("--top-k", type=int, default=3, help="Number of candidates to inspect")
    parser.add_argument("--min-score", type=float, default=1.15, help="Router abstention threshold")
    parser.add_argument("--no-body", action="store_true", help="Do not include skill bodies in lexical search")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    result = evaluate(
        anima=args.anima,
        fixture=args.fixture,
        top_k=args.top_k,
        min_score=args.min_score,
        include_body=not args.no_body,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_text(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
