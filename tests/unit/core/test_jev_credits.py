"""Jev prepaid-credit accounting: ledger aggregation and dashboard status."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from core.config.models import JevConfig
from core.jev_credits import build_status, month_start, next_month_start, parse_ts, read_spend
from core.time_utils import get_app_timezone


def _at(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=get_app_timezone())


def _write(ledger_dir: Path, month: str, rows: list[dict[str, object]]) -> None:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    path = ledger_dir / f"{month}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _row(ts: datetime, *, input_tokens: int = 1000, cost: float | None = None) -> dict[str, object]:
    row: dict[str, object] = {
        "ts": ts.isoformat(),
        "model": "jev-1.13.0",
        "input_tokens": input_tokens,
        "output_tokens": 20,
    }
    if cost is not None:
        row["cost_usd"] = cost
    return row


def test_read_spend_sums_recorded_cost(tmp_path: Path):
    _write(tmp_path, "2026-09", [_row(_at(2026, 9, 3), cost=0.25), _row(_at(2026, 9, 4), cost=0.75)])

    spend = read_spend(tmp_path)

    assert spend.cost_usd == 1.0
    assert spend.calls == 2
    assert spend.input_tokens == 2000
    assert spend.output_tokens == 40


def test_read_spend_prices_rows_without_cost(tmp_path: Path):
    """A row with no cost_usd is priced with the configured rates."""
    _write(tmp_path, "2026-09", [_row(_at(2026, 9, 3), input_tokens=1_000_000)])

    spend = read_spend(tmp_path, input_usd_per_mtok=0.042, output_usd_per_mtok=0.0)

    assert spend.cost_usd == 0.042


def test_read_spend_honours_recorded_cost_over_current_price(tmp_path: Path):
    """Historical rows keep the price that applied when the call was made."""
    _write(tmp_path, "2026-09", [_row(_at(2026, 9, 3), input_tokens=1_000_000, cost=0.010)])

    spend = read_spend(tmp_path, input_usd_per_mtok=99.0)

    assert spend.cost_usd == 0.010


def test_read_spend_filters_by_range_across_months(tmp_path: Path):
    _write(tmp_path, "2026-08", [_row(_at(2026, 8, 30), cost=5.0)])
    _write(tmp_path, "2026-09", [_row(_at(2026, 9, 2), cost=1.0), _row(_at(2026, 9, 20), cost=2.0)])
    _write(tmp_path, "2026-10", [_row(_at(2026, 10, 1), cost=7.0)])

    spend = read_spend(tmp_path, since=_at(2026, 9, 10), until=_at(2026, 10, 1))

    assert spend.cost_usd == 2.0
    assert spend.calls == 1


def test_read_spend_skips_malformed_lines_and_undated_boundary_rows(tmp_path: Path):
    ledger = tmp_path / "2026-09.jsonl"
    tmp_path.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps({"ts": _at(2026, 9, 12).isoformat(), "cost_usd": 3.0})
        + "\n"
        + "{not json\n"
        + json.dumps({"cost_usd": 100.0})
        + "\n",  # no ts: cannot be placed inside the range
        encoding="utf-8",
    )

    bounded = read_spend(tmp_path, since=_at(2026, 9, 1), until=_at(2026, 10, 1))
    unbounded = read_spend(tmp_path)

    assert bounded.cost_usd == 3.0
    assert unbounded.cost_usd == 103.0


def test_read_spend_ignores_unrelated_files(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "notes.txt").write_text("nope", encoding="utf-8")
    (tmp_path / "2026-09.jsonl.bak").write_text(json.dumps({"cost_usd": 9.0}) + "\n", encoding="utf-8")
    _write(tmp_path, "2026-09", [_row(_at(2026, 9, 5), cost=1.5)])

    assert read_spend(tmp_path).cost_usd == 1.5


def test_read_spend_on_missing_directory(tmp_path: Path):
    spend = read_spend(tmp_path / "absent")

    assert spend.cost_usd == 0.0
    assert spend.calls == 0


def test_parse_ts_accepts_iso_and_epoch():
    assert parse_ts("2026-09-19T16:38:46+09:00") is not None
    assert parse_ts(1758268726).tzinfo is not None
    assert parse_ts("nope") is None
    assert parse_ts(None) is None
    # A naive stamp is read in the app timezone rather than rejected.
    assert parse_ts("2026-09-19T16:38:46").tzinfo is not None


def test_month_boundaries_span_december():
    assert month_start(_at(2026, 12, 19)).isoformat().startswith("2026-12-01T00:00:00")
    assert next_month_start(_at(2026, 12, 19)).isoformat().startswith("2027-01-01T00:00:00")


class _Config:
    def __init__(self, jev: JevConfig):
        self.jev = jev


def test_build_status_derives_balance_and_budget_bar(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEV_USAGE_LEDGER_DIR", str(tmp_path))
    now = _at(2026, 9, 19)
    # Before the baseline reading: counts against the month, not the balance.
    _write(tmp_path, "2026-09", [_row(_at(2026, 9, 2), cost=1.0)])
    _write(tmp_path, "2026-09", [_row(_at(2026, 9, 15), cost=2.0), _row(_at(2026, 9, 18), cost=0.5)])
    cfg = _Config(
        JevConfig(
            monthly_budget_usd=10.0,
            balance_usd=20.0,
            balance_checked_at=_at(2026, 9, 10).isoformat(),
        )
    )

    status = build_status(cfg, now=now)

    assert status["month"]["spend_usd"] == 3.5
    assert status["month"]["budget_usd"] == 10.0
    assert status["month"]["utilization"] == 35.0
    assert status["month"]["window_seconds"] == 30 * 86400
    assert status["balance"]["spent_since_usd"] == 2.5
    assert status["balance"]["balance_usd"] == 17.5
    assert status["ledger_present"] is True


def test_build_status_without_budget_still_reports_spend(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEV_USAGE_LEDGER_DIR", str(tmp_path))
    _write(tmp_path, "2026-09", [_row(_at(2026, 9, 5), cost=0.25)])

    status = build_status(_Config(JevConfig()), now=_at(2026, 9, 19))

    assert status["month"]["utilization"] is None
    assert status["month"]["spend_usd"] == 0.25
    assert status["balance"] is None


def test_build_status_without_checked_at_subtracts_nothing(tmp_path: Path, monkeypatch):
    """A baseline with no reading time is taken as current — nothing to deduct."""
    monkeypatch.setenv("JEV_USAGE_LEDGER_DIR", str(tmp_path))
    _write(tmp_path, "2026-09", [_row(_at(2026, 9, 5), cost=4.0)])

    status = build_status(_Config(JevConfig(balance_usd=12.0)), now=_at(2026, 9, 19))

    assert status["balance"]["balance_usd"] == 12.0
    assert status["balance"]["spent_since_usd"] == 0.0
    assert status["balance"]["checked_at"] is None


def test_build_status_reports_no_credentials_when_unconfigured(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEV_USAGE_LEDGER_DIR", str(tmp_path / "absent"))
    monkeypatch.setenv("ANIMAWORKS_JEV_SECRETS_PATH", str(tmp_path / "no_secrets.py"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    status = build_status(_Config(JevConfig()), now=_at(2026, 9, 19))

    assert status["error"] == "no_credentials"


def test_build_status_shows_numbers_once_a_budget_exists(tmp_path: Path, monkeypatch):
    """A configured budget is enough to show the card, key or not."""
    monkeypatch.setenv("JEV_USAGE_LEDGER_DIR", str(tmp_path / "absent"))
    monkeypatch.setenv("ANIMAWORKS_JEV_SECRETS_PATH", str(tmp_path / "no_secrets.py"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    status = build_status(_Config(JevConfig(monthly_budget_usd=5.0)), now=_at(2026, 9, 19))

    assert "error" not in status
    assert status["credentials"] is False
    assert status["ledger_present"] is False
    assert status["month"]["utilization"] == 0.0


def test_build_status_resets_at_is_the_next_month(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JEV_USAGE_LEDGER_DIR", str(tmp_path))
    now = _at(2026, 9, 19)

    status = build_status(_Config(JevConfig(monthly_budget_usd=1.0)), now=now)

    resets_at = datetime.fromtimestamp(status["month"]["resets_at"], tz=get_app_timezone())
    assert resets_at == _at(2026, 10, 1, 0)
    assert resets_at - timedelta(seconds=status["month"]["window_seconds"]) == _at(2026, 9, 1, 0)
