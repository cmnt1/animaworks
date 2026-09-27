from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.memory.rag.store import Document, SearchResult
from core.supervisor.memory_service import MemoryService, MemoryServiceUnavailable


class _QueryStore:
    def __init__(self, errors: list[str] | None = None) -> None:
        self.errors = list(errors or [])
        self.closed = False
        self.query_calls = 0
        self.close_calls = 0

    def _query_once(self, *_args, **_kwargs) -> list[SearchResult]:
        self.query_calls += 1
        if self.closed:
            raise RuntimeError("store is closed")
        if self.errors:
            raise RuntimeError(self.errors.pop(0))
        return [SearchResult(Document("recovered", "ok"), 1.0)]

    def query(self, *args, **kwargs) -> list[SearchResult]:
        """Legacy public method kept to prove MemoryService bypasses it."""
        return self._query_once(*args, **kwargs)

    def close(self) -> None:
        self.closed = True
        self.close_calls += 1


@pytest.mark.asyncio
async def test_repeated_transient_query_reopens_service_store_and_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.memory.rag import repair

    record_error = MagicMock()
    monkeypatch.setattr(repair, "record_chroma_error", record_error)
    original = _QueryStore(["Failed to get segments", "Failed to get segments"])
    reopened = _QueryStore()
    opener = MagicMock(side_effect=[original, reopened])
    service = MemoryService("sakura", tmp_path / "sakura", opener=opener)
    params = {"collection": "sakura_knowledge", "embedding": [0.1], "top_k": 1}

    first = await service.handle("memory.query", params)
    second = await service.handle("memory.query", params)

    assert first["results"][0]["document"]["id"] == "recovered"
    assert second["results"][0]["document"]["id"] == "recovered"
    assert original.closed
    assert original.close_calls == 1
    assert service._store is reopened
    assert not reopened.closed
    assert opener.call_count == 2
    record_error.assert_called_once()
    await service.close()


@pytest.mark.asyncio
async def test_corruption_error_is_recorded_for_repair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.memory.rag import repair, repair_state

    data_dir = tmp_path / "runtime"
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))
    repair._reset_for_testing()
    original = _QueryStore(["database disk image is malformed"])
    reopened = _QueryStore()
    service = MemoryService(
        "sakura", data_dir / "animas" / "sakura", opener=MagicMock(side_effect=[original, reopened])
    )

    result = await service.handle("memory.query", {"collection": "sakura_knowledge", "embedding": [0.1]})

    state = repair_state.read_state("sakura", animas_dir=data_dir / "animas")
    assert result["results"][0]["document"]["id"] == "recovered"
    assert state["status"] == "requested"
    assert state["reason"] == "sqlite_malformed"
    assert state["source"] == "root:memory.query"
    await service.close()
    repair._reset_for_testing()


@pytest.mark.asyncio
async def test_second_corruption_within_interval_does_not_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from time import monotonic

    from core.memory.rag import repair

    monkeypatch.setattr(repair, "record_chroma_error", MagicMock())
    store = _QueryStore(["database disk image is malformed"])
    opener = MagicMock(return_value=store)
    service = MemoryService("sakura", tmp_path / "sakura", opener=opener)
    service._last_reopen_monotonic = monotonic()

    with pytest.raises(MemoryServiceUnavailable, match="malformed"):
        await service.handle("memory.query", {"collection": "sakura_knowledge", "embedding": [0.1]})

    assert opener.call_count == 1
    assert not store.closed
    await service.close()


@pytest.mark.asyncio
async def test_reopen_failure_leaves_service_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.memory.rag import repair

    monkeypatch.setattr(repair, "record_chroma_error", MagicMock())
    original = _QueryStore(["database disk image is malformed"])
    opener = MagicMock(side_effect=[original, RuntimeError("reopen failed")])
    service = MemoryService("sakura", tmp_path / "sakura", opener=opener)

    with pytest.raises(MemoryServiceUnavailable, match="reopen failed"):
        await service.handle("memory.query", {"collection": "sakura_knowledge", "embedding": [0.1]})

    assert original.closed
    assert service._store is None
    assert str(service._open_error) == "reopen failed"
    with pytest.raises(MemoryServiceUnavailable, match="reopen failed"):
        await service.handle("memory.query", {"collection": "sakura_knowledge", "embedding": [0.1]})
    await service.close()


@pytest.mark.asyncio
async def test_run_native_is_blocked_while_repairing(tmp_path: Path) -> None:
    store = _QueryStore()
    service = MemoryService("sakura", tmp_path / "sakura", opener=lambda: store)
    await service.start()
    service._repairing = True

    with pytest.raises(MemoryServiceUnavailable, match="repair in progress"):
        await asyncio.get_running_loop().run_in_executor(
            service._executor,
            service._run_native,
            "memory.query",
            "sakura_knowledge",
            lambda current: current._query_once("sakura_knowledge", [0.1]),
        )

    assert store.query_calls == 0
    service._repairing = False
    await service.close()
