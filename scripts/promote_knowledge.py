"""Promote Anima procedures/knowledge to Obsidian `_ai_rules/_inbox/` for review.

Animaが書き出した `procedures/` `knowledge/` のうち、confidence/利用実績の閾値を満たし
まだ昇格されていないものをObsidianのレビュー待ち inbox に書き出す。

設計趣旨:
- `_index.md` の「Obsidian = ストック/canonical、NotebookLM = フロー」原則に従い、
  Anima → Obsidian 正本への直書きは行わない。`_inbox/` に staging し、ユーザーが
  レビュー後に `projects/<X>/runbooks/` に昇格させる。
- 冪等性: source frontmatter に `promoted_to_inbox` タイムスタンプを書き込み、
  二度目以降はスキップ（`--force` で強制再昇格）。
- レート制御: project あたり `max_items_per_project_per_run` 件で頭打ち。

使い方:
    python3 scripts/promote_knowledge.py                # 全Anima、デフォルト閾値
    python3 scripts/promote_knowledge.py --dry-run      # 何も書かない
    python3 scripts/promote_knowledge.py --anima sakura # 特定Animaのみ
    python3 scripts/promote_knowledge.py --since 7      # 直近7日に更新された分のみ
    python3 scripts/promote_knowledge.py --force        # 既昇格分も再昇格

config: scripts/promote_knowledge.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("promote_knowledge")

JST = timezone(timedelta(hours=9))

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "promote_knowledge.json"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"config not found: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def animaworks_home() -> Path:
    return Path(os.environ.get("ANIMAWORKS_HOME") or Path.home() / ".animaworks")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = m.group(2)
    return fm, body


def dump_frontmatter(fm: dict[str, Any], body: str) -> str:
    if not fm:
        return body
    yaml_text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=True).rstrip()
    return f"---\n{yaml_text}\n---\n\n{body.lstrip()}"


def resolve_project(
    anima_name: str, department: str | None, config: dict[str, Any]
) -> str:
    override = config.get("anima_override", {}) or {}
    if anima_name in override:
        return override[anima_name]
    dept_map = config.get("department_map", {}) or {}
    if department and department in dept_map:
        return dept_map[department]
    return config.get("default_project", "General")


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9一-龥ぁ-んァ-ヶー\-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80] or "item"


def load_anima_status(anima_dir: Path) -> dict[str, Any]:
    status_path = anima_dir / "status.json"
    if not status_path.exists():
        return {}
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def collect_candidates(
    anima_dir: Path,
    kind: str,
    thresholds: dict[str, Any],
    since_days: int | None,
    force: bool,
) -> list[tuple[Path, dict[str, Any], str]]:
    """Return [(path, frontmatter, body), ...] for items eligible for promotion."""
    sub = anima_dir / kind
    if not sub.exists():
        return []

    now = datetime.now(JST)
    min_conf = (
        thresholds["procedure_min_confidence"]
        if kind == "procedures"
        else thresholds["knowledge_min_confidence"]
    )
    min_success = thresholds.get("procedure_min_success", 0) if kind == "procedures" else 0

    out: list[tuple[Path, dict[str, Any], str]] = []
    for p in sorted(sub.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, body = parse_frontmatter(text)
        if not body.strip():
            continue

        if not force and fm.get("promoted_to_inbox"):
            continue

        conf = float(fm.get("confidence", 0.0) or 0.0)
        if conf < min_conf:
            continue
        if kind == "procedures":
            if int(fm.get("success_count", 0) or 0) < min_success:
                continue

        if since_days is not None:
            ts = fm.get("last_used") or fm.get("updated_at") or fm.get("created_at")
            mtime = None
            if isinstance(ts, str):
                try:
                    mtime = datetime.fromisoformat(ts)
                except ValueError:
                    mtime = None
            if mtime is None:
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=JST)
            if mtime.tzinfo is None:
                mtime = mtime.replace(tzinfo=JST)
            if mtime < now - timedelta(days=since_days):
                continue

        out.append((p, fm, body))
    return out


def build_inbox_doc(
    *,
    anima: str,
    kind: str,
    source_path: Path,
    source_fm: dict[str, Any],
    body: str,
    project: str,
    today: datetime,
) -> str:
    inbox_fm = {
        "role": "runbook",
        "scope": "project",
        "project": project,
        "status": "pending_review",
        "source_anima": anima,
        "source_kind": kind,
        "source_path": str(source_path).replace("\\", "/"),
        "source_confidence": source_fm.get("confidence"),
        "promoted_at": today.isoformat(timespec="seconds"),
        "updated": today.date().isoformat(),
    }
    if kind == "procedures":
        inbox_fm["source_success_count"] = source_fm.get("success_count")
        inbox_fm["source_failure_count"] = source_fm.get("failure_count")
    inbox_fm = {k: v for k, v in inbox_fm.items() if v is not None}

    header = (
        f"> [!review] {anima} の {kind} から昇格された知見。"
        f"レビュー後 `_ai_rules/projects/{project}/runbooks/` へ移動してください。\n"
        f"> source: `{source_path.name}` (confidence={source_fm.get('confidence')})\n\n"
    )
    return dump_frontmatter(inbox_fm, header + body.strip() + "\n")


def stamp_source(path: Path, fm: dict[str, Any], body: str, now: datetime) -> None:
    fm = dict(fm)
    fm["promoted_to_inbox"] = now.isoformat(timespec="seconds")
    new_text = dump_frontmatter(fm, body)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    tmp.replace(path)


def title_from_body(body: str, fallback: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return fallback


def promote_one(
    *,
    anima: str,
    kind: str,
    source_path: Path,
    fm: dict[str, Any],
    body: str,
    project: str,
    inbox_root: Path,
    now: datetime,
    dry_run: bool,
) -> Path | None:
    title = title_from_body(body, source_path.stem)
    slug = slugify(source_path.stem)
    date_prefix = now.date().isoformat()
    target_dir = inbox_root / project
    target_path = target_dir / f"{date_prefix}-{anima}-{slug}.md"

    doc = build_inbox_doc(
        anima=anima,
        kind=kind,
        source_path=source_path,
        source_fm=fm,
        body=body,
        project=project,
        today=now,
    )
    logger.info(
        "%s [%s] %s/%s/%s -> %s",
        "DRY" if dry_run else "PROMOTE",
        project,
        anima,
        kind,
        source_path.name,
        target_path,
    )
    if dry_run:
        return target_path

    target_dir.mkdir(parents=True, exist_ok=True)
    # Avoid clobbering an existing inbox file with the same name
    n = 1
    final = target_path
    while final.exists():
        n += 1
        final = target_dir / f"{date_prefix}-{anima}-{slug}-{n}.md"
    final.write_text(doc, encoding="utf-8")
    stamp_source(source_path, fm, body, now)
    # Silence unused-var lint without touching logic
    _ = title
    return final


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--anima", help="Limit to a single anima")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="Re-promote already-promoted items")
    p.add_argument("--since", type=int, default=None, help="Only items updated within N days")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    config = load_config()
    thresholds = config["thresholds"]
    max_per_project = int(thresholds.get("max_items_per_project_per_run", 10))
    inbox_root = Path(config["inbox_root"])

    animas_root = animaworks_home() / "animas"
    if not animas_root.exists():
        print(f"No animas directory at {animas_root}", file=sys.stderr)
        return 1

    anima_dirs = sorted(
        d for d in animas_root.iterdir()
        if d.is_dir() and (not args.anima or d.name == args.anima)
    )
    if not anima_dirs:
        print("No matching anima directories", file=sys.stderr)
        return 1

    now = datetime.now(JST)
    per_project_count: dict[str, int] = {}
    summary: dict[str, dict[str, int]] = {}

    for anima_dir in anima_dirs:
        anima = anima_dir.name
        status = load_anima_status(anima_dir)
        project = resolve_project(anima, status.get("department"), config)

        for kind in ("procedures", "knowledge"):
            candidates = collect_candidates(
                anima_dir, kind, thresholds, args.since, args.force
            )
            for path, fm, body in candidates:
                if per_project_count.get(project, 0) >= max_per_project:
                    logger.info(
                        "rate-limited: %s already has %d items this run, skipping rest",
                        project,
                        max_per_project,
                    )
                    break
                target = promote_one(
                    anima=anima,
                    kind=kind,
                    source_path=path,
                    fm=fm,
                    body=body,
                    project=project,
                    inbox_root=inbox_root,
                    now=now,
                    dry_run=args.dry_run,
                )
                if target is None:
                    continue
                per_project_count[project] = per_project_count.get(project, 0) + 1
                summary.setdefault(anima, {}).setdefault(kind, 0)
                summary[anima][kind] += 1

    print("\n=== promote_knowledge summary ===")
    if not summary:
        print("(no items promoted)")
    for anima, kinds in sorted(summary.items()):
        for kind, n in sorted(kinds.items()):
            print(f"  {anima:10s} {kind:11s} {n}")
    for project, n in sorted(per_project_count.items()):
        print(f"  project[{project}]: {n}")
    if args.dry_run:
        print("(dry-run: no files written, no source frontmatter stamped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
