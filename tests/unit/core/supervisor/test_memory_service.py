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
    store._create_collection_once.return_value = True
    store._delete_collection_once.return_value = True
    store._upsert_once.return_value = True
    store._delete_documents_once.return_value = True
    store._update_metadata_once.return_value = True
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
async def test_memory_service_supports_all_vector_store_writes(tmp_path: Path) -> None:
    store = _store()
    service = MemoryService("sakura", tmp_path / "sakura", opener=lambda: store)
    document = {"id": "doc-1", "content": "hello", "embedding": [0.1], "metadata": {"kind": "knowledge"}}

    assert await service.handle("memory.create_collection", {"collection": "sakura_knowledge"}) == {"ok": True}
    assert await service.handle(
        "memory.upsert",
        {"collection": "sakura_knowledge", "documents": [document]},
    ) == {"ok": True}
    assert await service.handle(
        "memory.update_metadata",
        {"collection": "sakura_knowledge", "ids": ["doc-1"], "metadatas": [{"kind": "episode"}]},
    ) == {"ok": True}
    assert await service.handle(
        "memory.delete_documents",
        {"collection": "sakura_knowledge", "ids": ["doc-1"]},
    ) == {"ok": True}
    assert await service.handle("memory.delete_collection", {"collection": "sakura_knowledge"}) == {"ok": True}

    store._create_collection_once.assert_called_once_with("sakura_knowledge")
    store._upsert_once.assert_called_once()
    store._update_metadata_once.assert_called_once_with("sakura_knowledge", ["doc-1"], [{"kind": "episode"}])
    store._delete_documents_once.assert_called_once_with("sakura_knowledge", ["doc-1"])
    store._delete_collection_once.assert_called_once_with("sakura_knowledge")
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

    def blocked_upsert(_collection: str, _documents: list[Document]) -> bool:
        entered.set()
        release.wait(timeout=2)
        return True

    store._upsert_once.side_effect = blocked_upsert
    service = MemoryService("sakura", tmp_path / "sakura", queue_limit=1, opener=lambda: store)
    params = {
        "collection": "sakura_knowledge",
        "documents": [{"id": "doc-1", "content": "hello", "embedding": [0.1], "metadata": {}}],
    }
    first = asyncio.create_task(service.handle("memory.upsert", params))
    await asyncio.to_thread(entered.wait, 1)

    with pytest.raises(MemoryServiceUnavailable, match="queue is full"):
        await service.handle("memory.upsert", params)

    release.set()
    assert await first == {"ok": True}
    await service.close()


@pytest.mark.asyncio
async def test_memory_service_serializes_parallel_writes(tmp_path: Path) -> None:
    store = _store()
    first_entered = threading.Event()
    release_first = threading.Event()
    order: list[str] = []

    def ordered_upsert(_collection: str, documents: list[Document]) -> bool:
        order.append(documents[0].id)
        if documents[0].id == "first":
            first_entered.set()
            release_first.wait(timeout=2)
        return True

    store._upsert_once.side_effect = ordered_upsert
    service = MemoryService("sakura", tmp_path / "sakura", opener=lambda: store)

    def params(doc_id: str) -> dict:
        return {
            "collection": "sakura_knowledge",
            "documents": [{"id": doc_id, "content": doc_id, "embedding": [0.1], "metadata": {}}],
        }

    first = asyncio.create_task(service.handle("memory.upsert", params("first")))
    await asyncio.to_thread(first_entered.wait, 1)
    second = asyncio.create_task(service.handle("memory.upsert", params("second")))
    await asyncio.sleep(0)
    release_first.set()

    assert await asyncio.gather(first, second) == [{"ok": True}, {"ok": True}]
    assert order == ["first", "second"]
    await service.close()


@pytest.mark.asyncio
async def test_memory_ipc_round_trip_and_checked_unavailable(tmp_path: Path) -> None:
    native = _store()
    written: dict[str, Document] = {}

    def upsert(_collection: str, documents: list[Document]) -> bool:
        written.update((document.id, document) for document in documents)
        return True

    def query(_collection: str, _embedding: list[float], _top_k: int, _where) -> list[SearchResult]:
        return [SearchResult(document, 1.0) for document in written.values()]

    native._upsert_once.side_effect = upsert
    native._query_once.side_effect = query
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
            for _ in range(3):
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
        for _ in range(3):
            assert rpc.accept_response(await connection.receive())

    receiver = asyncio.create_task(receive_responses())
    assert await asyncio.to_thread(
        store.upsert,
        "sakura_knowledge",
        [Document("written", "through root", embedding=[0.1], metadata={"kind": "knowledge"})],
    )
    results = await asyncio.to_thread(store.query, "sakura_knowledge", [0.1])
    assert results[0].document.id == "written"

    service._repair_fenced = lambda: True
    assert await asyncio.to_thread(store.list_collections_checked) is None
    await receiver

    rpc.close()
    await connection.close()
    server.close()
    await server.wait_closed()
    await service.close()


def test_ipc_vector_store_routes_writes_to_root() -> None:
    requester = MagicMock(return_value={"ok": True})
    store = IpcVectorStore("http://vector.invalid", "sakura", requester)

    assert store.create_collection("sakura_knowledge") is True
    requester.assert_called_once_with("memory.create_collection", {"collection": "sakura_knowledge"})
    assert store._client is None


def test_ipc_vector_store_marks_unavailable_write_as_transient() -> None:
    responses = iter([RuntimeError("root busy"), {"ok": True}])

    def requester(_method: str, _params: dict) -> dict:
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    store = IpcVectorStore("http://vector.invalid", "sakura", requester)

    assert store.create_collection("sakura_knowledge") is False
    assert store.is_transient_write_failure("sakura_knowledge") is True
    assert store.create_collection("sakura_knowledge") is True
    assert store.is_transient_write_failure("sakura_knowledge") is False


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
