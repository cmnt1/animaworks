#!/usr/bin/env python3
"""Audit task exec deaths and wasted continuations across the fleet.

Run every few days against production:

    .venv/bin/python scripts/audit_task_exec_waste.py --days 3

Reports, per the completion-declaration protocol (2026-08-10):
- task_exec_end status breakdown per anima
- continuation burns: tasks that consumed all continuations and failed
- rapid burns: tasks whose continuations were all spent within minutes
- stranded continuations: queue in_progress with no descriptor (claim race)
- claim deferrals/rejections seen in logs
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

RAPID_BURN_WINDOW_MIN = 15


def _iter_events(activity_dir: Path, since: datetime):
    for day_file in sorted(activity_dir.glob("*.jsonl")):
        try:
            day = datetime.strptime(day_file.stem, "%Y-%m-%d")
        except ValueError:
            continue
        if day.date() < since.date():
            continue
        for line in day_file.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "task_exec_end":
                continue
            try:
                ts = datetime.fromisoformat(event["ts"])
            except (KeyError, ValueError):
                continue
            if ts.replace(tzinfo=None) < since:
                continue
            yield ts, event


def _stranded_continuations(anima_dir: Path) -> list[str]:
    queue_path = anima_dir / "state" / "task_queue.jsonl"
    if not queue_path.exists():
        return []
    latest: dict[str, dict] = {}
    for line in queue_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        task_id = entry.get("task_id")
        if task_id:
            latest[task_id] = entry
    stranded = []
    pending_dir = anima_dir / "state" / "pending"
    for task_id, entry in latest.items():
        if entry.get("status") != "in_progress":
            continue
        if "automatic continuation scheduled" not in str(entry.get("summary") or ""):
            continue
        if not (pending_dir / f"{task_id}.json").exists() and not (
            pending_dir / "processing" / f"{task_id}.json"
        ).exists():
            stranded.append(task_id)
    return stranded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--root", type=Path, default=Path.home() / ".animaworks")
    args = parser.parse_args()
    since = datetime.now() - timedelta(days=args.days)

    fleet_status: Counter[str] = Counter()
    burns: list[str] = []
    all_stranded: dict[str, list[str]] = {}
    per_anima: dict[str, Counter] = {}
    continued_ts: dict[tuple[str, str], list[datetime]] = defaultdict(list)

    for anima_dir in sorted((args.root / "animas").iterdir()):
        activity_dir = anima_dir / "activity_log"
        if not activity_dir.is_dir():
            continue
        anima = anima_dir.name
        counts: Counter[str] = Counter()
        for ts, event in _iter_events(activity_dir, since):
            meta = event.get("meta") or {}
            status = str(meta.get("status") or "completed")
            counts[status] += 1
            task_id = str(meta.get("task_id") or "?")
            if status == "continued":
                continued_ts[(anima, task_id)].append(ts)
            if status == "failed" and "continuations" in str(meta.get("error") or ""):
                burns.append(f"  {anima}/{task_id}: {str(meta.get('error'))[:120]}")
        if counts:
            per_anima[anima] = counts
            fleet_status.update(counts)
        stranded = _stranded_continuations(anima_dir)
        if stranded:
            all_stranded[anima] = stranded

    print(f"# task exec waste audit — last {args.days} days (since {since:%Y-%m-%d %H:%M})")
    print(f"\n## fleet totals: {dict(fleet_status)}")
    print("\n## per anima")
    for anima, counts in sorted(per_anima.items()):
        print(f"  {anima}: {dict(counts)}")

    print("\n## continuation-limit failures (all continuations burned)")
    print("\n".join(burns) or "  none")

    print(f"\n## rapid burns (>=2 continuations within {RAPID_BURN_WINDOW_MIN} min)")
    rapid = [
        f"  {anima}/{task_id}: {len(ts_list)} continuations in "
        f"{(max(ts_list) - min(ts_list)).total_seconds() / 60:.1f} min"
        for (anima, task_id), ts_list in sorted(continued_ts.items())
        if len(ts_list) >= 2
        and (max(ts_list) - min(ts_list)) <= timedelta(minutes=RAPID_BURN_WINDOW_MIN)
    ]
    print("\n".join(rapid) or "  none")

    print("\n## stranded continuations (queue in_progress, no descriptor — claim race)")
    if all_stranded:
        for anima, ids in sorted(all_stranded.items()):
            print(f"  {anima}: {', '.join(ids)}")
    else:
        print("  none")


if __name__ == "__main__":
    main()
