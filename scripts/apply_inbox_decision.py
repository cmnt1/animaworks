"""apply_inbox_decision.py — deterministic adopt/reject executor for the
`_ai_rules/_inbox` knowledge-promotion pipeline (修正3 of the second-brain
knowledge-delivery fix).

Why this exists
---------------
sakura-4 (the weekly LLM review cron) used to *judge* inbox items but the actual
"`status: pending_review` 除去 + runbook へ mv" was left to LLM self-report, so it
often never happened ("判定したが配送されない"). This script makes the move
**deterministic and self-verifying**: the LLM only decides adopt/reject + target
project; THIS script performs the file move, frontmatter cleaning, and
read-after-write verification, exactly like the review_*.py mechanical pattern.

Contract
--------
Input: a decisions JSON (file path, or `-` for stdin):

    {
      "decisions": [
        {"inbox_file": "Affiliate/2026-06-10-sakura-foo.md",
         "action": "adopt", "project": "Affiliate",
         "target_name": "foo.md",            # optional; derived if omitted
         "overwrite": false,                  # optional; default false
         "reason": "durable affiliate procedure"},
        {"inbox_file": "General/2026-06-10-codex-task-diary.md",
         "action": "reject", "reason": "daily snapshot"}
      ]
    }

Output: result JSON to stdout (and to state/task_results/ unless --no-log):

    {"status": "done"|"partial", "adopted": N, "rejected": M, "skipped": K,
     "failed": F, "results": [...], "residual_inbox": {"General": x, ...}}

Exit code 0 only if every decision verified (no failures). Non-zero on any
failure so the cron can detect a broken sweep.

Usage:
    python apply_inbox_decision.py --decisions decisions.json
    python apply_inbox_decision.py --decisions - --dry-run < decisions.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

# sibling module: deterministic runbook-index (consumption wiring) regenerator
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from runbook_index import write_index as regenerate_runbook_index
except ImportError:
    regenerate_runbook_index = None

JST = timezone(timedelta(hours=9))

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "promote_knowledge.json"

AI_RULES_ROOT = Path("E:/OneDriveBiz/Obsidian/_ai_rules")
DEFAULT_INBOX_ROOT = AI_RULES_ROOT / "_inbox"
PROJECTS_ROOT = AI_RULES_ROOT / "projects"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
AUTO_MARKER = "<!-- task-diary-inbox:auto-generated -->"

# Pipeline-only frontmatter keys that must NOT survive into a runbook.
STRIP_KEYS = {
    "status",
    "source_anima",
    "source_kind",
    "source_path",
    "source_confidence",
    "source_success_count",
    "source_failure_count",
    "promoted_at",
    "promoted_to_inbox",
}


def load_inbox_root() -> Path:
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return Path(cfg.get("inbox_root") or DEFAULT_INBOX_ROOT)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_INBOX_ROOT


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, m.group(2)


def dump_frontmatter(fm: dict[str, Any], body: str) -> str:
    yaml_text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=True).rstrip()
    return f"---\n{yaml_text}\n---\n\n{body.lstrip()}"


def confidence_label(raw: Any) -> str:
    """Map a numeric source_confidence to the ai_note_quality scale."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return "medium"
    if v >= 0.95:
        return "stated"
    if v >= 0.8:
        return "high"
    if v >= 0.6:
        return "medium"
    return "speculation"


def clean_body(body: str) -> str:
    """Drop the inbox review scaffolding from the body."""
    lines = body.splitlines()
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s == AUTO_MARKER:
            continue
        if s.startswith("> [!review]") or (s.startswith(">") and "source:" in s):
            continue
        # standalone [IMPORTANT] marker line left over from Anima notes
        if s == "[IMPORTANT]":
            continue
        out.append(ln)
    return "\n".join(out).strip() + "\n"


def derive_target_name(inbox_stem: str) -> str:
    """`2026-06-10-sakura-aff-priority-recovery` -> `aff-priority-recovery`."""
    name = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", inbox_stem)
    # strip a single leading anima/source token (lowercase word) if followed by more
    name = re.sub(r"^[a-z0-9]+-(?=[a-z0-9])", "", name, count=1)
    return f"{name}.md"


def build_runbook(
    fm: dict[str, Any], body: str, project: str, now: datetime
) -> str:
    clean_fm: dict[str, Any] = {
        "role": fm.get("role", "runbook"),
        "scope": "project",
        "project": project,
        "priority": fm.get("priority", "normal"),
        "updated": now.date().isoformat(),
        "ai-first": True,
        "confidence": confidence_label(fm.get("source_confidence")),
    }
    # preserve a Base tracking id if present
    if fm.get("daily_ops_copy_id"):
        clean_fm["daily_ops_copy_id"] = fm["daily_ops_copy_id"]
    # carry over any non-pipeline keys we didn't explicitly set
    for k, v in fm.items():
        if k in STRIP_KEYS or k in clean_fm:
            continue
        clean_fm[k] = v
    return dump_frontmatter(clean_fm, clean_body(body))


