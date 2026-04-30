from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
import concurrent.futures
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from server.events import emit

logger = logging.getLogger("animaworks.routes.internal")

_native_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="native-ops",
)


class MessageSentNotification(BaseModel):
    from_person: str
    to_person: str
    content: str = ""
    message_id: str = ""


class EmbedRequest(BaseModel):
    texts: list[str]


class VectorQueryRequest(BaseModel):
    anima_name: str | None = None
    collection: str
    embedding: list[float]
    top_k: int = 10
    filter_metadata: dict[str, str | int | float] | None = None


class VectorUpsertRequest(BaseModel):
    anima_name: str | None = None
    collection: str
    documents: list[dict[str, Any]]


class VectorUpdateMetadataRequest(BaseModel):
    anima_name: str | None = None
    collection: str
    ids: list[str]
    metadatas: list[dict[str, str | int | float]]


class VectorDeleteDocumentsRequest(BaseModel):
    anima_name: str | None = None
    collection: str
    ids: list[str]


class VectorGetByMetadataRequest(BaseModel):
    anima_name: str | None = None
    collection: str
    where: dict[str, str | int | float] = {}
    limit: int = 20


class VectorGetByIdsRequest(BaseModel):
    anima_name: str | None = None
    collection: str
    ids: list[str]


class VectorCollectionRequest(BaseModel):
    anima_name: str | None = None
    collection: str


class VectorListCollectionsRequest(BaseModel):
    anima_name: str | None = None


