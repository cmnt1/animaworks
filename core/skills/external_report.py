from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Report the result of indexing external engine skill roots.

Usage:
    python -m core.skills.external_report [--anima <name>] [--json]

Displays the externally adopted skills (engine / name / origin), the skills
shadowed by name collisions (dropped / kept / reason), and the excluded
(denied) entries.
"""

import argparse
import json
import sys

from core.paths import get_animas_dir, get_common_skills_dir, get_data_dir
from core.skills.index import SkillIndex


def _build_index(anima: str | None) -> SkillIndex:
    """Build a SkillIndex for the requested anima (or a bare one when None)."""
    if anima:
        anima_dir = get_animas_dir() / anima
        index = SkillIndex(
            anima_dir / "skills",
            get_common_skills_dir(),
            anima_dir / "procedures",
            anima_dir=anima_dir,
        )
    else:
        data_dir = get_data_dir()
        index = SkillIndex(data_dir / "skills", get_common_skills_dir(), None)
    index.build_index()
    return index


def _as_dict(skill) -> dict:
    return {
        "name": skill.name,
        "engine": (skill.source and skill.source.engine) or None,
        "origin": (skill.source and skill.source.origin) or str(skill.path),
        "trust_level": skill.trust_level.value if hasattr(skill.trust_level, "value") else str(skill.trust_level),
    }


def _run(anima: str | None, as_json: bool) -> int:
    index = _build_index(anima)
    adopted = [m for m in index.all_skills if m.is_external]
    shadowed = index.shadowed
    excluded = index.excluded

    if as_json:
        payload = {
            "adopted": [_as_dict(m) for m in adopted],
            "shadowed": [
                {
                    "dropped": _as_dict(s.dropped),
                    "kept": _as_dict(s.kept),
                    "reason": s.reason,
                }
                for s in shadowed
            ],
            "excluded": [{"path": p, "reason": r} for p, r in excluded.items()],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"=== External skills report (anima={anima or 'none'}) ===")
    print(f"\nAdopted external skills ({len(adopted)}):")
    for m in adopted:
        engine = (m.source and m.source.engine) or "?"
        origin = (m.source and m.source.origin) or "?"
        print(f"  - {m.name} (engine={engine}, origin={origin})")

    print(f"\nShadowed ({len(shadowed)}):")
    for s in shadowed:
        print(
            f"  - dropped={s.dropped.name} kept={s.kept.name} reason={s.reason} "
            f"(dropped_engine={(s.dropped.source and s.dropped.source.engine) or '?'})"
        )

    print(f"\nExcluded ({len(excluded)}):")
    for path, reason in excluded.items():
        print(f"  - {path} ({reason})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report external skill root indexing results.")
    parser.add_argument("--anima", default=None, help="Anima name (default: bare index, no anima).")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args(argv)
    try:
        return _run(args.anima, args.json)
    except Exception as exc:  # pragma: no cover - CLI boundary
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
