from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from core.memory.rag.store import Document
from core.memory.rag.vector_client import VectorClient, VectorStoreRetryableError


class _Response:
    def __init__(self, status_code: int, body: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _HttpClient:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.calls = 0
        self.paths: list[str] = []
        self.payloads: list[dict[str, Any]] = []

    def post(self, path: str, *, json: dict[str, Any]) -> _Response:
        self.calls += 1
        self.paths.append(path)
        self.payloads.append(json)
        return self.responses.pop(0)


def _success() -> _Response:
    return _Response(200, {"ok": True})


def _retryable_http() -> _Response:
    return _Response(503, {"retry_after_ms": 50}, {"Retry-After": "0.05"})


@pytest.mark.parametrize("kind", ["http", "internal"])
def test_write_circuit_is_shared_by_all_transports(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [10.0]
    monkeypatch.setattr("core.memory.rag.vector_client.time.monotonic", lambda: clock[0])
    if kind == "http":
        store = VectorClient("sora", base_url="http://vector.invalid")
        client = _HttpClient([_retryable_http(), _success()])
        store._client = client

        def calls() -> int:
            return client.calls
    else:
        attempts = [0]

        def transport(_path: str, _payload: dict[str, Any]) -> dict[str, Any]:
            attempts[0] += 1
            if attempts[0] == 1:
                raise VectorStoreRetryableError("temporarily unavailable", retry_after_ms=50)
            return {"ok": True}

        store = VectorClient("sora", transport=transport)

        def calls() -> int:
            return attempts[0]

    document = Document("d1", "body", embedding=[0.1])
    assert store.upsert("sora_knowledge", [document]) is False
    assert store.is_transient_write_failure("sora_knowledge")

    assert store.upsert("sora_knowledge", [document]) is False
    assert calls() == 1

    clock[0] += 0.051
    assert store.upsert("sora_knowledge", [document]) is True
    assert calls() == 2
    assert not store.is_transient_write_failure("sora_knowledge")


@pytest.mark.parametrize("kind", ["http", "internal"])
def test_reads_retry_once_for_all_transports(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.memory.rag.vector_client.time.sleep", lambda _seconds: None)
    if kind == "http":
        store = VectorClient("sora", base_url="http://vector.invalid")
        client = _HttpClient([_retryable_http(), _Response(200, {"collections": ["sora_knowledge"]})])
        store._client = client

        def calls() -> int:
            return client.calls
    else:
        attempts = [0]

        def transport(_path: str, _payload: dict[str, Any]) -> dict[str, Any]:
            attempts[0] += 1
            if attempts[0] == 1:
                raise VectorStoreRetryableError("temporarily unavailable", retry_after_ms=0)
            return {"collections": ["sora_knowledge"]}

        store = VectorClient("sora", transport=transport)

        def calls() -> int:
            return attempts[0]

    assert store.list_collections() == ["sora_knowledge"]
    assert calls() == 2


@pytest.mark.parametrize("kind", ["http", "bridge"])
def test_get_all_returns_documents_across_transports(kind: str) -> None:
    documents = [{"id": f"doc-{index}", "content": f"body-{index}", "metadata": {"index": index}} for index in range(3)]
    payloads: list[tuple[str, dict[str, Any]]] = []

    if kind == "http":
        store = VectorClient("sora", base_url="http://vector.invalid")
        client = _HttpClient([_Response(200, {"results": documents})])
        store._client = client
    else:

        def transport(path: str, payload: dict[str, Any]) -> dict[str, Any]:
            payloads.append((path, payload))
            return {"results": documents}

        store = VectorClient("sora", transport=transport)

    results = store.get_all("sora_knowledge", limit=100_000)

    assert [result.document.id for result in results] == ["doc-0", "doc-1", "doc-2"]
    assert [result.document.content for result in results] == ["body-0", "body-1", "body-2"]
    if kind == "http":
        assert client.calls == 1
        assert client.paths == ["/get-all"]
        assert client.payloads[0] == {
            "anima_name": "sora",
            "collection": "sora_knowledge",
            "limit": 100_000,
        }
    else:
        assert payloads == [("/get-all", {"anima_name": "sora", "collection": "sora_knowledge", "limit": 100_000})]


@pytest.mark.asyncio
async def test_root_event_loop_bridge_failure_is_logged_as_error(caplog: pytest.LogCaptureFixture) -> None:
    from core.memory.rag.vector_ops import bridge_transport

    async def handler(_method: str, _params: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True}

    loop = asyncio.get_running_loop()
    store = VectorClient("sora", transport=bridge_transport(handler, loop))

    with caplog.at_level(logging.ERROR):
        assert store.get_all("sora_knowledge") == []

    assert "synchronous memory operation attempted on the root event loop" in caplog.text
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_vector_client_requires_exactly_one_destination() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        VectorClient("sora")
    with pytest.raises(ValueError, match="exactly one"):
        VectorClient("sora", base_url="http://vector.invalid", transport=lambda *_args: {})
