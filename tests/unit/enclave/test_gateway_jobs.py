# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the enclave gateway's asynchronous job behaviour.

These test the completion conditions described in
``docs/plans/20261013_enclave-async-ask-A-gateway.md``: immediate 202s,
no timeout on long jobs, deduplication, thread_id normalisation, progress
egress masking, undelivered/ack flow, restart recovery, and cancellation.
The supervisor is mocked throughout.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn

from core.enclave.config import EnclaveConfig
from core.enclave.gateway import create_gateway_app
from core.enclave.gateway_server import PeerCredHttpProtocol, prepare_socket
from core.enclave.jobs import EnclaveJobStore, make_thread_id

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

    def __init__(self, answer: str, *, gate: asyncio.Event | None = None) -> None:
        self.answer = answer
        self.gate = gate
        self.sent: list[dict] = []

    def is_bootstrapping(self, name: str) -> bool:
        return False

    async def send_request(self, **kwargs: object) -> dict:
        if kwargs.get("method") == "interrupt":
            return {"interrupted": True}
        self.sent.append(kwargs)
        if self.gate is not None:
            await self.gate.wait()
        return {"response": self.answer}


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
        "request_timeout_s": 0,
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


def _payload(question: str = "is it ok?", case_id: str = "case-1", from_anima: str = "host") -> dict:
    return {"request_id": "req-1", "from_anima": from_anima, "case_id": case_id, "question": question}


_GOOD_ANSWER = '{"facts": [{"fact": "ping is fine", "evidence": ["record:42"]}]}'
_THREAD_RE = re.compile(r"^[A-Za-z0-9_-]{1,36}$")


async def _wait_running(client: httpx.AsyncClient, job_id: str, from_anima: str = "host") -> dict:
    deadline = time.time() + 10
    while time.time() < deadline:
        resp = await client.get(f"http://enclave/v1/ask/{job_id}?from_anima={from_anima}")
        assert resp.status_code == 200
        if resp.json()["status"] == "running":
            return resp.json()
        await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} did not start in time")


async def _wait_done(client: httpx.AsyncClient, job_id: str, from_anima: str = "host") -> dict:
    deadline = time.time() + 10
    while time.time() < deadline:
        resp = await client.get(f"http://enclave/v1/ask/{job_id}?from_anima={from_anima}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in ("done", "failed", "cancelled"):
            return data
        await asyncio.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish in time")


async def test_post_is_immediate_and_get_reports_done(tmp_path: Path) -> None:
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        gate.set()
        done = await _wait_done(client, job_id)
    assert done["status"] == "done"
    assert done["facts"] == [{"fact": "ping is fine", "evidence": ["record:42"]}]


async def test_long_job_is_not_cut_off_with_default_timeout(tmp_path: Path) -> None:
    # Default request_timeout_s (0) means unlimited: a job that has not
    # answered for longer than the former default (900s worth of waiting via
    # the event) must stay running rather than being cut off.
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        running = await _wait_running(client, job_id)
        assert running["status"] == "running"
        assert not running.get("error")
        # Still running while the gateway keeps waiting; not failed/timeout.
        status_again = (await client.get(f"http://enclave/v1/ask/{job_id}?from_anima=host")).json()
        assert status_again["status"] == "running"
        # Releasing the event lets it complete as done.
        gate.set()
        done = await _wait_done(client, job_id)
    assert done["status"] == "done"
    assert done["facts"] == [{"fact": "ping is fine", "evidence": ["record:42"]}]


async def test_duplicate_post_reuses_job_and_calls_send_request_once(tmp_path: Path) -> None:
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        r1 = await client.post("http://enclave/v1/ask", json=_payload())
        job_id = r1.json()["job_id"]
        await _wait_running(client, job_id)
        r2 = await client.post("http://enclave/v1/ask", json=_payload())
        assert r2.status_code == 202
        assert r2.json()["job_id"] == job_id
        assert r2.json()["deduplicated"] is True
        gate.set()
        await _wait_done(client, job_id)
    assert len(sup.sent) == 1


@pytest.mark.parametrize(
    "case_id",
    [
        "x" * 64,
        "case.with.many.dots.and.also.dashes-and_underscores.long.long.long",
        "長いケースIDで許可外の文字を含む１２３",
        "UPPER_and_lower_123-with-dash",
    ],
)
def test_thread_id_satisfies_rules(case_id: str) -> None:
    thread_id = make_thread_id(case_id)
    assert _THREAD_RE.fullmatch(thread_id), thread_id


def test_thread_id_is_stable_and_unique(case_id: str = "case.with.dots" * 4) -> None:
    assert make_thread_id(case_id) == make_thread_id(case_id)
    assert make_thread_id(case_id) != make_thread_id(case_id + ".other")


async def test_long_case_id_thread_id_used_for_process_message(tmp_path: Path) -> None:
    long_case = "x" * 50 + ".y.z"
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload(case_id=long_case))
        job_id = resp.json()["job_id"]
        gate.set()
        await _wait_done(client, job_id)
    sent = sup.sent[0]
    thread_id = sent["params"]["thread_id"]
    assert _THREAD_RE.fullmatch(thread_id), thread_id
    # Same case_id always maps to the same thread_id.
    assert thread_id == make_thread_id(long_case)