def create_internal_router() -> APIRouter:
    router = APIRouter()

    @router.post("/internal/message-sent")
    async def internal_message_sent(body: MessageSentNotification, request: Request):
        """Notify the server that a message was sent via CLI.

        Triggers WebSocket broadcast and updates reply tracking so that
        selective archival (Fix 2) works for CLI-sent messages too.
        """
        await emit(
            request,
            "anima.interaction",
            {
                "from_person": body.from_person,
                "to_person": body.to_person,
                "type": "message",
                "summary": body.content[:200],
                "message_id": body.message_id,
            },
        )

        # Note: replied_to tracking is now managed by each Anima process.
        # The server no longer holds live DigitalAnima objects.

        return {"status": "ok"}

    @router.get("/messages/{message_id}")
    async def get_message(message_id: str, request: Request):
        """Return the full JSON of a stored message by its ID."""
        # Sanitize to prevent path traversal
        if "/" in message_id or "\\" in message_id or ".." in message_id:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid message_id"},
            )

        shared_dir: Path = request.app.state.shared_dir
        inbox_root = shared_dir / "inbox"
        if not inbox_root.is_dir():
            return JSONResponse(
                status_code=404,
                content={"detail": "Message not found"},
            )

        filename = f"{message_id}.json"
        for anima_inbox in sorted(inbox_root.iterdir()):
            if not anima_inbox.is_dir():
                continue
            # Check processed first, then inbox root
            for candidate in [
                anima_inbox / "processed" / filename,
                anima_inbox / filename,
            ]:
                if candidate.is_file():
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    return data

        return JSONResponse(
            status_code=404,
            content={"detail": "Message not found"},
        )

    # ── Embedding inference endpoint ────────────────────────────

    @router.post("/internal/embed")
    async def internal_embed(body: EmbedRequest):
        """Centralized embedding inference for child processes.

        Child processes call this endpoint via HTTP instead of loading
        the SentenceTransformer model on their own GPU, reducing total
        VRAM usage from ~22 GB to ~800 MB.
        """
        if len(body.texts) > 1000:
            return JSONResponse(
                status_code=400,
                content={"detail": "Max 1000 texts per request"},
            )
        if not body.texts:
            return {"embeddings": []}

        from core.memory.rag.singleton import thread_safe_encode

        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            _native_executor,
            thread_safe_encode,
            body.texts,
        )
        return {"embeddings": embeddings}

    # ── Vector store endpoints (ChromaDB process separation) ───────

    async def _run_native(fn, *args):
        """Run *fn* in the single-threaded native executor.

        ChromaDB Rust bindings and PyTorch native code SEGV when run
        concurrently on glibc 2.43+ / kernel 7.x.  Pinning all native
        operations to one OS thread eliminates the race.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_native_executor, fn, *args)

    @router.post("/internal/vector/query")
    async def vector_query(body: VectorQueryRequest):
        from core.memory.rag.singleton import get_vector_store

        store = get_vector_store(body.anima_name)
        if store is None:
            return {"results": []}
        results = await _run_native(
            store.query,
            body.collection,
            body.embedding,
            body.top_k,
            body.filter_metadata,
        )
        return {
            "results": [
                {
                    "id": r.document.id,
                    "content": r.document.content,
                    "score": r.score,
                    "metadata": r.document.metadata,
                }
                for r in results
            ]
        }

    @router.post("/internal/vector/upsert")
    async def vector_upsert(body: VectorUpsertRequest):
        from core.memory.rag.singleton import get_vector_store
        from core.memory.rag.store import Document

        store = get_vector_store(body.anima_name)
        if store is None:
            return JSONResponse(status_code=503, content={"detail": "Vector store unavailable"})
        docs = [
            Document(
                id=d["id"],
                content=d.get("content", ""),
                embedding=d.get("embedding"),
                metadata=d.get("metadata", {}),
            )
            for d in body.documents
        ]
        await _run_native(store.upsert, body.collection, docs)
        return {"status": "ok"}

    @router.post("/internal/vector/update-metadata")
    async def vector_update_metadata(body: VectorUpdateMetadataRequest):
        from core.memory.rag.singleton import get_vector_store

        store = get_vector_store(body.anima_name)
        if store is None:
            return JSONResponse(status_code=503, content={"detail": "Vector store unavailable"})
        await _run_native(
            store.update_metadata,
            body.collection,
            body.ids,
            body.metadatas,
        )
        return {"status": "ok"}

    @router.post("/internal/vector/delete-documents")
    async def vector_delete_documents(body: VectorDeleteDocumentsRequest):
        from core.memory.rag.singleton import get_vector_store

        store = get_vector_store(body.anima_name)
        if store is None:
            return JSONResponse(status_code=503, content={"detail": "Vector store unavailable"})
        await _run_native(store.delete_documents, body.collection, body.ids)
        return {"status": "ok"}

    @router.post("/internal/vector/get-by-metadata")
    async def vector_get_by_metadata(body: VectorGetByMetadataRequest):
        from core.memory.rag.singleton import get_vector_store

        store = get_vector_store(body.anima_name)
        if store is None:
            return {"results": []}
        results = await _run_native(
            store.get_by_metadata,
            body.collection,
            body.where,
            body.limit,
        )
        return {
            "results": [
                {
                    "id": r.document.id,
                    "content": r.document.content,
                    "score": r.score,
                    "metadata": r.document.metadata,
                }
                for r in results
            ]
        }

    @router.post("/internal/vector/get-by-ids")
    async def vector_get_by_ids(body: VectorGetByIdsRequest):
        from core.memory.rag.singleton import get_vector_store

        store = get_vector_store(body.anima_name)
        if store is None:
            return {"documents": []}
        docs = await _run_native(store.get_by_ids, body.collection, body.ids)
        return {"documents": [{"id": d.id, "content": d.content, "metadata": d.metadata} for d in docs]}

    @router.post("/internal/vector/create-collection")
    async def vector_create_collection(body: VectorCollectionRequest):
        from core.memory.rag.singleton import get_vector_store

        store = get_vector_store(body.anima_name)
        if store is None:
            return JSONResponse(status_code=503, content={"detail": "Vector store unavailable"})
        await _run_native(store.create_collection, body.collection)
        return {"status": "ok"}

    @router.post("/internal/vector/delete-collection")
    async def vector_delete_collection(body: VectorCollectionRequest):
        from core.memory.rag.singleton import get_vector_store

        store = get_vector_store(body.anima_name)
        if store is None:
            return JSONResponse(status_code=503, content={"detail": "Vector store unavailable"})
        await _run_native(store.delete_collection, body.collection)
        return {"status": "ok"}

    @router.post("/internal/vector/list-collections")
    async def vector_list_collections(body: VectorListCollectionsRequest):
        from core.memory.rag.singleton import get_vector_store

        store = get_vector_store(body.anima_name)
        if store is None:
            return {"collections": []}
        collections = await _run_native(store.list_collections)
        return {"collections": collections}

    return router
