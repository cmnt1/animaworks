# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the enclave gateway (Unix-socket HTTP ingress)."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn

from core.enclave.config import EnclaveConfig
from core.enclave.gateway import create_gateway_app
from core.enclave.gateway_server import PeerCredHttpProtocol, prepare_socket

_EGRESS = {
    "stages": [
        {"type": "regex_denylist", "patterns": [{"regex": "SECRET", "action": "block"}]},
        {"type": "regex_denylist", "patterns": [{"regex": r"\d{4}-\d{4}", "action": "redact"}]},
    ]
}


class FakeSupervisor:
    """A stand-in for ProcessSupervisor that returns a canned answer."""

    def __init__(self, answer: str, *, delay: float = 0.0, bootstrapping: bool = False) -> None:
        self.answer = answer
        self.delay = delay
        self.bootstrapping = bootstrapping
        self.sent: list[dict] = []
        self.active = 0
        self.max_active = 0

    def is_bootstrapping(self, name: str) -> bool:
        return self.bootstrapping

    async def send_request(self, **kwargs: object) -> dict:
        self.sent.append(kwargs)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return {"response": self.answer}
        finally:
            self.active -= 1


@asynccontextmanager
async def _running_gateway(tmp_path: Path, supervisor: FakeSupervisor, **config_overrides: object):
    sock_path = tmp_path / "gateway.sock"
    params: dict = {
        "enabled": True,
        "name": "test",
        "socket_path": str(sock_path),
        "entry_anima": "main",
        "allowed_peer_uids": [os.getuid()],
        "max_concurrency": 2,
        "request_timeout_s": 30,
        "egress": _EGRESS,
    }
    params.update(config_overrides)
    cfg = EnclaveConfig(**params)
    app = create_gateway_app(get_supervisor=lambda: supervisor, config=cfg, data_dir=tmp_path)
    sock = prepare_socket(cfg)
    server = uvicorn.Server(
        uvicorn.Config(app, lifespan="off", http=PeerCredHttpProtocol, ws=None, log_level="warning")
    )
    task = asyncio.get_running_loop().create_task(server.serve(sockets=[sock]))
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.01)
    transport = httpx.AsyncHTTPTransport(uds=str(sock_path))
    try:
        async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
            yield client, supervisor
    finally:
        server.should_exit = True
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        sock.close()


def _payload(question: str = "is it ok?", case_id: str = "case-1") -> dict:
    return {"request_id": "req-1", "from_anima": "host", "case_id": case_id, "question": question}


_GOOD_ANSWER = '{"facts": [{"fact": "ping is fine", "evidence": ["record:42"]}]}'


async def test_health(tmp_path: Path) -> None:
    async with _running_gateway(tmp_path, FakeSupervisor("{}")) as (client, _sup):
        resp = await client.get("http://enclave/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "name": "test"}


async def test_ask_success(tmp_path: Path) -> None:
    sup = FakeSupervisor(_GOOD_ANSWER)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["request_id"] == "req-1"
    assert body["audit_id"]
    assert body["facts"] == [{"fact": "ping is fine", "evidence": ["record:42"]}]
    # The instruction + question were forwarded.
    sent = _sup.sent[0]
    assert sent["method"] == "process_message"
    assert sent["params"]["from_person"] == "enclave:host"
    assert sent["params"]["thread_id"] == "enclave-case-1"
    assert sent["params"]["intent"] == "question"
    assert "facts" in sent["params"]["message"]


async def test_ask_unparseable_answer(tmp_path: Path) -> None:
    sup = FakeSupervisor("the answer is yes, but not valid json")
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "answer_unparseable"
    assert body["audit_id"]
    # No answer body leaked into the response.
    assert "answer" not in body
    assert "yes" not in str(body)


async def test_ask_bad_fact_structure(tmp_path: Path) -> None:
    sup = FakeSupervisor('{"facts": "not-a-list"}')
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
    assert resp.status_code == 422
    assert resp.json()["error"] == "answer_unparseable"


async def test_ask_egress_blocked(tmp_path: Path) -> None:
    sup = FakeSupervisor('{"facts": [{"fact": "contains SECRET value", "evidence": ["record:1"]}]}')
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "egress_blocked"
    assert body["audit_id"]
    assert "SECRET" not in str(body)


async def test_ask_unauthorized_peer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import core.enclave.gateway as gateway_mod

    # Return an uid that is not in allowed_peer_uids -> 403.
    monkeypatch.setattr(gateway_mod, "_request_uid", lambda request: os.getuid() + 12345)
    sup = FakeSupervisor(_GOOD_ANSWER)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
    assert resp.status_code == 403
    assert resp.json() == {"error": "unauthorized_peer"}
    assert _sup.sent == []


async def test_ask_missing_peer_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import core.enclave.gateway as gateway_mod

    # peercred unavailable -> None -> 403 (fail-closed).
    monkeypatch.setattr(gateway_mod, "_request_uid", lambda request: None)
    sup = FakeSupervisor(_GOOD_ANSWER)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
    assert resp.status_code == 403


async def test_ask_concurrency_limit(tmp_path: Path) -> None:
    # max_concurrency=1 serialises requests.
    sup = FakeSupervisor(_GOOD_ANSWER, delay=0.3)
    async with _running_gateway(tmp_path, sup, max_concurrency=1, request_timeout_s=60) as (client, _sup):
        results = await asyncio.gather(
            client.post("http://enclave/v1/ask", json=_payload(question="q1")),
            client.post("http://enclave/v1/ask", json=_payload(question="q2")),
        )
    assert all(r.status_code == 200 for r in results)
    assert sup.max_active == 1


async def test_ask_timeout(tmp_path: Path) -> None:
    sup = FakeSupervisor(_GOOD_ANSWER, delay=5)
    async with _running_gateway(tmp_path, sup, request_timeout_s=1) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
    assert resp.status_code == 504
    assert resp.json() == {"error": "timeout"}


async def test_ask_bootstrapping(tmp_path: Path) -> None:
    sup = FakeSupervisor(_GOOD_ANSWER, bootstrapping=True)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
    assert resp.status_code == 503
    assert resp.json() == {"error": "entry_bootstrapping"}
