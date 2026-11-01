# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the enclave gateway ``GET /v1/usage`` endpoint."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from core.time_utils import today_local
from tests.unit.enclave.test_gateway import FakeSupervisor, _running_gateway

_BUDGET = {"month": "2026-10", "budget": 1000, "consumed": 150, "remaining": 850, "exceeded": False}


def _write_usage(anima_dir: Path, *, sessions: int = 2, input_tokens: int = 100) -> None:
    """Write a single token-usage JSONL file for today under *anima_dir*."""
    usage_dir = anima_dir / "token_usage"
    usage_dir.mkdir(parents=True, exist_ok=True)
    today = today_local().isoformat()
    entries = []
    for i in range(sessions):
        entries.append(
            {
                "ts": f"{today}T12:0{i}:00",
                "model": "claude-sonnet-5",
                "trigger": "chat",
                "input_tokens": input_tokens,
                "output_tokens": 50,
                "total_tokens": input_tokens + 50,
                "estimated_cost_usd": 0.001,
                "pricing_status": "estimated",
            }
        )
    (usage_dir / f"{today}.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n",
        encoding="utf-8",
    )


def _reader(anima_dir: Path, days: int) -> dict:
    """Mirror of the server-layer reader injected into the gateway."""
    import core.usage.token_budget
    from core.usage.token_usage import TokenUsageLogger

    summary = TokenUsageLogger(anima_dir).summarize(days)
    summary.update(core.usage.token_budget.read_budget_fields(anima_dir))
    return summary


def _patch_budget():
    import core.usage.token_budget

    return patch.object(core.usage.token_budget, "read_budget_fields", return_value=dict(_BUDGET))


async def test_usage_allowed_peer_returns_summary(tmp_path: Path) -> None:
    _write_usage(tmp_path / "animas" / "momo")
    _write_usage(tmp_path / "animas" / "second")
    with _patch_budget():
        async with _running_gateway(tmp_path, FakeSupervisor("{}"), usage_reader=_reader) as (client, _sup):
            resp = await client.get("http://enclave/v1/usage?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "test"
    assert body["days"] == 30
    assert set(body["animas"]) == {"momo", "second"}
    momo = body["animas"]["momo"]
    assert momo["total_sessions"] == 2
    assert momo["total_input_tokens"] == 200
    assert momo["budget"] == 1000
    # No conversation text leaks into the usage payload.
    assert "question" not in momo and "case_id" not in momo


async def test_usage_single_anima(tmp_path: Path) -> None:
    _write_usage(tmp_path / "animas" / "momo")
    _write_usage(tmp_path / "animas" / "other")
    with _patch_budget():
        async with _running_gateway(tmp_path, FakeSupervisor("{}"), usage_reader=_reader) as (client, _sup):
            resp = await client.get("http://enclave/v1/usage?days=14&anima=momo")
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 14
    assert set(body["animas"]) == {"momo"}


async def test_usage_single_anima_not_found(tmp_path: Path) -> None:
    _write_usage(tmp_path / "animas" / "momo")
    with _patch_budget():
        async with _running_gateway(tmp_path, FakeSupervisor("{}"), usage_reader=_reader) as (client, _sup):
            resp = await client.get("http://enclave/v1/usage?days=30&anima=ghost")
    assert resp.status_code == 404


async def test_usage_invalid_anima_name(tmp_path: Path) -> None:
    _write_usage(tmp_path / "animas" / "momo")
    with _patch_budget():
        async with _running_gateway(tmp_path, FakeSupervisor("{}"), usage_reader=_reader) as (client, _sup):
            for bad in ("../momo", "a/b", "a\\b"):
                resp = await client.get("http://enclave/v1/usage?days=30&anima=" + bad)
                assert resp.status_code == 400, bad


async def test_usage_invalid_days(tmp_path: Path) -> None:
    with _patch_budget():
        async with _running_gateway(tmp_path, FakeSupervisor("{}"), usage_reader=_reader) as (client, _sup):
            for bad_days in (0, 367, -5):
                resp = await client.get(f"http://enclave/v1/usage?days={bad_days}")
                assert resp.status_code == 400, bad_days


async def test_usage_unauthorized_peer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import core.enclave.gateway as gateway_mod

    monkeypatch.setattr(gateway_mod, "_request_uid", lambda request: os.getuid() + 9999)
    with _patch_budget():
        async with _running_gateway(tmp_path, FakeSupervisor("{}"), usage_reader=_reader) as (client, _sup):
            resp = await client.get("http://enclave/v1/usage?days=30")
    assert resp.status_code == 403
    assert resp.json() == {"error": "unauthorized_peer"}


async def test_usage_without_reader_is_unavailable(tmp_path: Path) -> None:
    _write_usage(tmp_path / "animas" / "momo")
    async with _running_gateway(tmp_path, FakeSupervisor("{}")) as (client, _sup):
        resp = await client.get("http://enclave/v1/usage?days=30")
    assert resp.status_code == 503