async def test_progress_is_masked_by_egress(tmp_path: Path) -> None:
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
        job_id = resp.json()["job_id"]
        await _wait_running(client, job_id)
        # The entry anima writes an interim note containing PII worth masking.
        store = EnclaveJobStore(tmp_path)
        store.write_progress(job_id, "found SECRET marker 1234-5678 in the record")
        status = (await client.get(f"http://enclave/v1/ask/{job_id}?from_anima=host")).json()
        gate.set()
        await _wait_done(client, job_id)
    assert status["progress"] == [{"at": status["progress"][0]["at"], "text": "(masked)"}]
    assert "SECRET" not in status["progress"][0]["text"]


async def test_undelivered_and_ack_flow(tmp_path: Path) -> None:
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
        job_id = resp.json()["job_id"]
        gate.set()
        await _wait_done(client, job_id)

        undelivered = (await client.get("http://enclave/v1/jobs?from_anima=host&undelivered=1")).json()
        assert any(j["job_id"] == job_id for j in undelivered["jobs"])

        ack = await client.post(f"http://enclave/v1/ask/{job_id}/ack")
        assert ack.status_code == 200
        assert ack.json()["delivered"] is True

        after = (await client.get("http://enclave/v1/jobs?from_anima=host&undelivered=1")).json()
        assert all(j["job_id"] != job_id for j in after["jobs"])

        # A different anima cannot read this job.
        other = await client.get(f"http://enclave/v1/ask/{job_id}?from_anima=someone-else")
        assert other.status_code == 404


async def test_restart_marks_running_as_failed(tmp_path: Path) -> None:
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        resp = await client.post("http://enclave/v1/ask", json=_payload())
        job_id = resp.json()["job_id"]
        await _wait_running(client, job_id)
        # Simulate a restart: a fresh store reloads from disk and reaps jobs.
        fresh_store = EnclaveJobStore(tmp_path)
        fresh_store.restart_mark_failed()
        job = fresh_store.load(job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error == "enclave_restarted"


async def test_delete_queued_cancels_job(tmp_path: Path) -> None:
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    async with _running_gateway(tmp_path, sup, max_concurrency=1) as (client, _sup):
        # Occupy the only slot with a long-running job so the second queues.
        r1 = await client.post("http://enclave/v1/ask", json=_payload(case_id="first"))
        r1_job = r1.json()["job_id"]
        await _wait_running(client, r1_job)

        r2 = await client.post("http://enclave/v1/ask", json=_payload(case_id="second"))
        r2_job = r2.json()["job_id"]
        r2_status = (await client.get(f"http://enclave/v1/ask/{r2_job}?from_anima=host")).json()
        assert r2_status["status"] == "queued"

        resp = await client.request("DELETE", f"http://enclave/v1/ask/{r2_job}?from_anima=host")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

        gate.set()
        await _wait_done(client, r1_job)
        await asyncio.sleep(0.1)
        # The cancelled queued job never reaches the anima.
        assert len(_sup.sent) == 1
        assert (await client.get(f"http://enclave/v1/ask/{r2_job}?from_anima=host")).json()["status"] == "cancelled"


async def test_cancel_running_is_not_overwritten_by_late_answer(tmp_path: Path) -> None:
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    async with _running_gateway(tmp_path, sup) as (client, _sup):
        job_id = (await client.post("http://enclave/v1/ask", json=_payload())).json()["job_id"]
        await _wait_running(client, job_id)
        resp = await client.request("DELETE", f"http://enclave/v1/ask/{job_id}?from_anima=host")
        assert resp.json()["status"] == "cancelled"
        gate.set()
        await asyncio.sleep(0.1)
        data = (await client.get(f"http://enclave/v1/ask/{job_id}?from_anima=host")).json()
        assert data["status"] == "cancelled"
        assert "facts" not in data


async def test_progress_fails_closed_when_egress_unreadable(tmp_path: Path) -> None:
    gate = asyncio.Event()
    sup = FakeSupervisor(_GOOD_ANSWER, gate=gate)
    bad_egress = {"stages": [{"type": "no_such_stage"}]}
    async with _running_gateway(tmp_path, sup, egress=bad_egress) as (client, _sup):
        job_id = (await client.post("http://enclave/v1/ask", json=_payload())).json()["job_id"]
        await _wait_running(client, job_id)
        ok, _ = EnclaveJobStore(tmp_path).write_progress(job_id, "raw 1234-5678")
        assert ok
        data = (await client.get(f"http://enclave/v1/ask/{job_id}?from_anima=host")).json()
        assert [p["text"] for p in data["progress"]] == ["(masked)"]
        assert data["last_activity_at"] == data["progress"][-1]["at"]
        gate.set()
