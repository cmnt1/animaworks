from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Isolated HTTP worker for native ChromaDB vector operations."""

import argparse
import asyncio
import concurrent.futures
import functools
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.platform.fd_limits import raise_fd_soft_limit

logger = logging.getLogger("animaworks.rag.vector_worker")

_CIRCUIT_FAILURE_THRESHOLD = int(os.environ.get("ANIMAWORKS_VECTOR_CIRCUIT_FAILURE_THRESHOLD", "3"))
_CIRCUIT_BACKOFF_BASE_SECONDS = float(os.environ.get("ANIMAWORKS_VECTOR_CIRCUIT_BACKOFF_BASE_SECONDS", "1"))
_CIRCUIT_BACKOFF_MAX_SECONDS = float(os.environ.get("ANIMAWORKS_VECTOR_CIRCUIT_BACKOFF_MAX_SECONDS", "300"))
_CIRCUIT_REJECTION_LOG_INTERVAL_SECONDS = float(
    os.environ.get("ANIMAWORKS_VECTOR_CIRCUIT_REJECTION_LOG_INTERVAL_SECONDS", "60")
)
_write_circuit_breakers: dict[str, dict[str, Any]] = {}
_VECTOR_ACTION_ERROR = object()
_LATCH_RECOVERY_BACKOFF_SECONDS = float(os.environ.get("ANIMAWORKS_VECTOR_LATCH_RECOVERY_BACKOFF_SECONDS", "5"))
_LATCH_RECOVERY_RETRY_STATUSES = {"ok", "missing"}
_ACTIVE_REPAIR_STATUSES = {"requested", "stopping", "repairing"}
_ACTIVE_REPAIR_WRITE_RETRY_AFTER_SECONDS = int(os.environ.get("ANIMAWORKS_VECTOR_REPAIR_RETRY_AFTER_SECONDS", "30"))
_latched_store_recovery_lock = threading.Lock()
_latched_store_recovery_backoff_until: dict[str, float] = {}
_latched_store_recovery_in_progress: set[str] = set()
_SELF_HEAL_ESCALATION_THRESHOLD = 3
_SELF_HEAL_ESCALATION_WINDOW_SECONDS = 600.0
_SELF_HEAL_ESCALATION_COOLDOWN_SECONDS = 600.0
_self_heal_escalation_lock = threading.Lock()
_self_heal_failures: dict[str, deque[float]] = {}
_self_heal_last_escalated_at: dict[str, float] = {}

_native_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="vector-worker-native",
)
_VECTOR_QUEUE_LIMIT_DEFAULT = 64
_VECTOR_QUEUE_RETRY_AFTER_SECONDS = 1


class _NativeQueueFull(RuntimeError):
    """Raised when no more work can be admitted to the native queue."""

    def __init__(self, queue_limit: int) -> None:
        super().__init__("Vector worker queue full")
        self.queue_limit = queue_limit


class _NativeResultFuture(asyncio.Future[Any]):
    """Future that publishes cancellation to the executor thread immediately."""

    def __init__(self, cancel_event: threading.Event) -> None:
        super().__init__()
        self._cancel_event = cancel_event

    def cancel(self, msg: str | None = None) -> bool:
        self._cancel_event.set()
        return super().cancel(msg)


class _NativeAdmission:
    """Thread-safe admission and metrics for the single native executor."""

    def __init__(self, queue_limit: int) -> None:
        self.queue_limit = queue_limit
        self._lock = threading.Lock()
        self._pending = 0
        self._in_flight = 0
        self._submitted = 0
        self._completed = 0
        self._rejected = 0

    def admit(self) -> bool:
        with self._lock:
            if self._pending >= self.queue_limit:
                self._rejected += 1
                return False
            self._pending += 1
            self._submitted += 1
            return True

    def submission_failed(self) -> None:
        with self._lock:
            self._pending -= 1
            self._submitted -= 1

    def start(self, *, cancelled: bool) -> bool:
        with self._lock:
            self._pending -= 1
            if cancelled:
                self._completed += 1
                return False
            self._in_flight += 1
            return True

    def finish(self) -> None:
        with self._lock:
            self._in_flight -= 1
            self._completed += 1

    def status(self) -> dict[str, int]:
        with self._lock:
            return {
                "queue_limit": self.queue_limit,
                "queue_depth": self._pending,
                "in_flight": self._in_flight,
                "submitted": self._submitted,
                "completed": self._completed,
                "rejected": self._rejected,
            }


def _get_vector_queue_limit() -> int:
    raw_limit = os.environ.get("ANIMAWORKS_VECTOR_QUEUE_LIMIT", str(_VECTOR_QUEUE_LIMIT_DEFAULT))
    try:
        queue_limit = int(raw_limit)
    except ValueError:
        logger.warning(
            "Invalid ANIMAWORKS_VECTOR_QUEUE_LIMIT=%r; using default=%d",
            raw_limit,
            _VECTOR_QUEUE_LIMIT_DEFAULT,
        )
        return _VECTOR_QUEUE_LIMIT_DEFAULT
    if queue_limit < 1:
        logger.warning(
            "ANIMAWORKS_VECTOR_QUEUE_LIMIT must be positive; using default=%d",
            _VECTOR_QUEUE_LIMIT_DEFAULT,
        )
        return _VECTOR_QUEUE_LIMIT_DEFAULT
    return queue_limit


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


class VectorQuickCheckRequest(BaseModel):
    anima_name: str
    timeout_seconds: float = 10.0
    source: str = "worker_quick_check"
    record_repair: bool = True


def _set_future_result(future: asyncio.Future[Any], result: Any) -> None:
    if not future.done():
        future.set_result(result)


def _set_future_exception(future: asyncio.Future[Any], exc: BaseException) -> None:
    if not future.done():
        future.set_exception(exc)


async def _run_native(fn, *args, _admission: _NativeAdmission | None = None, **kwargs):
    loop = asyncio.get_running_loop()
    call = functools.partial(fn, *args, **kwargs)
    if _admission is None:
        return await loop.run_in_executor(_native_executor, call)
    if not _admission.admit():
        raise _NativeQueueFull(_admission.queue_limit)

    cancelled = threading.Event()
    result_future = _NativeResultFuture(cancelled)

    def run() -> None:
        if not _admission.start(cancelled=cancelled.is_set()):
            return
        try:
            result = call()
        except BaseException as exc:
            _admission.finish()
            try:
                loop.call_soon_threadsafe(_set_future_exception, result_future, exc)
            except RuntimeError:
                pass
        else:
            _admission.finish()
            try:
                loop.call_soon_threadsafe(_set_future_result, result_future, result)
            except RuntimeError:
                pass

    try:
        _native_executor.submit(run)
    except BaseException:
        _admission.submission_failed()
        raise

    try:
        return await result_future
    except asyncio.CancelledError:
        cancelled.set()
        result_future.cancel()
        raise


def _has_active_repair_state(anima_name: str) -> bool:
    try:
        from core.memory.rag import repair_state

        return repair_state.read_state(anima_name).get("status") in _ACTIVE_REPAIR_STATUSES
    except Exception:
        logger.debug("Failed to read RAG repair state for owner=%s", anima_name, exc_info=True)
        return True


def _begin_latched_store_recovery(anima_name: str) -> bool:
    now = time.monotonic()
    with _latched_store_recovery_lock:
        retry_at = float(_latched_store_recovery_backoff_until.get(anima_name) or 0.0)
        if retry_at > now:
            return False
        if retry_at:
            _latched_store_recovery_backoff_until.pop(anima_name, None)
        if anima_name in _latched_store_recovery_in_progress:
            return False
        _latched_store_recovery_in_progress.add(anima_name)
        return True


def _end_latched_store_recovery(anima_name: str) -> None:
    with _latched_store_recovery_lock:
        _latched_store_recovery_in_progress.discard(anima_name)


def _set_latched_store_recovery_backoff(anima_name: str) -> None:
    with _latched_store_recovery_lock:
        _latched_store_recovery_backoff_until[anima_name] = time.monotonic() + _LATCH_RECOVERY_BACKOFF_SECONDS


def _clear_latched_store_recovery_backoff(anima_name: str) -> None:
    with _latched_store_recovery_lock:
        _latched_store_recovery_backoff_until.pop(anima_name, None)


def _try_recover_latched_store(anima_name: str | None) -> Any | None:
    if anima_name is None:
        return None

    from core.memory.rag.singleton import (
        clear_vector_store_init_failed,
        get_vector_store,
        is_global_vector_store_init_failed,
        is_vector_store_init_failed,
    )

    if is_global_vector_store_init_failed() or not is_vector_store_init_failed(anima_name):
        return None
    if _has_active_repair_state(anima_name):
        return None
    if not _begin_latched_store_recovery(anima_name):
        return None

    try:
        if is_global_vector_store_init_failed() or not is_vector_store_init_failed(anima_name):
            return None
        if _has_active_repair_state(anima_name):
            return None

        from core.memory.rag.sqlite_health import check_anima_vectordb_health

        health = check_anima_vectordb_health(
            anima_name,
            source="worker_store_unavailable",
            record_repair=True,
        )
        if health.status not in _LATCH_RECOVERY_RETRY_STATUSES:
            _set_latched_store_recovery_backoff(anima_name)
            logger.info(
                "Skipping latched vector-store recovery for owner=%s: health_status=%s; backing off for %.1fs",
                anima_name,
                health.status,
                _LATCH_RECOVERY_BACKOFF_SECONDS,
            )
            return None

        clear_vector_store_init_failed(anima_name)
        store = get_vector_store(anima_name)
        if store is not None:
            _clear_latched_store_recovery_backoff(anima_name)
            _clear_owner_write_circuit_breakers(anima_name)
            logger.info("Recovered latched vector store for owner=%s", anima_name)
            return store

        _set_latched_store_recovery_backoff(anima_name)
        logger.warning(
            "Latched vector-store recovery did not reopen a store for owner=%s; backing off for %.1fs",
            anima_name,
            _LATCH_RECOVERY_BACKOFF_SECONDS,
        )
        return None
    except Exception:
        _set_latched_store_recovery_backoff(anima_name)
        logger.warning("Latched vector-store recovery failed for owner=%s", anima_name, exc_info=True)
        return None
    finally:
        _end_latched_store_recovery(anima_name)


def _call_vector_store(anima_name: str | None, action: Callable[[Any], Any]) -> Any | None:
    from core.memory.rag.singleton import get_vector_store, reset_vector_store, reset_vector_store_after_error

    try:
        store = get_vector_store(anima_name)
        if store is None:
            store = _try_recover_latched_store(anima_name)
            if store is None:
                return None
        result = action(store)
        consume_failure = getattr(type(store), "consume_lightweight_self_heal_failure", None)
        if not callable(consume_failure) or not consume_failure(store) or not _record_self_heal_failure(anima_name):
            return result

        owner = anima_name or "shared"
        logger.warning(
            "Escalating repeated lightweight ChromaDB self-heal failures to full vector-store reset: "
            "owner=%s failures=%d window=%ss cooldown=%ss",
            owner,
            _SELF_HEAL_ESCALATION_THRESHOLD,
            int(_SELF_HEAL_ESCALATION_WINDOW_SECONDS),
            int(_SELF_HEAL_ESCALATION_COOLDOWN_SECONDS),
        )
        reset_vector_store(anima_name)
        _clear_owner_write_circuit_breakers(anima_name)
        fresh_store = get_vector_store(anima_name)
        if fresh_store is None:
            return result
        return action(fresh_store)
    except Exception:
        logger.warning("Vector worker native store action failed for owner=%s", anima_name or "shared", exc_info=True)
        try:
            reset_vector_store_after_error(anima_name, source="worker_action_failure")
        except Exception:
            logger.debug(
                "Vector worker failed to reset native store after action failure for owner=%s",
                anima_name or "shared",
                exc_info=True,
            )
        return _VECTOR_ACTION_ERROR


def _record_self_heal_failure(anima_name: str | None) -> bool:
    """Return True once three lightweight retry failures require escalation."""
    owner = anima_name or "shared"
    now = time.monotonic()
    with _self_heal_escalation_lock:
        failures = _self_heal_failures.setdefault(owner, deque())
        cutoff = now - _SELF_HEAL_ESCALATION_WINDOW_SECONDS
        while failures and failures[0] < cutoff:
            failures.popleft()
        failures.append(now)
        last_escalated = _self_heal_last_escalated_at.get(owner)
        if len(failures) < _SELF_HEAL_ESCALATION_THRESHOLD:
            return False
        if last_escalated is not None and now - last_escalated < _SELF_HEAL_ESCALATION_COOLDOWN_SECONDS:
            return False
        failures.clear()
        _self_heal_last_escalated_at[owner] = now
        return True


def _clear_owner_self_heal_escalation(anima_name: str | None) -> None:
    owner = anima_name or "shared"
    with _self_heal_escalation_lock:
        _self_heal_failures.pop(owner, None)
        _self_heal_last_escalated_at.pop(owner, None)


def _vector_write_failed(operation: str, collection: str) -> JSONResponse:
    logger.warning("Vector worker %s failed for collection '%s'", operation, collection)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Vector {operation} failed",
            "collection": collection,
        },
    )


def _breaker_key(anima_name: str | None, collection: str) -> str:
    owner = anima_name or "shared"
    return f"{owner}:{collection}"


def _clear_owner_write_circuit_breakers(anima_name: str | None) -> None:
    owner = anima_name or "shared"
    for key, state in list(_write_circuit_breakers.items()):
        if state.get("owner", "shared") == owner or key.startswith(f"{owner}:"):
            _write_circuit_breakers.pop(key, None)


def _before_vector_write(anima_name: str | None, collection: str) -> JSONResponse | None:
    if anima_name and _has_active_repair_state(anima_name):
        logger.warning(
            "Vector write deferred during active RAG repair: owner=%s collection=%s",
            anima_name,
            collection,
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": "RAG repair in progress",
                "collection": collection,
                "owner": anima_name,
                "retry_after_seconds": _ACTIVE_REPAIR_WRITE_RETRY_AFTER_SECONDS,
            },
            headers={"Retry-After": str(_ACTIVE_REPAIR_WRITE_RETRY_AFTER_SECONDS)},
        )

    key = _breaker_key(anima_name, collection)
    state = _write_circuit_breakers.get(key)
    if not state:
        return None
    retry_at = float(state.get("next_retry_at") or 0.0)
    now = time.monotonic()
    if retry_at <= now:
        return None
    retry_after = max(1, int(retry_at - now))
    last_logged_at = float(state.get("last_logged_at") or 0.0)
    suppressed_count = int(state.get("suppressed_count") or 0)
    if not last_logged_at or now - last_logged_at >= _CIRCUIT_REJECTION_LOG_INTERVAL_SECONDS:
        logger.error(
            "Vector write circuit breaker open: owner=%s collection=%s failures=%s retry_after=%ss suppressed=%d",
            anima_name or "shared",
            collection,
            state.get("consecutive_failures", 0),
            retry_after,
            suppressed_count,
        )
        state["last_logged_at"] = now
        state["suppressed_count"] = 0
    else:
        state["suppressed_count"] = suppressed_count + 1
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Vector write circuit breaker open",
            "collection": collection,
            "owner": anima_name or "shared",
            "consecutive_failures": state.get("consecutive_failures", 0),
            "retry_after_seconds": retry_after,
        },
        headers={"Retry-After": str(retry_after)},
    )


def _record_vector_write_success(anima_name: str | None, collection: str) -> None:
    _write_circuit_breakers.pop(_breaker_key(anima_name, collection), None)


def _record_vector_write_failure(anima_name: str | None, collection: str, operation: str) -> dict[str, Any]:
    key = _breaker_key(anima_name, collection)
    now = time.monotonic()
    state = dict(_write_circuit_breakers.get(key) or {})
    failures = int(state.get("consecutive_failures") or 0) + 1
    delay = (
        min(_CIRCUIT_BACKOFF_BASE_SECONDS * (2 ** max(0, failures - 1)), _CIRCUIT_BACKOFF_MAX_SECONDS)
        if failures >= _CIRCUIT_FAILURE_THRESHOLD
        else 0.0
    )
    state.update(
        {
            "owner": anima_name or "shared",
            "collection": collection,
            "operation": operation,
            "consecutive_failures": failures,
            "next_retry_at": now + delay if delay > 0 else 0.0,
            "last_failure_monotonic": now,
            "threshold": _CIRCUIT_FAILURE_THRESHOLD,
        }
    )
    state.setdefault("last_logged_at", 0.0)
    state.setdefault("suppressed_count", 0)
    _write_circuit_breakers[key] = state
    log = logger.error if failures >= _CIRCUIT_FAILURE_THRESHOLD else logger.warning
    log(
        "Vector write failure recorded: owner=%s collection=%s operation=%s failures=%d next_retry=%.1fs",
        anima_name or "shared",
        collection,
        operation,
        failures,
        delay,
    )
    return state


def _breaker_status() -> list[dict[str, Any]]:
    now = time.monotonic()
    statuses: list[dict[str, Any]] = []
    for state in _write_circuit_breakers.values():
        retry_at = float(state.get("next_retry_at") or 0.0)
        item = {
            "owner": state.get("owner", "shared"),
            "collection": state.get("collection", ""),
            "operation": state.get("operation", ""),
            "consecutive_failures": int(state.get("consecutive_failures") or 0),
            "threshold": int(state.get("threshold") or _CIRCUIT_FAILURE_THRESHOLD),
            "open": retry_at > now,
            "retry_after_seconds": max(0, int(retry_at - now)),
        }
        statuses.append(item)
    return statuses


def _write_success_response(anima_name: str | None, collection: str) -> dict[str, str]:
    _record_vector_write_success(anima_name, collection)
    return {"status": "ok"}


def _is_vector_action_error(value: Any) -> bool:
    return value is _VECTOR_ACTION_ERROR


def _write_failure_response(anima_name: str | None, collection: str, operation: str) -> JSONResponse:
    state = _record_vector_write_failure(anima_name, collection, operation)
    retry_at = float(state.get("next_retry_at") or 0.0)
    retry_after = max(0, int(retry_at - time.monotonic()))
    content = {
        "detail": f"Vector {operation} failed",
        "collection": collection,
        "owner": anima_name or "shared",
        "consecutive_failures": state["consecutive_failures"],
        "circuit_breaker_threshold": state["threshold"],
    }
    headers = None
    if retry_after > 0:
        content["retry_after_seconds"] = retry_after
        headers = {"Retry-After": str(retry_after)}
    return JSONResponse(
        status_code=500,
        content=content,
        headers=headers,
    )


def _search_results_payload(results) -> dict[str, Any]:
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


async def _close_native_vector_stores() -> None:
    from core.memory.rag.singleton import close_all_vector_stores

    logger.info("Vector worker shutdown: closing cached vector stores")
    # This is one internal shutdown job and must not be rejected by HTTP admission.
    await _run_native(close_all_vector_stores)


def create_app() -> FastAPI:
    os.environ.pop("ANIMAWORKS_VECTOR_URL", None)
    _write_circuit_breakers.clear()
    _latched_store_recovery_backoff_until.clear()
    _latched_store_recovery_in_progress.clear()
    _self_heal_failures.clear()
    _self_heal_last_escalated_at.clear()
    from core.memory.rag.direct_access import enable_direct_chroma_for_process

    enable_direct_chroma_for_process()
    admission = _NativeAdmission(_get_vector_queue_limit())

    async def run_native(fn, *args, **kwargs):
        return await _run_native(fn, *args, _admission=admission, **kwargs)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            await _close_native_vector_stores()

    app = FastAPI(title="AnimaWorks Vector Worker", lifespan=lifespan)

    @app.exception_handler(_NativeQueueFull)
    async def native_queue_full(_request: Any, exc: _NativeQueueFull) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Vector worker queue full",
                "queue_limit": exc.queue_limit,
                "retry_after_seconds": _VECTOR_QUEUE_RETRY_AFTER_SECONDS,
            },
            headers={"Retry-After": str(_VECTOR_QUEUE_RETRY_AFTER_SECONDS)},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/status")
    async def status() -> dict[str, Any]:
        from core.gpu import get_gpu_status

        return {
            "status": "ok",
            "write_circuit_breakers": _breaker_status(),
            "gpu": get_gpu_status(),
            **admission.status(),
        }

    @app.post("/reset-store")
    async def vector_reset_store(body: VectorListCollectionsRequest) -> dict[str, str]:
        from core.memory.rag.singleton import reset_vector_store

        await run_native(reset_vector_store, body.anima_name)
        _clear_owner_write_circuit_breakers(body.anima_name)
        _clear_owner_self_heal_escalation(body.anima_name)
        return {"status": "ok"}

    @app.post("/query")
    async def vector_query(body: VectorQueryRequest):
        results = await run_native(
            _call_vector_store,
            body.anima_name,
            lambda store: store.query(
                body.collection,
                body.embedding,
                body.top_k,
                body.filter_metadata,
            ),
        )
        if results is None:
            return {"results": []}
        if _is_vector_action_error(results):
            return {"results": []}
        return _search_results_payload(results)

    @app.post("/upsert")
    async def vector_upsert(body: VectorUpsertRequest):
        from core.memory.rag.store import Document

        breaker = _before_vector_write(body.anima_name, body.collection)
        if breaker is not None:
            return breaker
        docs = [
            Document(
                id=d["id"],
                content=d.get("content", ""),
                embedding=d.get("embedding"),
                metadata=d.get("metadata", {}),
            )
            for d in body.documents
        ]
        ok = await run_native(
            _call_vector_store,
            body.anima_name,
            lambda store: store.upsert(body.collection, docs),
        )
        if ok is None:
            return JSONResponse(status_code=503, content={"detail": "Vector store unavailable"})
        if _is_vector_action_error(ok) or not ok:
            return _write_failure_response(body.anima_name, body.collection, "upsert")
        return _write_success_response(body.anima_name, body.collection)

    @app.post("/update-metadata")
    async def vector_update_metadata(body: VectorUpdateMetadataRequest):
        breaker = _before_vector_write(body.anima_name, body.collection)
        if breaker is not None:
            return breaker
        ok = await run_native(
            _call_vector_store,
            body.anima_name,
            lambda store: store.update_metadata(
                body.collection,
                body.ids,
                body.metadatas,
            ),
        )
        if ok is None:
            return JSONResponse(status_code=503, content={"detail": "Vector store unavailable"})
        if _is_vector_action_error(ok) or not ok:
            return _write_failure_response(body.anima_name, body.collection, "update-metadata")
        return _write_success_response(body.anima_name, body.collection)

    @app.post("/delete-documents")
    async def vector_delete_documents(body: VectorDeleteDocumentsRequest):
        breaker = _before_vector_write(body.anima_name, body.collection)
        if breaker is not None:
            return breaker
        ok = await run_native(
            _call_vector_store,
            body.anima_name,
            lambda store: store.delete_documents(body.collection, body.ids),
        )
        if ok is None:
            return JSONResponse(status_code=503, content={"detail": "Vector store unavailable"})
        if _is_vector_action_error(ok) or not ok:
            return _write_failure_response(body.anima_name, body.collection, "delete-documents")
        return _write_success_response(body.anima_name, body.collection)

    @app.post("/get-by-metadata")
    async def vector_get_by_metadata(body: VectorGetByMetadataRequest):
        results = await run_native(
            _call_vector_store,
            body.anima_name,
            lambda store: store.get_by_metadata(
                body.collection,
                body.where,
                body.limit,
            ),
        )
        if results is None:
            return {"results": []}
        if _is_vector_action_error(results):
            return {"results": []}
        return _search_results_payload(results)

    @app.post("/get-by-ids")
    async def vector_get_by_ids(body: VectorGetByIdsRequest):
        docs = await run_native(
            _call_vector_store,
            body.anima_name,
            lambda store: store.get_by_ids(body.collection, body.ids),
        )
        if docs is None:
            return {"documents": []}
        if _is_vector_action_error(docs):
            return {"documents": []}
        return {"documents": [{"id": d.id, "content": d.content, "metadata": d.metadata} for d in docs]}

    @app.post("/create-collection")
    async def vector_create_collection(body: VectorCollectionRequest):
        breaker = _before_vector_write(body.anima_name, body.collection)
        if breaker is not None:
            return breaker
        ok = await run_native(
            _call_vector_store,
            body.anima_name,
            lambda store: store.create_collection(body.collection),
        )
        if ok is None:
            return JSONResponse(status_code=503, content={"detail": "Vector store unavailable"})
        if _is_vector_action_error(ok) or not ok:
            return _write_failure_response(body.anima_name, body.collection, "create-collection")
        return {"status": "ok"}

    @app.post("/delete-collection")
    async def vector_delete_collection(body: VectorCollectionRequest):
        breaker = _before_vector_write(body.anima_name, body.collection)
        if breaker is not None:
            return breaker
        ok = await run_native(
            _call_vector_store,
            body.anima_name,
            lambda store: store.delete_collection(body.collection),
        )
        if ok is None:
            return JSONResponse(status_code=503, content={"detail": "Vector store unavailable"})
        if _is_vector_action_error(ok) or not ok:
            return _write_failure_response(body.anima_name, body.collection, "delete-collection")
        return _write_success_response(body.anima_name, body.collection)

    @app.post("/list-collections")
    async def vector_list_collections(body: VectorListCollectionsRequest):
        collections = await run_native(
            _call_vector_store,
            body.anima_name,
            lambda store: store.list_collections(),
        )
        if collections is None:
            return {"collections": []}
        if _is_vector_action_error(collections):
            return {"collections": []}
        return {"collections": collections}

    @app.post("/quick-check")
    async def vector_quick_check(body: VectorQuickCheckRequest):
        from core.memory.rag.sqlite_health import check_anima_vectordb_health

        result = await run_native(
            check_anima_vectordb_health,
            body.anima_name,
            timeout_seconds=body.timeout_seconds,
            source=body.source,
            record_repair=body.record_repair,
        )
        return {
            "status": result.status,
            "ok": result.ok,
            "corrupt": result.corrupt,
            "db_path": str(result.db_path),
            "details": list(result.details),
            "error": result.error,
        }

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run isolated AnimaWorks vector worker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    import uvicorn

    raise_fd_soft_limit(logger=logger, process_label="vector worker")
    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        log_level="info",
        timeout_keep_alive=65,
    )


if __name__ == "__main__":
    main()