def apply_one(
    decision: dict[str, Any], inbox_root: Path, now: datetime, dry_run: bool
) -> dict[str, Any]:
    rel = decision.get("inbox_file", "")
    action = decision.get("action", "")
    res: dict[str, Any] = {
        "inbox_file": rel,
        "action": action,
        "reason": decision.get("reason", ""),
        "checks": {},
        "ok": False,
    }
    inbox_path = inbox_root / rel
    if not inbox_path.exists():
        res["error"] = f"inbox file not found: {inbox_path}"
        return res

    if action == "reject":
        if dry_run:
            res["ok"] = True
            res["note"] = "DRY: would delete"
            return res
        inbox_path.unlink()
        res["checks"]["inbox_removed"] = not inbox_path.exists()
        res["ok"] = res["checks"]["inbox_removed"]
        return res

    if action != "adopt":
        res["error"] = f"unknown action: {action!r}"
        return res

    project = decision.get("project")
    if not project:
        res["error"] = "adopt requires 'project'"
        return res
    target_dir = PROJECTS_ROOT / project / "runbooks"
    target_name = decision.get("target_name") or derive_target_name(inbox_path.stem)
    if not target_name.endswith(".md"):
        target_name += ".md"
    target_path = target_dir / target_name
    res["target"] = str(target_path).replace("\\", "/")

    if target_path.exists() and not decision.get("overwrite"):
        res["ok"] = True
        res["skipped"] = True
        res["note"] = "target already exists (overwrite=false); leaving inbox file"
        return res

    fm, body = parse_frontmatter(inbox_path.read_text(encoding="utf-8"))
    doc = build_runbook(fm, body, project, now)

    if dry_run:
        res["ok"] = True
        res["note"] = f"DRY: would write {target_path} and remove inbox file"
        return res

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path.write_text(doc, encoding="utf-8", newline="\n")

    # read-after-write verification
    written_ok = target_path.exists()
    nonempty_ok = False
    if written_ok:
        rt_fm, rt_body = parse_frontmatter(target_path.read_text(encoding="utf-8"))
        nonempty_ok = bool(rt_body.strip()) and rt_fm.get("status") != "pending_review"
    res["checks"]["target_written"] = written_ok
    res["checks"]["target_nonempty_clean"] = nonempty_ok

    if written_ok and nonempty_ok:
        inbox_path.unlink()
        res["checks"]["inbox_removed"] = not inbox_path.exists()
    else:
        res["checks"]["inbox_removed"] = False

    res["ok"] = all(res["checks"].values())
    return res


def residual_counts(inbox_root: Path) -> dict[str, int]:
    out: dict[str, int] = {}
    if not inbox_root.exists():
        return out
    for sub in sorted(inbox_root.iterdir()):
        if sub.is_dir():
            out[sub.name] = len(list(sub.glob("*.md")))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--decisions", required=True, help="path to decisions JSON, or - for stdin")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-log", action="store_true", help="do not write a result JSON to task_results")
    args = p.parse_args(argv)

    if args.decisions == "-":
        payload = json.load(sys.stdin)
    else:
        payload = json.loads(Path(args.decisions).read_text(encoding="utf-8"))
    decisions = payload.get("decisions", payload if isinstance(payload, list) else [])

    inbox_root = load_inbox_root()
    now = datetime.now(JST)

    results = [apply_one(d, inbox_root, now, args.dry_run) for d in decisions]

    def is_new_adopt(r: dict[str, Any]) -> bool:
        return r["action"] == "adopt" and bool(r.get("ok")) and not r.get("skipped")

    adopted = sum(1 for r in results if is_new_adopt(r))
    skipped = sum(1 for r in results if r.get("skipped"))
    rejected = sum(1 for r in results if r["action"] == "reject" and r.get("ok"))
    failed = sum(1 for r in results if not r.get("ok"))

    # consumption wiring: a runbook that is adopted but never surfaced just
    # accumulates unread. Regenerate the awareness index for each project that
    # gained a runbook so the new knowledge is discoverable at session start.
    index_updates: list[dict[str, Any]] = []
    if not args.dry_run and regenerate_runbook_index is not None:
        touched = sorted({
            d.get("project")
            for d, r in zip(decisions, results)
            if is_new_adopt(r) and d.get("project")
        })
        for proj in touched:
            try:
                index_updates.append(regenerate_runbook_index(proj, now=now))
            except Exception as exc:  # best-effort; never fail the sweep on index
                index_updates.append({"project": proj, "error": str(exc)})

    summary = {
        "status": "done" if failed == 0 else "partial",
        "ran_at": now.isoformat(timespec="seconds"),
        "dry_run": args.dry_run,
        "adopted": adopted,
        "rejected": rejected,
        "skipped": skipped,
        "failed": failed,
        "results": results,
        "residual_inbox": residual_counts(inbox_root),
        "index_updates": index_updates,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not args.dry_run and not args.no_log:
        # leave a machine-checkable trail in sakura's task_results
        tr = Path(r"C:\Users\cmnt\.animaworks\animas\sakura\state\task_results")
        if tr.exists():
            stamp = now.strftime("%Y%m%d-%H%M%S")
            (tr / f"inbox-apply-{stamp}.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
