# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the enclave gateway (Unix-socket HTTP ingress, async jobs)."""

from __future__ import annotations

import asyncio
import os
import time
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
    """A stand-in for ProcessSupervisor that returns a canned answer.

    When ``gate`` (an :class:`asyncio.Event`) is given, ``send_request``
    blocks until it is set — used to simulate a long-running job.
    """

    def __init__(
        self,
        answer: str,
        *,
        delay: float = 0.0,
        bootstrapping: bool = False,
        gate: asyncio.Event | None = None,
    ) -> None:
        self.answer = answer
        self.delay = delay
        self.bootstrapping = bootstrapping
        self.gate = gate
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
            if self.gate is not None:
                await self.gate.wait()
            if self.delay:
                await asyncio.sleep(self.delay)
            return {"response": self.answer}
        finally:
            self.active -= 1


@asynccontextmanager
async def _running_gateway(
    tmp_path: Path, supervisor: FakeSupervisor, *, usage_reader: object = None, **config_overrides: object
):
    sock_path = tmp_path / "gateway.sock"
    params: dict = {
        "enabled": True,
        "name": "test",
        "socket_path": str(sock_path),
        "entry_anima": "main",
        "allowed_peer_uids": [os.getuid()],
        "max_concurrency": 2,
        "request_timeout_s": 0,
        "egress": _EGRESS,
    }
    params.update(config_overrides)
    cfg = EnclaveConfig(**params)
    app = create_gateway_app(
        get_supervisor=lambda: supervisor, config=cfg, data_dir=tmp_path, usage_reader=usage_reader
    )
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


async def _wait_running(
    client: httpx.AsyncClient,
    job_id: str,
    from_anima: str = "host",
    timeout: float = 10.0,
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = await client.get(f"http://enclave/v1/ask/{job_id}?from_anima={from_anima}")
        data = resp.json()
        if data["status"] == "running":
            return data
        if data["status"] in ("done", "failed", "cancelled"):
            return data
        await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} did not start in time")


async def _wait_done(
    client: httpx.AsyncClient,
    job_id: str,
    from_anima: str = "host",
    timeout: float = 10.0,
) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = await client.get(f"http://enclave/v1/ask/{job_id}?from_anima={from_anima}")
        data = resp.json()
        if data["status"] in ("done", "failed", "cancelled"):
            return data
        await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish in time")


_GOOD_ANSWER = '{"facts": [{"fact": "ping is fine", "evidence": ["record:42"]}]}'


async def test_health(tmp_path: Path) -> None:
    async with _running_gateway(tmp_path, FakeSupervisor("{}")) as (client, _sup):
        resp = await client.get("http://enclave/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "name": "test"}


async def test_ask_success(tmp_path: Path) -> None:
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
        assert resp.status_code == 202
        body = resp.json()
        assert body["job_id"]
        assert body["status"] == "queued"
        job_id = body["job_id"]
        # The job is kept running until the gate is released.
        running = await _wait_running(client, job_id)
        assert running["status"] == "running"
        gate.set()
        done = await _wait_done(client, job_id)
    assert done["status"] == "done"
    assert done["facts"] == [{"fact": "ping is fine", "evidence": ["record:42"]}]
    assert done.get("audit_id")
    # The instruction + progress note + question were forwarded.
    sent = _sup.sent[0]
    assert sent["method"] == "process_message"
    assert sent["params"]["from_person"] == "enclave:host"
    assert sent["params"]["thread_id"] == "enclave-case-1"
    assert sent["params"]["intent"] == "question"
    assert "facts" in sent["params"]["message"]
    assert job_id in sent["params"]["message"]


async def test_ask_unparseable_answer(tmp_path: Path) -> None:
    sup = FakeSupervisor("the answer is yes, but not valid json")
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
        job_id = resp.json()["job_id"]
        done = await _wait_done(client, job_id)
    assert resp.status_code == 202
    assert done["status"] == "failed"
    assert done["error"] == "answer_unparseable"
    assert done.get("audit_id")
    # No answer body leaked into the response.
    assert "answer" not in done
    assert "yes" not in str(done)


async def test_ask_bad_fact_structure(tmp_path: Path) -> None:
    sup = FakeSupervisor('{"facts": "not-a-list"}')
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
        job_id = resp.json()["job_id"]
        done = await _wait_done(client, job_id)
    assert resp.status_code == 202
    assert done["status"] == "failed"
    assert done["error"] == "answer_unparseable"


async def test_ask_egress_blocked(tmp_path: Path) -> None:
    sup = FakeSupervisor('{"facts": [{"fact": "contains SECRET value", "evidence": ["record:1"]}]}')
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
        job_id = resp.json()["job_id"]
        done = await _wait_done(client, job_id)
    assert resp.status_code == 202
    assert done["status"] == "failed"
    assert done["error"] == "egress_blocked"
    assert done.get("audit_id")
    assert "SECRET" not in str(done)


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
        r1 = await client.post("http://enclave/v1/ask", json=_payload(question="q1"))
        r2 = await client.post("http://enclave/v1/ask", json=_payload(question="q2"))
        assert r1.status_code == 202 and r2.status_code == 202
        await _wait_done(client, r1.json()["job_id"])
        await _wait_done(client, r2.json()["job_id"])
    assert sup.max_active == 1


async def test_ask_bootstrapping(tmp_path: Path) -> None:
    sup = FakeSupervisor(_GOOD_ANSWER, bootstrapping=True)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
        job_id = resp.json()["job_id"]
        done = await _wait_done(client, job_id)
    assert resp.status_code == 202
    assert done["status"] == "failed"
    assert done["error"] == "entry_bootstrapping"
