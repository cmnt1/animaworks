# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for host-side enclave ask job tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from core.config import invalidate_cache
from core.integrations import enclave as enclave_mod
from tests.helpers.filesystem import DEFAULT_TEST_CONFIG


def _write_config(data_dir: Path, enclaves: dict[str, Any]) -> None:
    config = dict(DEFAULT_TEST_CONFIG)
    config["enclaves"] = enclaves
    (data_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    invalidate_cache()


def _mock_http(
    monkeypatch: pytest.MonkeyPatch,
    handler: Any,
) -> list[str]:
    sockets: list[str] = []

    def _transport(*, uds: str) -> httpx.MockTransport:
        sockets.append(uds)
        return httpx.MockTransport(handler)

    monkeypatch.setattr(enclave_mod.httpx, "HTTPTransport", _transport)
    return sockets


def _config(data_dir: Path, *, allowed_animas: list[str] | None = None, timeout_s: int = 900) -> None:
    _write_config(
        data_dir,
        {
            "data": {
                "socket_path": "/tmp/enclave.sock",
                "allowed_animas": allowed_animas if allowed_animas is not None else ["worker"],
                "timeout_s": timeout_s,
            }
        },
    )


def test_ask_returns_job_id_immediately_and_points_to_status_and_inbox(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/v1/ask"
        assert json.loads(request.content)["question"] == "question text"
        return httpx.Response(202, json={"job_id": "job-123", "status": "queued"}, request=request)

    sockets = _mock_http(monkeypatch, handler)
    _config(data_dir)

    result = enclave_mod.dispatch(
        "enclave_ask",
        {
            "enclave": "data",
            "question": "question text",
            "case_id": "case-1",
            "anima_dir": "/animas/worker",
        },
    )

    assert len(requests) == 1
    assert sockets == ["/tmp/enclave.sock"]
    assert "job-123" in result
    assert "queued" in result
    assert "animaworks-tool enclave status --enclave data --job-id job-123" in result
    assert "inbox" in result
    body = json.loads(requests[0].content)
    assert body["from_anima"] == "worker"
    assert body["case_id"] == "case-1"


def test_ask_wait_polls_until_done_and_formats_facts(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_count = 0
    get_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal get_count
        if request.method == "POST":
            return httpx.Response(202, json={"job_id": "job-456", "status": "queued"}, request=request)
        get_count += 1
        get_queries.append(request.url.params.get("from_anima", ""))
        if get_count == 1:
            return httpx.Response(200, json={"job_id": "job-456", "status": "running"}, request=request)
        return httpx.Response(
            200,
            json={
                "job_id": "job-456",
                "case_id": "case-2",
                "status": "done",
                "facts": [{"fact": "A completed fact", "evidence": ["record:7"]}],
                "audit_id": "audit-456",
            },
            request=request,
        )

    _mock_http(monkeypatch, handler)
    monkeypatch.setattr(enclave_mod.time, "sleep", lambda seconds: None)
    _config(data_dir)

    result = enclave_mod.dispatch(
        "enclave_ask",
        {
            "enclave": "data",
            "question": "question text",
            "anima_dir": "/animas/worker",
            "wait_s": 20,
        },
    )

    assert get_count == 2
    assert get_queries == ["worker", "worker"]
    assert "A completed fact" in result
    assert "record:7" in result
    assert "audit_id: audit-456" in result
    assert "job-456" not in result


def test_status_formats_progress_and_facts(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "job_id": "job-789",
                "case_id": "case-3",
                "status": "done",
                "queued_ahead": 2,
                "elapsed_s": 12.5,
                "last_activity_at": "2026-10-13T10:00:00Z",
                "progress": [{"at": f"time-{index}", "text": f"progress-{index}"} for index in range(6)],
                "facts": [{"fact": "Status fact", "evidence": ["record:9"]}],
                "audit_id": "audit-789",
            },
            request=request,
        )

    _mock_http(monkeypatch, handler)
    _config(data_dir)

    result = enclave_mod.dispatch(
        "enclave_status",
        {"enclave": "data", "job_id": "job-789", "anima_dir": "/animas/worker"},
    )

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/ask/job-789"
    assert requests[0].url.params["from_anima"] == "worker"
    assert "running" not in result
    assert "progress-0" not in result
    for index in range(1, 6):
        assert f"progress-{index}" in result
    assert "12.5s" in result
    assert "2" in result
    assert "Status fact" in result
    assert "record:9" in result
    assert "audit_id: audit-789" in result


def test_cancel_sends_delete(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"job_id": "job-cancel", "status": "cancelled"}, request=request)

    _mock_http(monkeypatch, handler)
    _config(data_dir)

    result = enclave_mod.dispatch(
        "enclave_cancel",
        {"enclave": "data", "job_id": "job-cancel", "anima_dir": "/animas/worker"},
    )

    assert len(requests) == 1
    assert requests[0].method == "DELETE"
    assert requests[0].url.path == "/v1/ask/job-cancel"
    assert requests[0].url.params["from_anima"] == "worker"
    assert "cancelled" in result


def test_http_uses_short_timeout_instead_of_job_timeout(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.Client
    seen: dict[str, Any] = {}

    def client_factory(**kwargs: Any) -> httpx.Client:
        seen.update(kwargs)
        return real_client(**kwargs)

    monkeypatch.setattr(enclave_mod.httpx, "Client", client_factory)
    _mock_http(
        monkeypatch,
        lambda request: httpx.Response(202, json={"job_id": "short", "status": "queued"}, request=request),
    )
    _config(data_dir, timeout_s=900)

    enclave_mod.dispatch(
        "enclave_ask",
        {"enclave": "data", "question": "q", "anima_dir": "/animas/worker"},
    )

    assert seen["timeout"] == 30.0


def test_allowed_animas_remains_fail_closed(data_dir: Path) -> None:
    _config(data_dir, allowed_animas=[])
    result = enclave_mod.dispatch(
        "enclave_ask",
        {"enclave": "data", "question": "q", "anima_dir": "/animas/worker"},
    )
    assert "許可" in result or "allowed" in result


def test_status_and_cancel_also_enforce_allowed_animas(data_dir: Path) -> None:
    _config(data_dir, allowed_animas=["worker"])
    args = {"enclave": "data", "job_id": "job-1", "anima_dir": "/animas/other"}

    assert "許可" in enclave_mod.dispatch("enclave_status", args)
    assert "許可" in enclave_mod.dispatch("enclave_cancel", args)


def test_unknown_enclave_and_missing_socket(data_dir: Path) -> None:
    _write_config(data_dir, {})
    unknown = enclave_mod.dispatch(
        "enclave_ask",
        {"enclave": "missing", "question": "q", "anima_dir": "/animas/worker"},
    )
    assert "missing" in unknown

    _config(data_dir)
    # No mock transport: a nonexistent Unix socket is caught and reported.
    result = enclave_mod.dispatch(
        "enclave_ask",
        {"enclave": "data", "question": "q", "anima_dir": "/animas/worker"},
    )
    assert "接続" in result or "reach" in result


def test_default_case_id_is_safe() -> None:
    from core.integrations.enclave import _safe_case_id

    value = _safe_case_id("anima-name!!" * 20)
    assert "-" in value
    assert len(value) <= 64
    assert all(c.isalnum() or c in "_.-" for c in value)


def test_schemas_register_ask_status_and_cancel() -> None:
    schemas = enclave_mod.get_tool_schemas()
    assert [schema["name"] for schema in schemas] == ["enclave_ask", "enclave_status", "enclave_cancel"]
    ask_properties = schemas[0]["input_schema"]["properties"]
    assert ask_properties["wait_s"]["type"] == "integer"


def test_cli_maps_subcommands_to_tool_schemas(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(enclave_mod, "dispatch", lambda name, args: calls.append((name, args)) or "ok")
    monkeypatch.setattr("core.platform.env.anima_dir_env", lambda: "/animas/worker")

    enclave_mod.cli_main(["ask", "--enclave", "data", "--question", "q", "--wait", "15"])
    enclave_mod.cli_main(["status", "--enclave", "data", "--job-id", "job-1"])
    enclave_mod.cli_main(["cancel", "--enclave", "data", "--job-id", "job-2"])

    assert calls[0] == (
        "enclave_ask",
        {"enclave": "data", "anima_dir": "/animas/worker", "question": "q", "case_id": "", "wait_s": 15},
    )
    assert calls[1] == ("enclave_status", {"enclave": "data", "anima_dir": "/animas/worker", "job_id": "job-1"})
    assert calls[2] == ("enclave_cancel", {"enclave": "data", "anima_dir": "/animas/worker", "job_id": "job-2"})
    assert capsys.readouterr().out.count("ok") == 3
