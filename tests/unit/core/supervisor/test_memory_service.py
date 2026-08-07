from __future__ import annotations

import asyncio
import threading
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.memory.rag.ipc_store import IpcVectorStore
from core.memory.rag.store import CollectionExistence, Document, SearchResult
from core.supervisor.ipc_v2 import IPCV2Connection, IPCV2ConnectionState, IPCV2Identity, ipc_v2_error
from core.supervisor.memory_service import MemoryService, MemoryServiceUnavailable
from core.supervisor.task_runner import _MemoryRpcClient


def _store() -> MagicMock:
    store = MagicMock()
    store._query_once.return_value = [SearchResult(Document("doc-1", "hello", metadata={"kind": "knowledge"}), 0.9)]
    store._list_collections_once.return_value = ["sakura_knowledge"]
    store._get_by_metadata_once.return_value = [
        SearchResult(Document("doc-2", "matched", metadata={"kind": "knowledge"}), 1.0)
    ]
    store._get_by_ids_once.return_value = [Document("doc-1", "hello", metadata={"kind": "knowledge"})]
    return store


@pytest.mark.asyncio
async def test_memory_service_checked_reads(tmp_path: Path) -> None:
    store = _store()
    service = MemoryService("sakura", tmp_path / "sakura", opener=lambda: store)

    query = await service.handle(
        "memory.query",
        {"collection": "sakura_knowledge", "embedding": [0.1, 0.2], "top_k": 3},
    )
    listed = await service.handle("memory.list_collections_checked", {})
    metadata = await service.handle(
        "memory.get_by_metadata",
        {"collection": "sakura_knowledge", "where": {"kind": "knowledge"}, "limit": 2},
    )
    documents = await service.handle(
        "memory.get_by_ids",
        {"collection": "sakura_knowledge", "ids": ["doc-1"]},
    )

    assert query["results"][0]["document"]["id"] == "doc-1"
    assert listed == {"collections": ["sakura_knowledge"]}
    assert metadata["results"][0]["document"]["content"] == "matched"
    assert documents["documents"][0]["metadata"] == {"kind": "knowledge"}
    await service.close()


@pytest.mark.asyncio
async def test_memory_service_rejects_invalid_request_as_protocol_error(tmp_path: Path) -> None:
    service = MemoryService("sakura", tmp_path / "sakura", opener=_store)

    with pytest.raises(ValueError, match="embedding"):
        await service.handle(
            "memory.query",
            {"collection": "sakura_knowledge", "embedding": "not-a-vector"},
        )
    await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("fenced", [True, False])
async def test_memory_service_unavailable_is_not_an_empty_success(tmp_path: Path, fenced: bool) -> None:
    opener = (lambda: _store()) if fenced else MagicMock(side_effect=RuntimeError("broken DB"))
    service = MemoryService(
        "sakura",
        tmp_path / "sakura",
        opener=opener,
        repair_fenced=lambda: fenced,
    )

    with pytest.raises(MemoryServiceUnavailable):
        await service.handle("memory.list_collections_checked", {})
    await service.close()


@pytest.mark.asyncio
async def test_memory_service_queue_overflow_is_unavailable(tmp_path: Path) -> None:
    store = _store()
    entered = threading.Event()
    release = threading.Event()

    def blocked_list() -> list[str]:
        entered.set()
        release.wait(timeout=2)
        return []

    store._list_collections_once.side_effect = blocked_list
    service = MemoryService("sakura", tmp_path / "sakura", queue_limit=1, opener=lambda: store)
    first = asyncio.create_task(service.handle("memory.list_collections_checked", {}))
    await asyncio.to_thread(entered.wait, 1)

    with pytest.raises(MemoryServiceUnavailable, match="queue is full"):
        await service.handle("memory.list_collections_checked", {})

    release.set()
    assert await first == {"collections": []}
    await service.close()


@pytest.mark.asyncio
async def test_memory_ipc_round_trip_and_checked_unavailable(tmp_path: Path) -> None:
    native = _store()
    service = MemoryService("sakura", tmp_path / "sakura", opener=lambda: native)
    identity = IPCV2Identity(
        job_id="job-memory",
        root_epoch=str(uuid.uuid4()),
        attempt=1,
        lane="cron",
        display_lane="background",
    )
    server_state = IPCV2ConnectionState(identity)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        connection = IPCV2Connection(reader, writer, server_state)
        try:
            for _ in range(2):
                request = await connection.receive()
                try:
                    result = await service.handle(request.body["method"], request.body["params"])
                except MemoryServiceUnavailable as exc:
                    await connection.send_response(
                        request.body["request_id"],
                        error=ipc_v2_error("UNAVAILABLE", str(exc), retryable=True),
                    )
                else:
                    await connection.send_response(request.body["request_id"], result=result)
        finally:
            await connection.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    connection = IPCV2Connection(reader, writer, IPCV2ConnectionState(identity))
    rpc = _MemoryRpcClient(connection)
    store = IpcVectorStore("http://vector.invalid", "sakura", rpc.request)

    async def receive_responses() -> None:
        for _ in range(2):
            assert rpc.accept_response(await connection.receive())

    receiver = asyncio.create_task(receive_responses())
    results = await asyncio.to_thread(store.query, "sakura_knowledge", [0.1])
    assert results[0].document.id == "doc-1"

    service._repair_fenced = lambda: True
    assert await asyncio.to_thread(store.list_collections_checked) is None
    await receiver

    rpc.close()
    await connection.close()
    server.close()
    await server.wait_closed()
    await service.close()


def test_ipc_vector_store_keeps_writes_on_http() -> None:
    store = IpcVectorStore("http://vector.invalid", "sakura", MagicMock())
    response = MagicMock()
    response.raise_for_status.return_value = None
    store._client = MagicMock()
    store._client.post.return_value = response

    assert store.create_collection("sakura_knowledge") is True
    store._client.post.assert_called_once_with(
        "/create-collection",
        json={"anima_name": "sakura", "collection": "sakura_knowledge"},
    )


def test_ipc_vector_store_collection_existence_is_three_state() -> None:
    available = IpcVectorStore(
        "http://vector.invalid",
        "sakura",
        lambda _method, _params: {"collections": ["sakura_knowledge"]},
    )
    unavailable = IpcVectorStore(
        "http://vector.invalid",
        "sakura",
        MagicMock(side_effect=RuntimeError("root down")),
    )

    assert available.collection_exists("sakura_knowledge") is CollectionExistence.EXISTS
    assert available.collection_exists("missing") is CollectionExistence.MISSING
    assert unavailable.collection_exists("sakura_knowledge") is CollectionExistence.UNAVAILABLE
