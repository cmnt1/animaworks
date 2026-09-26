# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Jev (TypeSafe System One) prepaid-credit accounting for the usage dashboard.

Jev sells prepaid credits but exposes no balance endpoint — ``/v1/systemone``
answers with per-call token counts and nothing else — so the balance shown on
the dashboard is *derived*: the baseline the user copied from the TypeSafe
console, minus every ledger row written since that reading.  The month bar
reuses the shape Claude's extra-credit window already uses: spend against a
monthly budget, paced against the month's own clock.

Ledger format — one JSON object per line, appended by every Jev caller (today
``Tools/Affiliate/py_mod/monetize/jev_client.py``) to ``<dir>/YYYY-MM.jsonl``::

    {"ts": "2026-09-19T16:38:46+09:00", "model": "jev-1.13.0",
     "input_tokens": 271, "output_tokens": 20, "cost_usd": 1.138e-05,
     "source": "classify_offers"}

``cost_usd`` wins when present so historical rows keep the price that applied
when the call was made; rows without it are priced with the configured
per-million rates.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.config.jev import jev_api_key, jev_ledger_dir
from core.time_utils import ensure_aware, now_local

logger = logging.getLogger("animaworks.jev_credits")

_LEDGER_NAME_RE = re.compile(r"^(\d{4}-\d{2})\.jsonl$")
_USD_PLACES = 6


@dataclass(frozen=True)
class JevSpend:
    """Aggregated ledger rows over some time range."""

    cost_usd: float = 0.0
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


def _month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(dt: datetime) -> datetime:
    # day=28 + 4 days always lands in the next month, for every month length.
    return month_start(month_start(dt) + timedelta(days=32))


def parse_ts(value: Any) -> datetime | None:
    """Parse a ledger/config timestamp (ISO 8601 or epoch seconds)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(float(value), tz=now_local().tzinfo)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return ensure_aware(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def _row_cost(row: dict[str, Any], input_rate: float, output_rate: float) -> float:
    recorded = row.get("cost_usd")
    if isinstance(recorded, (int, float)) and not isinstance(recorded, bool):
        return float(recorded)
    inp = row.get("input_tokens") or 0
    out = row.get("output_tokens") or 0
    try:
        return (float(inp) * input_rate + float(out) * output_rate) / 1_000_000.0
    except (TypeError, ValueError):
        return 0.0


def _int_field(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def _ledger_files(ledger_dir: Path) -> list[tuple[str, Path]]:
    """Return ``(month_key, path)`` for every ``YYYY-MM.jsonl`` in *ledger_dir*."""
    try:
        entries = list(ledger_dir.iterdir())
    except OSError:
        return []
    found: list[tuple[str, Path]] = []
    for entry in entries:
        match = _LEDGER_NAME_RE.match(entry.name)
        if match and entry.is_file():
            found.append((match.group(1), entry))
    return sorted(found)


def _iter_rows(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue  # a torn append must not void the whole month
                if isinstance(row, dict):
                    yield row
    except OSError:
        logger.warning("Jev ledger unreadable: %s", path, exc_info=True)


def read_spend(
    ledger_dir: Path,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    input_usd_per_mtok: float = 0.042,
    output_usd_per_mtok: float = 0.0,
) -> JevSpend:
    """Sum ledger rows with ``since <= ts < until`` (either bound may be None).

    Rows whose timestamp cannot be parsed are counted only when the whole
    month file sits strictly inside the range, so a malformed row can never
    be charged against a balance it predates.
    """
    since_key = _month_key(since) if since else None
    until_key = _month_key(until) if until else None

    cost = 0.0
    calls = 0
    input_tokens = 0
    output_tokens = 0

    for key, path in _ledger_files(ledger_dir):
        if since_key and key < since_key:
            continue
        if until_key and key > until_key:
            continue
        boundary_month = key in (since_key, until_key)
        for row in _iter_rows(path):
            ts = parse_ts(row.get("ts"))
            if ts is None:
                if boundary_month:
                    continue
            else:
                if since and ts < since:
                    continue
                if until and ts >= until:
                    continue
            cost += _row_cost(row, input_usd_per_mtok, output_usd_per_mtok)
            calls += 1
            input_tokens += _int_field(row, "input_tokens")
            output_tokens += _int_field(row, "output_tokens")

    return JevSpend(
        cost_usd=round(cost, _USD_PLACES),
        calls=calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def build_status(config: Any = None, now: datetime | None = None) -> dict[str, Any]:
    """Build the ``jev`` block of ``GET /api/usage``.

    Returns an ``error`` result only when Jev looks entirely unconfigured (no
    key, no ledger, no budget and no balance) — once any of those exist the
    card shows real numbers, with the missing pieces flagged as such.
    """
    from core.config.models import JevConfig

    if config is None:
        try:
            from core.config.models import load_config

            config = load_config()
        except Exception:
            logger.debug("Jev status: config unavailable", exc_info=True)
    cfg = getattr(config, "jev", None)
    if not isinstance(cfg, JevConfig):
        cfg = JevConfig()

    now = now or now_local()
    ledger_dir = jev_ledger_dir(cfg.ledger_dir)
    has_key = bool(jev_api_key())
    ledger_present = bool(_ledger_files(ledger_dir))

    if not has_key and not ledger_present and cfg.monthly_budget_usd is None and cfg.balance_usd is None:
        return {
            "provider": "jev",
            "error": "no_credentials",
            "message": "Jev API key not found",
            "ledger_dir": str(ledger_dir),
        }

    start = month_start(now)
    end = next_month_start(now)
    spend = read_spend(
        ledger_dir,
        since=start,
        until=end,
        input_usd_per_mtok=cfg.input_usd_per_mtok,
        output_usd_per_mtok=cfg.output_usd_per_mtok,
    )

    budget = cfg.monthly_budget_usd
    utilization = None
    if budget:
        utilization = round(spend.cost_usd / budget * 100.0, 4)
    month: dict[str, Any] = {
        "utilization": utilization,
        "remaining": None if utilization is None else round(100.0 - utilization, 4),
        "resets_at": end.timestamp(),
        "window_seconds": int((end - start).total_seconds()),
        "spend_usd": spend.cost_usd,
        "budget_usd": budget,
        "calls": spend.calls,
        "input_tokens": spend.input_tokens,
        "output_tokens": spend.output_tokens,
        "month": _month_key(now),
    }

    balance: dict[str, Any] | None = None
    if cfg.balance_usd is not None:
        checked_at = parse_ts(cfg.balance_checked_at)
        spent_since = 0.0
        if checked_at is not None:
            spent_since = read_spend(
                ledger_dir,
                since=checked_at,
                input_usd_per_mtok=cfg.input_usd_per_mtok,
                output_usd_per_mtok=cfg.output_usd_per_mtok,
            ).cost_usd
        balance = {
            "balance_usd": round(cfg.balance_usd - spent_since, _USD_PLACES),
            "baseline_usd": cfg.balance_usd,
            "checked_at": checked_at.isoformat() if checked_at else None,
            "spent_since_usd": round(spent_since, _USD_PLACES),
        }

    return {
        "provider": "jev",
        "month": month,
        "balance": balance,
        "credentials": has_key,
        "ledger_present": ledger_present,
        "ledger_dir": str(ledger_dir),
    }
