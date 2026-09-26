"""Listing-run tracking shared by the daily property reports.

A listing run starts on the first observed day a key appears and ends on the
first day its source was observed without it. Days on which a source was not
observed (fetch failure, no capture) are skipped, so they never read as a
withdrawal. A run that starts on the first data day, or after a gap longer than
MAX_OBSERVATION_GAP_DAYS in its source's observations, may have started
earlier: its day count is a floor ("以上").
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from datetime import datetime

# The normal Sun/Mon no-capture gap for minimini is 3 days.
MAX_OBSERVATION_GAP_DAYS = 4

# (date "YYYY-MM-DD", {key: (source, row)}, sources observed that day)
Observation = tuple[str, dict[str, tuple[str, dict]], set[str]]


def days_between(start: str, end: str) -> int:
    return (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days


def days_cell(days: int | None, uncertain: bool, unit: str) -> str:
    if days is None:
        return "-"
    return f"{days}{unit}以上" if uncertain else f"{days}{unit}"


Identity = Callable[[dict], Hashable | None]


def track_listing_runs(
    observations: list[Observation], identity: Identity | None = None
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (open runs, ended runs) keyed by listing key; each run keeps its latest row.

    With `identity`, a new key whose row has the same identity as a run of the
    same source last seen within MAX_OBSERVATION_GAP_DAYS continues that run
    (a portal re-issuing a listing ID): the old run is not reported as ended,
    and the new run records the old keys in `relisted_from` and `relisted_on`.
    """
    runs: dict[str, dict] = {}
    ended: dict[str, dict] = {}
    ended_by_identity: dict[tuple[str, Hashable], str] = {}
    last_observed: dict[str, str] = {}
    for date, items, observed in observations:
        observed = observed | {source for source, _ in items.values()}
        for key in [k for k, run in runs.items() if run["source"] in observed and k not in items]:
            run = ended[key] = {**runs.pop(key), "ended_on": date}
            ident = identity(run["row"]) if identity else None
            if ident is not None:
                ended_by_identity[(run["source"], ident)] = key
        for key, (source, row) in items.items():
            if key in runs:
                runs[key].update(last=date, row=row)
                continue
            ident = identity(row) if identity else None
            old_key = ended_by_identity.pop((source, ident), None) if ident is not None else None
            old = ended.get(old_key) if old_key else None
            if old and days_between(old["last"], date) <= MAX_OBSERVATION_GAP_DAYS:
                del ended[old_key]
                runs[key] = {**old, "last": date, "row": row, "relisted_on": date,
                             "relisted_from": [*old.get("relisted_from", []), old_key]}
                runs[key].pop("ended_on")
                continue
            prev = last_observed.get(source)
            runs[key] = {
                "source": source,
                "start": date,
                "last": date,
                "row": row,
                "start_uncertain": prev is None or days_between(prev, date) > MAX_OBSERVATION_GAP_DAYS,
            }
        for source in observed:
            last_observed[source] = date
    return runs, ended


def classify_listings(history: list[Observation], today: Observation, identity: Identity | None = None) -> dict:
    """Split today's listings into new / continued / unconfirmed / deleted rows with day counts.

    - new / continued: listed today (continued = run started before today,
      including a listing re-issued under a new ID; see track_listing_runs)
    - unconfirmed: open run whose source was not observed today
    - deleted: run whose end was detected today (listing_days = first to last seen)
    """
    date, items, _ = today
    runs, ended = track_listing_runs([*history, today], identity)

    def listed(run: dict) -> dict:
        return {**run["row"], "listing_start": run["start"], "start_uncertain": run["start_uncertain"],
                "listing_day": days_between(run["start"], date) + 1,
                "relisted_from": run.get("relisted_from", []), "relisted_today": run.get("relisted_on") == date}

    def withdrawn(run: dict) -> dict:
        return {**run["row"], "listing_start": run["start"], "start_uncertain": run["start_uncertain"],
                "last_seen": run["last"], "listing_days": days_between(run["start"], run["last"]) + 1}

    return {
        "new_rows": [listed(runs[k]) for k in items if runs[k]["start"] == date],
        "continued_rows": [listed(runs[k]) for k in items if runs[k]["start"] != date],
        "unconfirmed_rows": [listed(run) for k, run in runs.items() if k not in items],
        "deleted_rows": [withdrawn(run) for run in ended.values() if run["ended_on"] == date],
    }
