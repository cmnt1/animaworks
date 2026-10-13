# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for host-side delivery of completed enclave jobs."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from server import enclave_delivery as host_delivery


def _client_config(allowed_animas: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(socket_path="/tmp/enclave.sock", allowed_animas=allowed_animas or [])


def _mock_gateway(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    monkeypatch.setattr(
        host_delivery.httpx,
        "HTTPTransport",
        lambda **kwargs: httpx.MockTransport(handler),
    )


def _jobs_response(request: httpx.Request, jobs: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={"jobs": jobs}, request=request)


def test_delivers_job_to_allowed_anima_inbox_and_acknowledges(
    data_dir: Path,
    make_anima: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_anima("worker")
    requests: list[tuple[str, str]] = []
    job = {
        "job_id": "job-1",
        "from_anima": "worker",
        "case_id": "case-1",
        "status": "done",
        "facts": [{"fact": "A masked fact", "evidence": ["record:1"]}],
        "audit_id": "audit-1",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/v1/jobs":
            return _jobs_response(request, [job])
        if request.method == "POST" and request.url.path == "/v1/ask/job-1/ack":
            return httpx.Response(200, json={"ok": True}, request=request)
        return httpx.Response(404, request=request)

    _mock_gateway(monkeypatch, handler)
    shared_dir = data_dir / "shared"

    delivered = host_delivery.deliver_undelivered_once(
        {"data": _client_config(["worker"])},
        {"worker"},
        shared_dir,
    )

    assert delivered == 1
    inbox_files = list((shared_dir / "inbox" / "worker").glob("*.json"))
    assert len(inbox_files) == 1
    message = json.loads(inbox_files[0].read_text(encoding="utf-8"))
    assert message["from_person"] == "enclave-data"
    assert message["to_person"] == "worker"
    assert message["source"] == "human"
    assert message["intent"] == "report"
    assert "case_id: case-1" in message["content"]
    assert "job_id: job-1" in message["content"]
    assert "A masked fact" in message["content"]
    assert "record:1" in message["content"]
    assert "audit-1" in message["content"]
    assert requests == [
        ("GET", "/v1/jobs"),
        ("POST", "/v1/ask/job-1/ack"),
    ]


def test_delivery_exception_does_not_acknowledge_job(
    data_dir: Path,
    make_anima: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_anima("worker")
    ack_calls: list[str] = []
    job = {
        "job_id": "job-2",
        "from_anima": "worker",
        "case_id": "case-2",
        "status": "done",
        "facts": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _jobs_response(request, [job])
        ack_calls.append(request.url.path)
        return httpx.Response(200, request=request)

    class _FailingMessenger:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def send(self, **kwargs: Any) -> None:
            raise OSError("inbox unavailable")

    _mock_gateway(monkeypatch, handler)
    monkeypatch.setattr(host_delivery, "Messenger", _FailingMessenger)

    delivered = host_delivery.deliver_undelivered_once(
        {"data": _client_config(["worker"])},
        {"worker"},
        data_dir / "shared",
    )

    assert delivered == 0
    assert ack_calls == []


def test_disallowed_or_missing_host_anima_is_not_delivered_and_is_acknowledged(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ack_calls: list[str] = []
    job = {
        "job_id": "job-3",
        "from_anima": "not-allowed",
        "case_id": "case-3",
        "status": "failed",
        "error": "entry_unavailable",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _jobs_response(request, [job])
        ack_calls.append(request.url.path)
        return httpx.Response(200, request=request)

    _mock_gateway(monkeypatch, handler)
    delivered = host_delivery.deliver_undelivered_once(
        {"data": _client_config(["worker"])},
        {"worker"},
        data_dir / "shared",
    )

    assert delivered == 0
    assert ack_calls == ["/v1/ask/job-3/ack"]
    assert not (data_dir / "shared" / "inbox" / "worker").exists()


def test_enclave_mode_does_not_start_host_delivery() -> None:
    config = SimpleNamespace(
        enclave=SimpleNamespace(enabled=True),
        enclaves={"data": _client_config(["worker"])},
    )
    assert host_delivery.should_start_host_delivery(config) is False


def test_host_delivery_starts_only_when_host_has_enclave_clients() -> None:
    enclave_mode = SimpleNamespace(enclave=SimpleNamespace(enabled=True), enclaves={"data": object()})
    empty_host = SimpleNamespace(enclave=SimpleNamespace(enabled=False), enclaves={})
    configured_host = SimpleNamespace(enclave=SimpleNamespace(enabled=False), enclaves={"data": object()})

    assert host_delivery.should_start_host_delivery(enclave_mode) is False
    assert host_delivery.should_start_host_delivery(empty_host) is False
    assert host_delivery.should_start_host_delivery(configured_host) is True
