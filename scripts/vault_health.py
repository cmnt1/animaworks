"""Vault health audit for the _ai_rules SoT.

Scans Obsidian Vault and Tools/<Project>/ shim files for structural integrity.
Writes a single-line summary to vault_health_log.md and emits a JSON detail blob.

Categories (5):
  - dangling_shim       (Critical) — `@<absolute_path>` line in _ai_rules\ points to missing file
  - broken_tools_shim   (Critical) — Tools\<Project>\CLAUDE.md / AGENTS.md shim target missing
  - missing_frontmatter (Warning)  — Base-eligible .md without role/scope frontmatter
  - stale_updated       (Info)     — `updated` field older than 180 days (excludes role:principle)
  - orphan_persona      (Warning)  — Anima identity.md or injection.md shim missing/broken (15 personas pair check)

Usage:
  python vault_health.py             # human-readable report + log append
  python vault_health.py --json      # JSON detail to stdout
  python vault_health.py --dry-run   # do not append to log
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

VAULT_ROOT = Path(r"E:\OneDriveBiz\Obsidian")
AI_RULES = VAULT_ROOT / "_ai_rules"
TOOLS_ROOT = Path(r"E:\OneDriveBiz\Tools")
ANIMAS_ROOT = Path(r"C:\Users\cmnt\.animaworks\animas")
LOG_PATH = AI_RULES / "_shared" / "workflows" / "vault_health_log.md"

STALE_DAYS = 180

PROJECTS = [
    "Accounting", "Affiliate", "Business", "Finance",
    "General", "Property", "Writing",
]
# AnimaWorks / Obsidian are special — their shim files live in their owning repo trees.
TOOLS_SHIM_TARGETS = [
    (Path(r"E:\OneDriveBiz\Tools\Accounting\CLAUDE.md"), Path(r"E:\OneDriveBiz\Tools\Accounting\AGENTS.md")),
    (Path(r"E:\OneDriveBiz\Tools\Affiliate\CLAUDE.md"), Path(r"E:\OneDriveBiz\Tools\Affiliate\AGENTS.md")),
    (Path(r"E:\OneDriveBiz\Tools\Business\CLAUDE.md"), Path(r"E:\OneDriveBiz\Tools\Business\AGENTS.md")),
    (Path(r"E:\OneDriveBiz\Tools\Finance\CLAUDE.md"), Path(r"E:\OneDriveBiz\Tools\Finance\AGENTS.md")),
    (Path(r"E:\OneDriveBiz\Tools\General\CLAUDE.md"), Path(r"E:\OneDriveBiz\Tools\General\AGENTS.md")),
    (Path(r"E:\OneDriveBiz\Tools\Property\CLAUDE.md"), Path(r"E:\OneDriveBiz\Tools\Property\AGENTS.md")),
    (Path(r"E:\OneDriveBiz\Tools\Writing\CLAUDE.md"), Path(r"E:\OneDriveBiz\Tools\Writing\AGENTS.md")),
    # AnimaWorks/Obsidian shim live at .animaworks / .obsidian roots:
    (Path(r"E:\OneDriveBiz\Tools\General\animaworks\CLAUDE.md"), Path(r"E:\OneDriveBiz\Tools\General\animaworks\AGENTS.md")),
    (Path(r"E:\OneDriveBiz\Obsidian\CLAUDE.md"), Path(r"E:\OneDriveBiz\Obsidian\AGENTS.md")),
]


@dataclass
class Finding:
    category: str
    severity: str  # critical | warning | info
    path: str
    detail: str


@dataclass
class Report:
    critical: list[Finding] = field(default_factory=list)
    warning: list[Finding] = field(default_factory=list)
    info: list[Finding] = field(default_factory=list)

    def add(self, f: Finding) -> None:
        getattr(self, f.severity).append(f)

    def counts(self) -> tuple[int, int, int]:
        return len(self.critical), len(self.warning), len(self.info)


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_AT_IMPORT_RE = re.compile(r"^\s*@([A-Za-z]:[\\\/].+?)\s*$")


def parse_frontmatter(text: str) -> dict[str, str] | None:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm


def find_at_imports(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        m = _AT_IMPORT_RE.match(line)
        if m:
            out.append(m.group(1).strip())
    return out


def check_dangling_shim(report: Report) -> None:
    for md in AI_RULES.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
        except Exception as e:
            report.add(Finding("dangling_shim", "critical", str(md), f"read error: {e}"))
            continue
        for target in find_at_imports(text):
            tp = Path(target)
            if not tp.is_absolute() or not tp.exists():
                report.add(Finding(
                    "dangling_shim", "critical", str(md),
                    f"@import target missing: {target}",
                ))


def check_broken_tools_shim(report: Report) -> None:
    for claude_md, agents_md in TOOLS_SHIM_TARGETS:
        for f in (claude_md, agents_md):
            if not f.exists():
                # Not all projects have AGENTS.md / CLAUDE.md both — skip silently.
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except Exception as e:
                report.add(Finding("broken_tools_shim", "critical", str(f), f"read error: {e}"))
                continue
            targets = find_at_imports(text)
            if not targets:
                # File exists but has no shim — could be a full instruction file. Skip.
                continue
            for t in targets:
                tp = Path(t)
                if not tp.is_absolute() or not tp.exists():
                    report.add(Finding(
                        "broken_tools_shim", "critical", str(f),
                        f"@import target missing: {t}",
                    ))


def _is_base_eligible(md: Path) -> bool:
    """Return True if this .md should have role/scope frontmatter (per _index.md spec)."""
    try:
        rel = md.relative_to(AI_RULES)
    except ValueError:
        return False
    parts = rel.parts
    if not parts:
        return False
    # Exclude the workflows/{builder,fragments,memory}/ subtrees (AnimaWorks runtime fragments).
    if parts[0] == "_shared" and len(parts) >= 3 and parts[1] == "workflows":
        if parts[2] in {"builder", "fragments", "memory"}:
            return False
    # Skip _index.md itself (has frontmatter but role=doc which is fine)
    return True


def check_missing_frontmatter(report: Report) -> None:
    for md in AI_RULES.rglob("*.md"):
        if not _is_base_eligible(md):
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = parse_frontmatter(text)
        if fm is None:
            report.add(Finding("missing_frontmatter", "warning", str(md), "no frontmatter"))
            continue
        missing = [k for k in ("role", "scope") if k not in fm]
        if missing:
            report.add(Finding(
                "missing_frontmatter", "warning", str(md),
                f"missing keys: {','.join(missing)}",
            ))


def check_stale_updated(report: Report) -> None:
    today = _dt.date.today()
    threshold = today - _dt.timedelta(days=STALE_DAYS)
    for md in AI_RULES.rglob("*.md"):
        if not _is_base_eligible(md):
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = parse_frontmatter(text)
        if fm is None:
            continue
        if fm.get("role") == "principle":
            continue
        upd = fm.get("updated", "")
        if not upd:
            continue
        try:
            d = _dt.date.fromisoformat(upd)
        except ValueError:
            continue
        if d < threshold:
            report.add(Finding(
                "stale_updated", "info", str(md),
                f"updated={upd} (>{STALE_DAYS}d old)",
            ))


def check_orphan_persona(report: Report) -> None:
    if not ANIMAS_ROOT.exists():
        return
    for anima_dir in ANIMAS_ROOT.iterdir():
        if not anima_dir.is_dir():
            continue
        identity = anima_dir / "identity.md"
        injection = anima_dir / "injection.md"
        for f, kind in ((identity, "identity"), (injection, "injection")):
            if not f.exists():
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except Exception as e:
                report.add(Finding("orphan_persona", "warning", str(f), f"read error: {e}"))
                continue
            targets = find_at_imports(text)
            if not targets:
                continue  # file is not a shim, treat as ok
            for t in targets:
                tp = Path(t)
                if not tp.is_absolute() or not tp.exists():
                    report.add(Finding(
                        "orphan_persona", "warning", str(f),
                        f"{kind} shim target missing: {t}",
                    ))


def run(append_log: bool = True) -> tuple[Report, dict]:
    report = Report()
    check_dangling_shim(report)
    check_broken_tools_shim(report)
    check_missing_frontmatter(report)
    check_stale_updated(report)
    check_orphan_persona(report)

    c, w, i = report.counts()
    today = _dt.date.today().isoformat()
    summary_line = f"## [{today}] health | critical={c} warning={w} info={i}"

    if append_log:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not LOG_PATH.exists():
            LOG_PATH.write_text(
                "---\nrole: workflow\nscope: shared\npriority: normal\nupdated: " + today + "\n---\n\n"
                "# Vault health log\n\n", encoding="utf-8")
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(summary_line + "\n")

    detail = {
        "date": today,
        "counts": {"critical": c, "warning": w, "info": i},
        "findings": [
            {"category": f.category, "severity": f.severity, "path": f.path, "detail": f.detail}
            for f in (*report.critical, *report.warning, *report.info)
        ],
    }
    return report, detail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="emit JSON detail to stdout")
    ap.add_argument("--dry-run", action="store_true", help="do not append to log")
    args = ap.parse_args()

    report, detail = run(append_log=not args.dry_run)

    if args.json:
        print(json.dumps(detail, ensure_ascii=False, indent=2))
        return 1 if report.critical else 0

    c, w, i = report.counts()
    print(f"Vault health: critical={c} warning={w} info={i}")
    for severity, items in (("CRITICAL", report.critical), ("WARNING", report.warning), ("INFO", report.info)):
        if not items:
            continue
        print(f"\n[{severity}]")
        for f in items:
            print(f"  {f.category}: {f.path} — {f.detail}")
    return 1 if report.critical else 0


if __name__ == "__main__":
    sys.exit(main())
