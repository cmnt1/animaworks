from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cli.commands.cost_cmd import _fmt_cost, cmd_cost
from core.i18n import t
from core.integrations.enclave import EnclavePermissionError, EnclaveUnreachable


def _usage_summary(*, sessions: int = 0, **kw) -> dict:
    base = {
        "period_days": 30,
        "total_sessions": sessions,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cache_write_tokens": 0,
        "total_tokens": 0,
        "total_estimated_cost_usd": 0.0,
        "unknown_pricing_sessions": 0,
        "cost_is_partial": False,
        "by_model": {},
        "by_trigger": {},
        "by_date": {},
    }
    base.update(kw)
    return base


def _args(*, anima: str | None = None, json_output: bool = False) -> argparse.Namespace:
    return argparse.Namespace(anima=anima, days=30, today=False, json_output=json_output)


def test_unknown_pricing_is_not_displayed_as_free() -> None:
    text = _fmt_cost(0.0, 5, 5)
    assert text == t("cost.unknown_pricing", count=5)
    assert "$0.0000" not in text


def test_mixed_pricing_explicitly_marks_incomplete_total() -> None:
    assert _fmt_cost(1.25, 2, 5) == t("cost.partial_pricing", cost="$1.2500", count=2)
    assert _fmt_cost(1.25, 0, 5) == "$1.2500"


def test_cost_json_includes_monthly_budget_fields_for_every_anima(tmp_path, capsys) -> None:
    data_dir = tmp_path / "data"
    alice = data_dir / "animas" / "alice"
    bob = data_dir / "animas" / "bob"
    alice.mkdir(parents=True)
    bob.mkdir(parents=True)
    (alice / "token_usage").mkdir()
    (bob / "token_usage").mkdir()

    def budget_status(anima_dir, *, now):
        if anima_dir.name == "alice":
            return SimpleNamespace(budget=1_000, consumed=1_100, remaining=0, exceeded=True)
        return SimpleNamespace(budget=None, consumed=25, remaining=None, exceeded=False)

    with (
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.usage.token_budget.read_token_budget_status", side_effect=budget_status),
    ):
        cmd_cost(_args(json_output=True))

    result = json.loads(capsys.readouterr().out)
    assert {key: result["alice"][key] for key in ("budget", "consumed", "remaining", "exceeded")} == {
        "budget": 1_000,
        "consumed": 1_100,
        "remaining": 0,
        "exceeded": True,
    }
    assert result["bob"]["budget"] is None
    assert result["bob"]["consumed"] == 25
    assert result["bob"]["remaining"] is None
    assert result["bob"]["exceeded"] is False


def test_cost_text_displays_unlimited_budget_as_dash(tmp_path, capsys) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "alice"
    anima_dir.mkdir(parents=True)
    status = SimpleNamespace(budget=None, consumed=25, remaining=None, exceeded=False)

    with (
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.usage.token_budget.read_token_budget_status", return_value=status),
    ):
        cmd_cost(_args(anima="alice"))

    output = capsys.readouterr().out
    assert "Monthly budget: -" in output
    assert "Consumed: 25" in output
    assert "Remaining: -" in output
    assert "Exceeded: no" in output


def test_cost_all_preserves_unconfigured_zero_usage_filter(tmp_path, capsys) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "alice"
    anima_dir.mkdir(parents=True)

    with (
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.config.model_config.load_model_config", return_value=SimpleNamespace(token_budget_monthly=None)),
    ):
        cmd_cost(_args())

    assert capsys.readouterr().out.strip() == "No token usage data found. Start the server and send some messages."
    assert not (anima_dir / "token_usage").exists()


def test_cost_single_from_enclave(tmp_path, capsys) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "animas").mkdir(parents=True)
    summary = _usage_summary(
        sessions=2,
        total_input_tokens=100,
        total_output_tokens=50,
        total_tokens=150,
        total_estimated_cost_usd=0.0012,
        month="2026-10",
        budget=None,
        consumed=150,
        remaining=None,
        exceeded=False,
    )
    data = {"name": "saas-data", "days": 30, "animas": {"momo": summary}}
    config = SimpleNamespace(enclaves={"saas-data": SimpleNamespace()})
    with (
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.config.load_config", return_value=config),
        patch("core.integrations.enclave.fetch_enclave_usage", return_value=data),
    ):
        cmd_cost(_args(anima="momo"))
    out = capsys.readouterr().out
    assert "momo (enclave: saas-data)" in out
    assert "Estimated cost: $0.0012" in out


def test_cost_single_nowhere_errors(tmp_path, capsys) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "animas").mkdir(parents=True)
    config = SimpleNamespace(enclaves={"saas-data": SimpleNamespace()})
    with (
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.config.load_config", return_value=config),
        patch("core.integrations.enclave.fetch_enclave_usage", return_value=None),
        pytest.raises(SystemExit) as exc,
    ):
        cmd_cost(_args(anima="momo"))
    assert exc.value.code == 1
    assert "not found" in capsys.readouterr().out


def test_cost_single_permission_guide(tmp_path, capsys) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "animas").mkdir(parents=True)
    config = SimpleNamespace(enclaves={"saas-data": SimpleNamespace()})
    err = EnclavePermissionError("saas-data")
    with (
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.config.load_config", return_value=config),
        patch("core.integrations.enclave.fetch_enclave_usage", side_effect=err),
        pytest.raises(SystemExit) as exc,
    ):
        cmd_cost(_args(anima="momo"))
    assert exc.value.code == 1
    assert "animaworks-enclave" in capsys.readouterr().out


def test_cost_all_includes_enclave_skips_unreachable(tmp_path, capsys) -> None:
    data_dir = tmp_path / "data"
    local = data_dir / "animas" / "local1"
    (local / "token_usage").mkdir(parents=True)

    summary = _usage_summary(
        sessions=1,
        total_input_tokens=10,
        total_output_tokens=5,
        total_tokens=15,
        total_estimated_cost_usd=0.0002,
        month="2026-10",
        budget=None,
        consumed=15,
        remaining=None,
        exceeded=False,
    )
    data = {"name": "reachable", "days": 30, "animas": {"momo": summary}}

    def fake_fetch(enclave_name, cfg, days, anima=None):
        if enclave_name == "reachable":
            return data
        raise EnclaveUnreachable("unreachable")

    config = SimpleNamespace(enclaves={"reachable": SimpleNamespace(), "unreachable": SimpleNamespace()})
    budget_status = SimpleNamespace(budget=None, consumed=0, remaining=None, exceeded=False)
    with (
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.config.load_config", return_value=config),
        patch("core.integrations.enclave.fetch_enclave_usage", side_effect=fake_fetch),
        patch("core.usage.token_budget.read_token_budget_status", return_value=budget_status),
    ):
        cmd_cost(_args(json_output=True))
    out, err = capsys.readouterr()
    result = json.loads(out)
    assert "local1" in result
    assert "momo@reachable" in result
    assert "unreachable" in err
