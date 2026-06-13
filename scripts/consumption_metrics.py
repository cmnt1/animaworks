"""consumption_metrics.py — append-only consumption ledger for GEN-019 Phase 3.

Why this exists
---------------
GEN-019 keeps re-discovering the same failure mode: a memory store is written to
faithfully but nothing downstream *consumes* it (NotebookLM reflex-recall is dead;
TaskDiary candidates were lost 100% before Phase 2). Neither store has a native
consumption history, so "did this get used?" can only be answered if we log it
ourselves. This module is that ledger.

It appends one JSON object per line to a single shared JSONL so the daily-ops
dashboard can render a per-department, last-N-days time series and flag
zero-streaks (= consumption stopped).

Event vocabulary
----------------
  source   "taskdiary" | "notebooklm"        (which store)
  event    "generated" | "adopted" | "ask"   (stage of the pipeline)
  project  department / project bucket        ("General", "Affiliate", ...)
  count    items represented by this row      (candidates: 1, items: N, asks: 1)

Generated  = taskdiary_promote.py emitted a candidate into _inbox/<P>/.
Adopted    = apply_inbox_decision.py moved a taskdiary-* candidate into runbooks/.
Ask        = a notebooklm ask wrapper fired (Phase 1, not yet wired).

The writer is best-effort: logging must NEVER break the pipeline, so all errors
are swallowed. Readers tolerate malformed lines.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

JST = timezone(timedelta(hours=9))

# Event vocabulary (closed set — see module docstring). Producers import these
# instead of raw strings so a typo can't silently mis-bucket a row off the
# dashboard this ledger exists to feed.
SOURCE_TASKDIARY = "taskdiary"
SOURCE_NOTEBOOKLM = "notebooklm"
EVENT_GENERATED = "generated"
EVENT_ADOPTED = "adopted"
EVENT_ASK = "ask"
EVENT_ORDER = (EVENT_GENERATED, EVENT_ADOPTED, EVENT_ASK)

# Single shared ledger next to the other daily-ops runner logs so the dashboard
# can read it without a new mount point.
LEDGER_PATH = Path(
    r"E:\OneDriveBiz\Tools\General\daily-ops-dashboard\logs\consumption_metrics.jsonl"
)


def log_event(
    *,
    source: str,
    event: str,
    project: str,
    count: int = 1,
    day: str | None = None,
    extra: dict[str, Any] | None = None,
    path: Path | None = None,
) -> None:
    """Append one ledger row. Best-effort: never raises."""
    try:
        now = datetime.now(JST)
        row: dict[str, Any] = {
            "ts": now.isoformat(),
            "date": day or now.date().isoformat(),
            "source": source,
            "event": event,
            "project": project,
            "count": int(count),
        }
        if extra:
            row.update(extra)
        target = path or LEDGER_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        # Logging must not break the consuming pipeline.
        pass


def read_rows(path: Path | None = None) -> list[dict[str, Any]]:
    """Read all ledger rows, skipping malformed lines."""
    target = path or LEDGER_PATH
    rows: list[dict[str, Any]] = []
    if not target.exists():
        return rows
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def aggregate(
    rows: Iterable[dict[str, Any]],
    *,
    days: int = 7,
    today: str | None = None,
) -> dict[str, Any]:
    """Aggregate rows into a per-date × per-project × event matrix for the last N days.

    Returns:
        {
          "dates": ["2026-06-04", ..., "2026-06-10"],   # oldest→newest
          "projects": ["Accounting", ...],               # sorted, seen in window
          "events": ["generated", "adopted", "ask"],
          "cells": { "<date>": { "<project>": { "<event>": count } } },
          "totals": { "<event>": count },
        }
    """
    end = datetime.fromisoformat(today).date() if today else datetime.now(JST).date()
    window = [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    window_set = set(window)

    cells: dict[str, dict[str, dict[str, int]]] = {d: {} for d in window}
    projects: set[str] = set()
    events: set[str] = set()
    totals: dict[str, int] = {}

    # Reducer is max-per-(date,project,event), not sum: the ledger is append-only
    # and the same candidate is re-logged on every (idempotent) re-run/backfill.
    # The latest snapshot's item count is the truth, so max dedups re-runs while
    # still growing if a day's diary later gained more items.
    for r in rows:
        d = r.get("date")
        if d not in window_set:
            continue
        project = r.get("project") or "General"
        event = r.get("event") or EVENT_GENERATED
        count = int(r.get("count") or 0)
        projects.add(project)
        events.add(event)
        cells[d].setdefault(project, {})
        prev = cells[d][project].get(event, 0)
        cells[d][project][event] = max(prev, count)

    # totals recomputed from the deduped cells
    for d in window:
        for project, evmap in cells[d].items():
            for event, count in evmap.items():
                totals[event] = totals.get(event, 0) + count

    # stable event ordering: pipeline stage order, then any extras
    order = list(EVENT_ORDER)
    ordered_events = [e for e in order if e in events] + sorted(events - set(order))

    return {
        "dates": window,
        "projects": sorted(projects),
        "events": ordered_events,
        "cells": cells,
        "totals": totals,
    }
