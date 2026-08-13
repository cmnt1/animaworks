"""Unit tests for IpcVectorStore retryable read retries."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from core.memory.rag.ipc_store import IpcVectorStore
from core.memory.rag.store import Document


class _RetryableError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True, retry_after_ms: int = 0) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms


def _store(requester) -> IpcVectorStore:
    return IpcVectorStore("http://vector.invalid", "sakura", requester)


def test_query_retries_once_on_retryable_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("core.memory.rag.ipc_store.time.sleep", lambda _s: None)
    calls: list[str] = []
    responses: list[Any] = [
        _RetryableError("busy", retry_after_ms=10),
        {
            "results": [
                {"id": "doc1", "content": "hello", "score": 0.9, "metadata": {"kind": "knowledge"}},
            ]
        },
    ]

    def requester(method: str, _params: dict) -> dict:
        calls.append(method)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    results = _store(requester).query("sakura_knowledge", [0.1, 0.2], top_k=3)

    assert len(results) == 1
    assert results[0].document.id == "doc1"
    assert calls == ["memory.query", "memory.query"]


def test_query_retryable_then_fail_returns_empty_and_calls_twice(monkeypatch) -> None:
    monkeypatch.setattr("core.memory.rag.ipc_store.time.sleep", lambda _s: None)
    requester = MagicMock(side_effect=_RetryableError("still busy", retry_after_ms=5))

    results = _store(requester).query("sakura_knowledge", [0.1], top_k=1)

    assert results == []
    assert requester.call_count == 2


def test_query_non_retryable_fails_immediately_without_retry() -> None:
    requester = MagicMock(side_effect=RuntimeError("PROTOCOL_ERROR: bad request"))

    results = _store(requester).query("sakura_knowledge", [0.1], top_k=1)

    assert results == []
    assert requester.call_count == 1


def test_query_unavailable_prefix_is_retryable(monkeypatch) -> None:
    """Production _MemoryRpcClient raises RuntimeError('UNAVAILABLE: ...')."""
    monkeypatch.setattr("core.memory.rag.ipc_store.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def requester(_method: str, _params: dict) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("UNAVAILABLE: memory queue is full")
        return {
            "results": [
                {"id": "recovered", "content": "ok", "score": 0.5, "metadata": {}},
            ]
        }

    results = _store(requester).query("sakura_knowledge", [0.1], top_k=1)

    assert len(results) == 1
    assert results[0].document.id == "recovered"
    assert calls["n"] == 2


def test_write_does_not_retry_on_retryable_failure(monkeypatch) -> None:
    sleep = MagicMock()
    monkeypatch.setattr("core.memory.rag.ipc_store.time.sleep", sleep)
    requester = MagicMock(side_effect=_RetryableError("busy", retry_after_ms=100))

    store = _store(requester)
    assert store.create_collection("sakura_knowledge") is False
    assert requester.call_count == 1
    sleep.assert_not_called()
    assert store.is_transient_write_failure("sakura_knowledge") is True


def test_get_by_ids_retries_once(monkeypatch) -> None:
    monkeypatch.setattr("core.memory.rag.ipc_store.time.sleep", lambda _s: None)
    responses: list[Any] = [
        _RetryableError("busy", retry_after_ms=1),
        {"documents": [{"id": "d1", "content": "c", "metadata": {}}]},
    ]

    def requester(_method: str, _params: dict) -> dict:
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    docs = _store(requester).get_by_ids("sakura_knowledge", ["d1"])
    assert len(docs) == 1
    assert isinstance(docs[0], Document)
    assert docs[0].id == "d1"


def test_retry_after_ms_capped_at_500(monkeypatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr("core.memory.rag.ipc_store.time.sleep", lambda s: slept.append(s))
    requester = MagicMock(side_effect=_RetryableError("busy", retry_after_ms=9999))

    assert _store(requester).query("sakura_knowledge", [0.1]) == []
    assert slept == [0.5]
    assert requester.call_count == 2
