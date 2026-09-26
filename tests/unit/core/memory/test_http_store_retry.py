"""Unit tests for HttpVectorStore single retry on owner-unavailable.

Reads retry once after the owner's reported ``retry_after_ms`` (capped at
500ms) when it answers UNAVAILABLE, for both the HTTP and the in-process
owner transport. Writes do not retry and instead mark a transient write
failure.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from core.memory.rag.http_store import HttpVectorStore
from core.memory.rag.owner_transport import owner_transport
from core.supervisor.memory_service import MemoryServiceUnavailable


class _FakeResp:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls = 0

    def post(self, path: str, json: dict | None = None) -> _FakeResp:
        self.calls += 1
        return self._responses.pop(0)


def _http_store(client: _FakeClient) -> HttpVectorStore:
    store = HttpVectorStore("http://vector.invalid", "sakura")
    store._get_client = lambda: client
    return store


_RESULTS = {"results": [{"id": "doc1", "content": "hello", "score": 0.9, "metadata": {"kind": "knowledge"}}]}


def test_http_read_retries_once_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("core.memory.rag.http_store.time.sleep", lambda _s: None)
    client = _FakeClient([_FakeResp(503, headers={"Retry-After": "1"}), _FakeResp(200, _RESULTS)])
    results = _http_store(client).query("sakura_knowledge", [0.1, 0.2], top_k=3)
    assert len(results) == 1
    assert results[0].document.id == "doc1"
    assert client.calls == 2


def test_http_read_second_failure_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr("core.memory.rag.http_store.time.sleep", lambda _s: None)
    client = _FakeClient([_FakeResp(503, headers={"Retry-After": "1"}), _FakeResp(503, headers={"Retry-After": "1"})])
    results = _http_store(client).query("sakura_knowledge", [0.1])
    assert results == []
    assert client.calls == 2


def test_http_retry_after_ms_capped_at_500(monkeypatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr("core.memory.rag.http_store.time.sleep", lambda s: slept.append(s))
    client = _FakeClient(
        [_FakeResp(503, headers={"Retry-After": "9"}), _FakeResp(503, headers={"Retry-After": "9"})]
    )
    assert _http_store(client).query("sakura_knowledge", [0.1]) == []
    assert slept == [0.5]
    assert client.calls == 2



def test_http_retry_waits_body_retry_after_ms(monkeypatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr("core.memory.rag.http_store.time.sleep", lambda s: slept.append(s))
    client = _FakeClient(
        [_FakeResp(503, {"retry_after_ms": 250}, headers={"Retry-After": "1"}), _FakeResp(200, _RESULTS)]
    )
    assert len(_http_store(client).query("sakura_knowledge", [0.1])) == 1
    assert slept == [0.25]


def test_http_retry_after_header_is_seconds(monkeypatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr("core.memory.rag.http_store.time.sleep", lambda s: slept.append(s))
    client = _FakeClient([_FakeResp(503, headers={"Retry-After": "0.2"}), _FakeResp(200, _RESULTS)])
    assert len(_http_store(client).query("sakura_knowledge", [0.1])) == 1
    assert slept == [0.2]

def test_http_non_retryable_failure_does_not_retry(monkeypatch) -> None:
    # 400 without Retry-After is an ordinary error, not a retryable owner signal.
    client = _FakeClient([_FakeResp(400, {"detail": "bad request"})])
    results = _http_store(client).query("sakura_knowledge", [0.1])
    assert results == []
    assert client.calls == 1


@pytest.mark.asyncio
async def test_owner_read_retries_once_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("core.memory.rag.http_store.time.sleep", lambda _s: None)
    calls = {"n": 0}

    async def handle(_method: str, _params: dict) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise MemoryServiceUnavailable("memory store unavailable")
        return _RESULTS

    loop = asyncio.get_running_loop()
    store = HttpVectorStore("", "sakura", transport=owner_transport(handle, loop))

    results = await asyncio.to_thread(store.query, "sakura_knowledge", [0.1])
    assert len(results) == 1
    assert results[0].document.id == "doc1"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_owner_read_second_failure_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr("core.memory.rag.http_store.time.sleep", lambda _s: None)

    async def handle(_method: str, _params: dict) -> dict:
        raise MemoryServiceUnavailable("memory store unavailable")

    loop = asyncio.get_running_loop()
    store = HttpVectorStore("", "sakura", transport=owner_transport(handle, loop))

    assert await asyncio.to_thread(store.query, "sakura_knowledge", [0.1]) == []


@pytest.mark.asyncio
async def test_owner_write_does_not_retry(monkeypatch) -> None:
    sleep = MagicMock()
    monkeypatch.setattr("core.memory.rag.http_store.time.sleep", sleep)

    async def handle(_method: str, _params: dict) -> dict:
        raise MemoryServiceUnavailable("memory queue is full")

    loop = asyncio.get_running_loop()
    store = HttpVectorStore("", "sakura", transport=owner_transport(handle, loop))

    assert await asyncio.to_thread(store.create_collection, "sakura_knowledge") is False
    sleep.assert_not_called()
    assert store.is_transient_write_failure("sakura_knowledge") is True
