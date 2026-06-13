"""taskdiary_promote.py — per-project, 4観点-filtered TaskDiary → _inbox promoter
(Phase 2 of GEN-019 memory-consumption-audit).

Why this exists
---------------
The old runner (`py_mod/task_diary_to_ai_rules_inbox.py`) dumped the ENTIRE
`●TaskDiary` section of a daily Diary as a single `General` blob into
`_inbox/General/<date>-codex-task-diary.md`. Phase 0 audit (2026-06-10) found
that every such candidate was lost: 0 of them ever reached a runbook
(取りこぼし率 ≒ 100%). Two structural causes:

  1. One coarse General blob — no per-project routing, so `apply_inbox_decision`
     never had a project to adopt it into, and sakura review skipped it.
  2. No 4観点 filter — daily failure logs / handoffs (ephemeral) were mixed with
     durable findings, so the candidate read as a daily snapshot, not knowledge.

This script fixes the FRONT half of the pipeline so candidates land in the
existing promote → apply → runbook_index last-mile (修正2-4) and get adopted:

  - Splits `●TaskDiary` by `**Project**` headings → per-project routing.
  - Keeps ONLY 「発見」+「うまくいったこと（効いた手法）」 (durable knowledge);
    drops 「うまくいかなかったこと」+「次回への申し送り」 (ephemeral).
  - Emits one candidate per project per day in promote_knowledge's `build_inbox_doc`
    format, so sakura review + `apply_inbox_decision.py` adopt it unchanged.
  - Idempotent (compares body, ignores the per-run promoted_at timestamp) and
    read-after-write verified.

Usage:
    python taskdiary_promote.py                       # today
    python taskdiary_promote.py --date 2026-06-08     # a specific diary
    python taskdiary_promote.py --date 2026-06-08 --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# sibling pipeline modules (promote_knowledge owns the canonical inbox format)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from promote_knowledge import (  # noqa: E402
    build_inbox_doc,
    dump_frontmatter,
    load_config,
    parse_frontmatter,
)
from consumption_metrics import (  # noqa: E402
    EVENT_GENERATED,
    SOURCE_TASKDIARY,
    log_event,
)

JST = timezone(timedelta(hours=9))

DEFAULT_VAULT = Path(r"E:\OneDriveBiz\Obsidian")
AUTO_MARKER = "<!-- task-diary-inbox:auto-generated -->"

# 4観点 we PROMOTE (durable knowledge) vs DROP (ephemeral). See module docstring.
PROMOTE_LABELS = ("発見", "うまくいったこと")
DROP_LABELS = ("うまくいかなかったこと", "次回への申し送り")
SECTION_TITLE = {"発見": "発見", "うまくいったこと": "効いた手法（うまくいったこと）"}

# Project-heading normalization. Valid project headings = config known_projects
# plus the two SoT-owning projects that route to their own runbooks dir.
EXTRA_PROJECTS = {"Obsidian", "AnimaWorks"}
HEADING_ALIASES = {
    "business": "General",
    "administration": "General",
    "全社": "General",
    "general": "General",
    "obsidian": "Obsidian",
    "animaworks": "AnimaWorks",
    "anima": "AnimaWorks",
}

_TIME_RE = re.compile(r"^\*\*\d{1,2}:\d{2}\*\*$")
_BOLD_RE = re.compile(r"^\*\*(.+?)\*\*$")
_TIME_CAPTURE_RE = re.compile(r"^\*\*(\d{1,2}:\d{2})\*\*$")
_BULLET_RE = re.compile(r"^-\s*([^:：]+?)\s*[:：]\s*(.*)$")

_EMPTY_VALUES = {
    "", "なし", "特になし", "特に無し", "なし。", "特になし。",
    "（なし）", "(なし)", "ない", "無し",
}


def parse_date(value: str | None) -> date:
    if not value:
        return datetime.now(JST).date()
    return datetime.strptime(value, "%Y-%m-%d").date()


def diary_path(vault: Path, day: date) -> Path:
    return vault / "Diary" / f"{day:%Y}" / f"{day:%Y-%m}" / f"Diary_{day:%y%m%d}.md"


def extract_task_diary_section(text: str) -> list[str]:
    """Return the lines of the `●TaskDiary` section (up to the next standalone ---)."""
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == "●TaskDiary":
            start = i + 1
            break
    if start is None:
        return []
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    return lines[start:end]


def normalize_project(heading: str, known: set[str]) -> str:
    h = heading.strip()
    if h in known or h in EXTRA_PROJECTS:
        return h
    low = h.lower()
    if low in HEADING_ALIASES:
        return HEADING_ALIASES[low]
    # case-insensitive match against known projects
    for proj in known | EXTRA_PROJECTS:
        if proj.lower() == low:
            return proj
    return "General"


def is_empty_value(value: str) -> bool:
    s = value.strip().rstrip("。").strip()
    return s in _EMPTY_VALUES


def collect_by_project(
    section_lines: list[str], known: set[str]
) -> dict[str, dict[str, list[tuple[str, str]]]]:
    """{project: {label: [(time, text), ...]}} for PROMOTE_LABELS only."""
    out: dict[str, dict[str, list[tuple[str, str]]]] = {}
    current_project = "General"
    current_time = ""
    for raw in section_lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        tm = _TIME_CAPTURE_RE.match(stripped)
        if tm:
            current_time = tm.group(1)
            continue
        bold = _BOLD_RE.match(stripped)
        if bold and not _TIME_RE.match(stripped):
            current_project = normalize_project(bold.group(1), known)
            current_time = ""
            continue
        bullet = _BULLET_RE.match(stripped)
        if not bullet:
            continue
        label = bullet.group(1).strip()
        value = bullet.group(2).strip()
        if label not in PROMOTE_LABELS:
            continue  # drop 失敗/申し送り and any mojibake/unknown label
        if is_empty_value(value):
            continue
        out.setdefault(current_project, {}).setdefault(label, []).append(
            (current_time, value)
        )
    return out


def render_body(project: str, day: date, buckets: dict[str, list[tuple[str, str]]]) -> str:
    """Build the candidate body (AUTO_MARKER + titled 観点 sections)."""
    parts: list[str] = [AUTO_MARKER, "", f"# {project} TaskDiary 知見（{day.isoformat()}）", ""]
    for label in PROMOTE_LABELS:
        items = buckets.get(label) or []
        if not items:
            continue
        parts.append(f"## {SECTION_TITLE[label]}")
        for tm, text in items:
            prefix = f"（{tm}）" if tm else ""
            parts.append(f"- {prefix}{text}")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def body_without_frontmatter(text: str) -> str:
    _fm, body = parse_frontmatter(text)
    return body.strip()


def write_candidate(
    *,
    project: str,
    day: date,
    buckets: dict[str, list[tuple[str, str]]],
    src_path: Path,
    inbox_root: Path,
    now: datetime,
    dry_run: bool,
) -> dict[str, Any]:
    body = render_body(project, day, buckets)
    doc = build_inbox_doc(
        anima="taskdiary",
        kind="task_diary",
        source_path=src_path,
        source_fm={"confidence": 0.7},
        body=body,
        project=project,
        today=now,
    )
    target_dir = inbox_root / project
    target_path = target_dir / f"{day.isoformat()}-taskdiary-{project.lower()}.md"
    rel = f"{project}/{target_path.name}"
    res: dict[str, Any] = {"project": project, "target": rel, "items": sum(len(v) for v in buckets.values())}

    if target_path.exists():
        existing = target_path.read_text(encoding="utf-8")
        if AUTO_MARKER not in existing:
            res["status"] = "refused"
            res["note"] = "target exists without AUTO_MARKER (hand-edited); not overwriting"
            return res
        if body_without_frontmatter(existing) == body_without_frontmatter(doc):
            res["status"] = "unchanged"
            return res

    if dry_run:
        res["status"] = "dry-run"
        res["preview"] = doc
        return res

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path.write_text(doc, encoding="utf-8", newline="\n")
    # read-after-write verification
    rt = target_path.read_text(encoding="utf-8")
    ok = target_path.exists() and AUTO_MARKER in rt and body_without_frontmatter(rt) == body_without_frontmatter(doc)
    res["status"] = "wrote" if ok else "verify-failed"
    return res


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", help="Target diary date YYYY-MM-DD (default: today JST)")
    p.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    p.add_argument("--inbox-root", type=Path, default=None,
                   help="Override inbox root (default: from promote_knowledge.json)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    config = load_config()
    known = set(config.get("known_projects", []) or [])
    inbox_root = args.inbox_root or Path(config["inbox_root"])

    day = parse_date(args.date)
    dpath = diary_path(args.vault, day)
    if not dpath.exists():
        print(f"[taskdiary-promote] diary not found: {dpath}")
        return 0

    section = extract_task_diary_section(dpath.read_text(encoding="utf-8"))
    if not section:
        print(f"[taskdiary-promote] no ●TaskDiary section: {dpath}")
        return 0

    by_project = collect_by_project(section, known)
    if not by_project:
        print(f"[taskdiary-promote] no promotable 発見/うまくいったこと items: {dpath}")
        return 0

    now = datetime.now(JST)
    results = []
    failed = 0
    for project in sorted(by_project):
        res = write_candidate(
            project=project,
            day=day,
            buckets=by_project[project],
            src_path=dpath,
            inbox_root=inbox_root,
            now=now,
            dry_run=args.dry_run,
        )
        results.append(res)
        if res["status"] in {"verify-failed", "refused"}:
            failed += 1
        # Ledger: a candidate with N items exists for this day. Logged on both
        # "wrote" and "unchanged" so re-runs/backfill stay accurate; the reducer
        # is max-per-(date,project), so re-logging the same snapshot is idempotent.
        if not args.dry_run and res["status"] in {"wrote", "unchanged"}:
            log_event(
                source=SOURCE_TASKDIARY,
                event=EVENT_GENERATED,
                project=project,
                count=res["items"],
                day=day.isoformat(),
            )

    print(f"=== taskdiary_promote {day.isoformat()} ({'DRY' if args.dry_run else 'LIVE'}) ===")
    for r in results:
        line = f"  [{r['status']:13s}] {r['target']}  (items={r['items']})"
        if r.get("note"):
            line += f"  — {r['note']}"
        print(line)
        if args.dry_run and r.get("preview"):
            print("    " + r["preview"].replace("\n", "\n    "))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
