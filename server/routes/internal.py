from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
import concurrent.futures
import json
import logging
import re
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.platform.atomic_io import atomic_write_json
from server.events import emit

logger = logging.getLogger("animaworks.routes.internal")

# Owner-unavailable 503s tell vector clients how long to wait before their single retry.
_ROOT_RETRY_AFTER_MS = 250

_native_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="native-ops",
)


class MessageSentNotification(BaseModel):
    from_person: str
    to_person: str
    content: str = ""
    message_id: str = ""


class EmbedRequest(BaseModel):
    texts: list[str]
    purpose: Literal["document", "query"] = "document"
    priority: Literal["interactive", "bulk"] = "interactive"


class RerankRequest(BaseModel):
    query: str
    documents: list[str]
    top_k: int | None = None


class VectorQueryRequest(BaseModel):
    anima_name: str
    collection: str
    embedding: list[float]
    top_k: int = 10
    filter_metadata: dict[str, str | int | float] | None = None


class VectorUpsertRequest(BaseModel):
    anima_name: str
    collection: str
    documents: list[dict[str, Any]]


class VectorUpdateMetadataRequest(BaseModel):
    anima_name: str
    collection: str
    ids: list[str]
    metadatas: list[dict[str, str | int | float]]


class VectorDeleteDocumentsRequest(BaseModel):
    anima_name: str
    collection: str
    ids: list[str]


class VectorGetByMetadataRequest(BaseModel):
    anima_name: str
    collection: str
    where: dict[str, str | int | float] = {}
    limit: int = 20


class VectorGetAllRequest(BaseModel):
    anima_name: str
    collection: str
    limit: int = 100_000


class VectorGetByIdsRequest(BaseModel):
    anima_name: str
    collection: str
    ids: list[str]


class VectorCollectionRequest(BaseModel):
    anima_name: str
    collection: str


class VectorListCollectionsRequest(BaseModel):
    anima_name: str


class NotificationMappingRequest(BaseModel):
    ts: str
    channel: str
    anima_name: str
    notification_text: str = ""
    callback_id: str = ""


class InteractionCreateRequest(BaseModel):
    anima_name: str
    category: str = "approval"
    options: list[str]
    allowed_users: dict[str, list[str]] | None = None
    callback_id: str = ""


class CallHumanConfirmRequest(BaseModel):
    anima_name: str
    session_id: str
    sha: str = ""


class InteractionMessageTsRequest(BaseModel):
    callback_id: str
    platform: str = "slack"
    ts: str


class AnimaCreateRequest(BaseModel):
    character_sheet_content: str | None = None
    character_sheet_path: str | None = None
    name: str | None = None
    supervisor: str | None = None
    calling_anima: str = ""  # supervisor fallback when status.json has none


class DelegateTaskPersistRequest(BaseModel):
    delegator: str  # source anima name
    target: str  # destination anima name
    instruction: str  # full delegation text
    summary: str
    sub_task_id: str  # client-assigned 12hex id
    tracking_task_id: str  # client-assigned 12hex id
    workspace: str = ""  # resolve_workspace absolute path string
    acceptance_criteria: list[str] = []  # verifiable acceptance criteria for pending JSON
    model: str = ""  # optional per-task LLM model override
    execution_input: dict[str, Any] | None = None  # complete canonical input from sandbox callers
    attempt_identity: dict[str, str] | None = None


class InternalSendMessageRequest(BaseModel):
    message: dict[str, Any]  # full core.schemas.Message dump from the sandboxed sender


class InternalPostChannelRequest(BaseModel):
    from_anima: str
    channel: str
    text: str
    source: str = "anima"
    from_name: str | None = None


class UpdateTaskPersistRequest(BaseModel):
    anima_name: str
    task_id: str
    status: Literal["pending", "in_progress", "done", "cancelled"]
    meta: dict[str, Any] = {}
    summary: str | None = None
    attempt_identity: dict[str, str] | None = None
    resume: bool = False


class TaskBoardActionRequest(BaseModel):
    actor: str
    action: Literal["claim", "release", "done", "cancel", "note"]
    task_id: str
    ttl_seconds: int | None = None
    text: str | None = None


class SubmitTasksPersistRequest(BaseModel):
    anima_name: str
    tasks: list[dict[str, Any]]
    source: Literal["human", "anima"] = "anima"
    meta: dict[str, Any] = {}
    attempt_identity: dict[str, str] | None = None


def create_internal_router() -> APIRouter:
    from core.notification import CallHumanKeys
    from server.internal_auth import (
        ensure_self,
        ensure_self_or_descendant,
        internal_authz_denied,
        require_internal_caller,
    )

    router = APIRouter()
    internal = APIRouter(dependencies=[Depends(require_internal_caller)])
    _call_human_keys = CallHumanKeys()

    @internal.get("/internal/company/boundary")
    async def internal_company_boundary(from_anima: str, to_anima: str, request: Request):
        """Resolve company membership on the host for sandboxed handlers."""
        denied = ensure_self(getattr(request.state, "internal_caller", None), from_anima, path=request.url.path)
        if denied is not None:
            return denied

        from core.anima.factory import validate_anima_name
        from core.config.models import read_anima_company_checked
        from core.org.company import get_company_display_name
        from core.paths import get_animas_dir

        if validate_anima_name(from_anima) or validate_anima_name(to_anima):
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid anima name"},
            )

        animas_dir = get_animas_dir()
        from_readable, from_company = read_anima_company_checked(animas_dir / from_anima)
        to_readable, to_company = read_anima_company_checked(animas_dir / to_anima)
        if not from_readable or not to_readable:
            unreadable = [
                name for name, readable in ((from_anima, from_readable), (to_anima, to_readable)) if not readable
            ]
            return JSONResponse(
                status_code=503,
                content={
                    "detail": f"Company membership unreadable for: {', '.join(unreadable)}",
                },
            )

        cross_company = from_company is not None and to_company is not None and from_company != to_company
        try:
            display_name = get_company_display_name(to_company or "")
        except Exception:
            logger.warning(
                "Failed to resolve company display name for %r",
                to_company,
                exc_info=True,
            )
            display_name = to_company or ""

        return {
            "from_company": from_company,
            "to_company": to_company,
            "cross_company": cross_company,
            "to_display_name": display_name,
        }

    @internal.post("/internal/message-sent")
    async def internal_message_sent(body: MessageSentNotification, request: Request):
        """Notify the server that a message was sent via CLI.

        Triggers WebSocket broadcast and updates reply tracking so that
        selective archival (Fix 2) works for CLI-sent messages too.
        """
        denied = ensure_self(getattr(request.state, "internal_caller", None), body.from_person, path=request.url.path)
        if denied is not None:
            return denied

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

    @internal.post("/internal/embed")
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

        from functools import partial

        from core.memory.rag.embedding import thread_safe_encode

        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            _native_executor,
            partial(thread_safe_encode, body.texts, purpose=body.purpose, priority=body.priority),
        )
        return {"embeddings": embeddings}

    # ── Cross-encoder rerank endpoint ─────────────────────────────

    @internal.post("/internal/rerank")
    async def internal_rerank(body: RerankRequest):
        """Centralized cross-encoder reranking for child processes.

        Child processes call this endpoint via HTTP instead of loading
        the CrossEncoder model on their own, eliminating per-MCP-subprocess
        model loads (~130 MB each).
        """
        if len(body.documents) > 1000:
            return JSONResponse(
                status_code=400,
                content={"detail": "Max 1000 documents per request"},
            )
        if not body.documents:
            return {"scores": []}

        from functools import partial

        from core.memory.retrieval.reranker import get_reranker

        started = perf_counter()
        init_started = perf_counter()
        reranker = get_reranker()
        init_elapsed = perf_counter() - init_started
        loop = asyncio.get_running_loop()
        score_started = perf_counter()
        scores = await loop.run_in_executor(
            _native_executor,
            partial(reranker.score_sync, body.query, body.documents),
        )
        logger.info(
            "Internal rerank complete: query_chars=%d documents=%d elapsed=%.3fs init=%.3fs score=%.3fs",
            len(body.query),
            len(body.documents),
            perf_counter() - started,
            init_elapsed,
            perf_counter() - score_started,
        )
        if scores is None:
            # Explicit failure — never collapse to empty success (caller must
            # treat as unavailable and keep original order).
            return JSONResponse(
                status_code=503,
                content={"detail": "Reranker unavailable"},
            )

        if body.top_k is not None and body.top_k >= 0:
            # Optional ranked view; primary contract remains full scores array.
            indexed = sorted(
                enumerate(scores),
                key=lambda pair: pair[1],
                reverse=True,
            )[: body.top_k]
            return {
                "scores": scores,
                "results": [{"index": i, "score": s} for i, s in indexed],
            }
        return {"scores": scores}

    # ── Vector store endpoints (ChromaDB process separation) ───────

    def _body_payload(body: BaseModel) -> dict[str, Any]:
        if hasattr(body, "model_dump"):
            return body.model_dump()
        return body.dict()

    async def _forward_to_root(request: Request, path: str, body: BaseModel) -> dict[str, Any] | JSONResponse:
        from core.anima.factory import validate_anima_name
        from core.i18n import t
        from core.memory.rag.vector_ops import UnsupportedVectorPath, to_owner_interaction

        anima_name = getattr(body, "anima_name", "")
        caller = getattr(request.state, "internal_caller", None)
        if isinstance(anima_name, str) and anima_name:
            denied = ensure_self(caller, anima_name, path=request.url.path)
            if denied is not None:
                return denied
        if not isinstance(anima_name, str) or validate_anima_name(anima_name) is not None:
            return JSONResponse(status_code=422, content={"detail": t("rag.invalid_anima_name")})

        try:
            method, params = to_owner_interaction(path, _body_payload(body))
        except UnsupportedVectorPath:
            return JSONResponse(status_code=409, content={"detail": t("rag.unsupported_vector_path")})

        supervisor = getattr(request.app.state, "supervisor", None)
        if supervisor is None:
            return JSONResponse(
                status_code=503,
                content={"detail": t("rag.root_unavailable"), "retry_after_ms": _ROOT_RETRY_AFTER_MS},
                headers={"Retry-After": "1"},
            )
        try:
            result = await supervisor.send_request(
                anima_name,
                "memory",
                {"method": method, "params": params},
                timeout=120.0,
            )
        except Exception:
            logger.warning("Root memory proxy unavailable: anima=%s method=%s", anima_name, method, exc_info=True)
            return JSONResponse(
                status_code=503,
                content={"detail": t("rag.root_unavailable"), "retry_after_ms": _ROOT_RETRY_AFTER_MS},
                headers={"Retry-After": "1"},
            )
        if not isinstance(result, dict) or result.get("ok") is False:
            return JSONResponse(
                status_code=503,
                content={"detail": t("rag.root_operation_failed"), "retry_after_ms": _ROOT_RETRY_AFTER_MS},
                headers={"Retry-After": "1"},
            )
        return result

    @internal.post("/internal/vector/query")
    async def vector_query(body: VectorQueryRequest, request: Request):
        return await _forward_to_root(request, "/query", body)

    @internal.post("/internal/vector/upsert")
    async def vector_upsert(body: VectorUpsertRequest, request: Request):
        return await _forward_to_root(request, "/upsert", body)

    @internal.post("/internal/vector/update-metadata")
    async def vector_update_metadata(body: VectorUpdateMetadataRequest, request: Request):
        return await _forward_to_root(request, "/update-metadata", body)

    @internal.post("/internal/vector/delete-documents")
    async def vector_delete_documents(body: VectorDeleteDocumentsRequest, request: Request):
        return await _forward_to_root(request, "/delete-documents", body)

    @internal.post("/internal/vector/get-by-metadata")
    async def vector_get_by_metadata(body: VectorGetByMetadataRequest, request: Request):
        return await _forward_to_root(request, "/get-by-metadata", body)

    @internal.post("/internal/vector/get-all")
    async def vector_get_all(body: VectorGetAllRequest, request: Request):
        return await _forward_to_root(request, "/get-all", body)

    @internal.post("/internal/vector/count")
    async def vector_count(body: VectorCollectionRequest, request: Request):
        return await _forward_to_root(request, "/count", body)

    @internal.post("/internal/vector/get-by-ids")
    async def vector_get_by_ids(body: VectorGetByIdsRequest, request: Request):
        return await _forward_to_root(request, "/get-by-ids", body)

    @internal.post("/internal/vector/create-collection")
    async def vector_create_collection(body: VectorCollectionRequest, request: Request):
        return await _forward_to_root(request, "/create-collection", body)

    @internal.post("/internal/vector/delete-collection")
    async def vector_delete_collection(body: VectorCollectionRequest, request: Request):
        return await _forward_to_root(request, "/delete-collection", body)

    @internal.post("/internal/vector/list-collections")
    async def vector_list_collections(body: VectorListCollectionsRequest, request: Request):
        return await _forward_to_root(request, "/list-collections", body)

    # ── Notification / interaction persistence for sandboxed CLIs ──
    #
    # ``animaworks-tool call_human`` runs inside execution sandboxes where
    # ``{data_dir}/run/`` is read-only.  These endpoints let the sandboxed
    # process delegate the run-state writes to the server so that Slack
    # thread replies and interactive approvals still route back correctly.

    @internal.post("/internal/notification-mapping")
    async def internal_notification_mapping(body: NotificationMappingRequest, request: Request):
        denied = ensure_self(getattr(request.state, "internal_caller", None), body.anima_name, path=request.url.path)
        if denied is not None:
            return denied

        from core.notification.reply_routing import save_notification_mapping

        ok = await asyncio.to_thread(
            save_notification_mapping,
            body.ts,
            body.channel,
            body.anima_name,
            notification_text=body.notification_text,
            callback_id=body.callback_id,
        )
        return {"ok": ok}

    @internal.post("/internal/call-human/confirm")
    async def internal_call_human_confirm(body: CallHumanConfirmRequest, request: Request):
        """Check the CLI ``call_human`` confirmation key; keys live in server memory only."""
        denied = ensure_self(getattr(request.state, "internal_caller", None), body.anima_name, path=request.url.path)
        if denied is not None:
            return denied
        issued_key = _call_human_keys.check(body.anima_name, body.session_id, body.sha)
        return {"ok": issued_key is None, "sha": issued_key or ""}

    @internal.post("/internal/interaction/create")
    async def internal_interaction_create(body: InteractionCreateRequest, request: Request):
        denied = ensure_self(getattr(request.state, "internal_caller", None), body.anima_name, path=request.url.path)
        if denied is not None:
            return denied

        from core.notification.interactive import get_interaction_router

        try:
            req = await get_interaction_router().create(
                body.anima_name,
                body.category,
                body.options,
                allowed_users=body.allowed_users,
                callback_id=body.callback_id or None,
            )
        except ValueError as exc:
            return JSONResponse(status_code=409, content={"detail": str(exc)})
        return {"ok": True, "request": req.model_dump(mode="json")}

    @internal.post("/internal/interaction/message-ts")
    async def internal_interaction_message_ts(body: InteractionMessageTsRequest):
        from core.notification.interactive import get_interaction_router

        await get_interaction_router().update_message_ts(
            body.callback_id,
            body.platform,
            body.ts,
        )
        return {"ok": True}

    @internal.post("/internal/anima/create")
    async def internal_anima_create(body: AnimaCreateRequest, request: Request):
        """Create an anima outside sandbox EROFS constraints.

        Sandboxed Mode C MCP subprocesses cannot write to animas/ root.
        They fall back here so create_from_md runs on the host server.
        """
        caller = getattr(request.state, "internal_caller", None)
        denied = ensure_self(caller, body.calling_anima, path=request.url.path)
        if denied is not None:
            return denied
        if caller is not None and caller.kind == "anima":
            from core.anima.skills_check import has_newstaff_skill
            from core.paths import get_animas_dir

            if not has_newstaff_skill(get_animas_dir() / caller.name):
                denied = internal_authz_denied(
                    caller,
                    body.calling_anima,
                    "server.internal_newstaff_required",
                    path=request.url.path,
                )
                if denied is not None:
                    return denied
            if body.supervisor is not None:
                denied = ensure_self_or_descendant(caller, body.supervisor, path=request.url.path)
                if denied is not None:
                    return denied

        if not body.character_sheet_content and not body.character_sheet_path:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": ("Either character_sheet_content or character_sheet_path is required"),
                },
            )

        def _create() -> Path:
            from core.anima.factory import create_from_md
            from core.paths import get_animas_dir, get_data_dir

            md_path = Path(body.character_sheet_path) if body.character_sheet_path else None
            anima_dir = create_from_md(
                get_animas_dir(),
                md_path,
                name=body.name,
                content=body.character_sheet_content,
                supervisor=body.supervisor,
            )

            # Supervisor fallback (same as _handle_create_anima local path)
            status_path = anima_dir / "status.json"
            if status_path.exists() and body.calling_anima:
                try:
                    status_data = json.loads(status_path.read_text(encoding="utf-8"))
                    if not status_data.get("supervisor"):
                        status_data["supervisor"] = body.calling_anima
                        atomic_write_json(status_path, status_data, indent=2, ensure_ascii=False)
                except (OSError, json.JSONDecodeError):
                    logger.warning(
                        "Failed to set fallback supervisor for '%s'",
                        anima_dir.name,
                        exc_info=True,
                    )

            try:
                from cli.commands.init_cmd import _register_anima_in_config

                _register_anima_in_config(get_data_dir(), anima_dir.name)
            except Exception:
                logger.warning(
                    "Failed to register anima '%s' in config.json",
                    anima_dir.name,
                    exc_info=True,
                )

            return anima_dir

        try:
            loop = asyncio.get_running_loop()
            anima_dir = await loop.run_in_executor(_native_executor, _create)
        except FileExistsError as exc:
            return JSONResponse(status_code=409, content={"detail": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"detail": str(exc)})
        except FileNotFoundError as exc:
            return JSONResponse(status_code=422, content={"detail": str(exc)})
        except Exception as exc:
            logger.exception("internal anima create failed")
            return JSONResponse(status_code=500, content={"detail": str(exc)})

        return {"status": "ok", "anima_dir": str(anima_dir)}

    @internal.post("/internal/send-message")
    async def internal_send_message(body: InternalSendMessageRequest, request: Request):
        """Persist a DM outside sandbox EROFS constraints.

        Sandboxed Messenger.send cannot write shared/inbox (write-access
        charter: only company shared + work dirs are writable), so it falls
        back here and the host writes the exact message file.
        """
        from core.anima.factory import validate_anima_name
        from core.paths import get_shared_dir
        from core.schemas import Message

        try:
            msg = Message(**body.message)
        except Exception as exc:
            return JSONResponse(status_code=400, content={"detail": f"Invalid message: {exc}"})
        denied = ensure_self(getattr(request.state, "internal_caller", None), msg.from_person, path=request.url.path)
        if denied is not None:
            return denied
        if validate_anima_name(msg.from_person) or not re.fullmatch(r"[A-Za-z0-9_-]+", msg.to_person):
            return JSONResponse(status_code=400, content={"detail": "Invalid sender/recipient name"})
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", msg.id):
            return JSONResponse(status_code=400, content={"detail": "Invalid message ID"})

        target_dir = get_shared_dir() / "inbox" / msg.to_person
        target_dir.mkdir(parents=True, exist_ok=True)
        from core.memory._io import atomic_write_text

        if not (target_dir / "processed" / f"{msg.id}.json").exists():
            atomic_write_text(target_dir / f"{msg.id}.json", msg.model_dump_json(indent=2))
        logger.info("internal send-message: %s -> %s (%s)", msg.from_person, msg.to_person, msg.id)
        return {"ok": True, "message_id": msg.id, "thread_id": msg.thread_id}

    @internal.post("/internal/post-channel")
    async def internal_post_channel(body: InternalPostChannelRequest, request: Request):
        """Append a channel post outside sandbox EROFS constraints."""
        denied = ensure_self(getattr(request.state, "internal_caller", None), body.from_anima, path=request.url.path)
        if denied is not None:
            return denied
        from core.anima.factory import validate_anima_name
        from core.exceptions import ChannelAccessDeniedError, ChannelNotFoundError
        from core.messaging.messenger import Messenger
        from core.paths import get_shared_dir

        if validate_anima_name(body.from_anima):
            return JSONResponse(status_code=400, content={"detail": "Invalid anima name"})
        messenger = Messenger(get_shared_dir(), body.from_anima)
        try:
            messenger.post_channel(
                body.channel,
                body.text,
                source=body.source,
                from_name=body.from_name,
            )
        except ChannelNotFoundError as exc:
            return JSONResponse(status_code=404, content={"detail": str(exc)})
        except ChannelAccessDeniedError as exc:
            return JSONResponse(status_code=403, content={"detail": str(exc)})
        logger.info("internal post-channel: %s -> #%s", body.from_anima, body.channel)
        return {"ok": True}

    @internal.get("/internal/tasks")
    async def internal_tasks(
        anima_name: str,
        request: Request,
        include_archived: bool = False,
        task_id: str | None = None,
    ):
        """Read a task snapshot for workers without direct database access."""
        denied = ensure_self_or_descendant(
            getattr(request.state, "internal_caller", None), anima_name, path=request.url.path
        )
        if denied is not None:
            return denied
        from core.anima.factory import validate_anima_name
        from core.paths import get_animas_dir
        from core.tasks.queue import TaskQueueManager

        if validate_anima_name(anima_name):
            return JSONResponse(status_code=400, content={"detail": "Invalid anima name"})
        anima_dir = get_animas_dir() / anima_name
        if not anima_dir.is_dir():
            return JSONResponse(status_code=404, content={"detail": "Anima directory not found"})

        def _read():
            store = TaskQueueManager(anima_dir).store
            with store.reader():
                if task_id is not None:
                    entry = store.get(anima_name, task_id)
                    return {"tasks": [entry.model_dump(mode="json")] if entry else [], "input_ids": []}
                return {
                    "tasks": [
                        entry.model_dump(mode="json")
                        for entry in store.read(anima_name, archived=include_archived).values()
                    ],
                    "input_ids": sorted(store.executable_ids(anima_name)),
                }

        return await asyncio.get_running_loop().run_in_executor(_native_executor, _read)

    @internal.post("/internal/submit-tasks")
    async def internal_submit_tasks(body: SubmitTasksPersistRequest, request: Request):
        """Publish a complete batch on the host; no sandbox DB grant is needed."""
        denied = ensure_self(getattr(request.state, "internal_caller", None), body.anima_name, path=request.url.path)
        if denied is not None:
            return denied
        from core.anima.factory import validate_anima_name
        from core.paths import get_animas_dir
        from core.tasks.dispatch import publish_tasks

        if validate_anima_name(body.anima_name):
            return JSONResponse(status_code=400, content={"detail": "Invalid anima name"})
        anima_dir = get_animas_dir() / body.anima_name
        if not anima_dir.is_dir():
            return JSONResponse(status_code=404, content={"detail": "Anima directory not found"})

        def _publish():
            from core.tasks.board.tasks import attempt_scope

            with attempt_scope(body.attempt_identity):
                return publish_tasks(anima_dir, body.tasks, source=body.source, meta=body.meta, host_fallback=False)

        try:
            entries = await asyncio.get_running_loop().run_in_executor(_native_executor, _publish)
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"detail": str(exc)})
        except Exception as exc:
            logger.exception("internal submit-tasks failed")
            return JSONResponse(status_code=500, content={"detail": str(exc)})
        return {"ok": True, "tasks": [entry.model_dump(mode="json") for entry in entries]}

    @internal.post("/internal/delegate-task")
    async def internal_delegate_task(body: DelegateTaskPersistRequest, request: Request):
        """Persist a delegated task outside sandbox EROFS constraints.

        Sandboxed ``delegate_task`` cannot write the shared task database.
        Mode C handlers use this endpoint for atomic host-side publication.
        """
        caller = getattr(request.state, "internal_caller", None)
        denied = ensure_self(caller, body.delegator, path=request.url.path)
        if denied is not None:
            return denied
        if caller is not None and caller.kind == "anima":
            from core.config.io import load_config
            from core.org.hierarchy import is_direct_subordinate

            if not is_direct_subordinate(load_config().animas, body.delegator, body.target):
                denied = internal_authz_denied(
                    caller,
                    body.target,
                    "server.internal_not_subordinate",
                    path=request.url.path,
                )
                if denied is not None:
                    return denied

        from core.anima.factory import validate_anima_name
        from core.org.company import check_company_boundary
        from core.paths import get_animas_dir

        if validate_anima_name(body.delegator) or validate_anima_name(body.target):
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid anima name"},
            )

        animas_dir = get_animas_dir()
        target_dir = animas_dir / body.target
        delegator_dir = animas_dir / body.delegator
        if not target_dir.is_dir() or not delegator_dir.is_dir():
            missing = body.target if not target_dir.is_dir() else body.delegator
            return JSONResponse(
                status_code=404,
                content={"detail": f"Anima directory not found: {missing}"},
            )

        boundary = check_company_boundary(
            body.delegator,
            body.target,
            animas_dir=animas_dir,
        )
        if boundary.cross_company:
            if boundary.resolved_via == "fail_closed":
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Company membership unreadable"},
                )
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        f"Cross-company delegation blocked: {body.delegator} -> {body.target} ({boundary.display_name})"
                    ),
                },
            )

        def _persist() -> dict[str, str]:
            from datetime import UTC, datetime

            from core.tasks.board.tasks import attempt_scope
            from core.tasks.dispatch import publish_delegation

            payload = {
                "task_type": "llm",
                "task_id": body.sub_task_id,
                "title": body.summary,
                "description": body.instruction,
                "context": "",
                "acceptance_criteria": list(body.acceptance_criteria or []),
                "constraints": [],
                "file_paths": [],
                "submitted_by": body.delegator,
                "submitted_at": datetime.now(UTC).isoformat(),
                "reply_to": body.delegator,
                "source": "delegation",
                "working_directory": body.workspace,
                "model": body.model,
            }
            if body.execution_input is not None:
                payload = dict(body.execution_input)
                if payload.get("task_id") != body.sub_task_id:
                    raise ValueError("Delegated execution input task_id must match sub_task_id")
                if payload.get("submitted_by", body.delegator) != body.delegator:
                    raise ValueError("Delegated execution input must retain its delegator")
                payload.setdefault("submitted_by", body.delegator)
            with attempt_scope(body.attempt_identity):
                publish_delegation(
                    target_dir,
                    payload,
                    delegator=body.delegator,
                    tracking_task_id=body.tracking_task_id,
                    host_fallback=False,
                )
            return {"sub_task_id": body.sub_task_id, "tracking_task_id": body.tracking_task_id}

        try:
            loop = asyncio.get_running_loop()
            ids = await loop.run_in_executor(_native_executor, _persist)
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"detail": str(exc)})
        except Exception as exc:
            logger.exception("internal delegate-task failed")
            return JSONResponse(status_code=500, content={"detail": str(exc)})

        return {
            "ok": True,
            "sub_task_id": ids["sub_task_id"],
            "tracking_task_id": ids["tracking_task_id"],
        }

    @internal.post("/internal/task-board-action")
    async def internal_task_board_action(body: TaskBoardActionRequest, request: Request):
        """Run a lease-guarded task board write for a sandboxed anima CLI."""
        caller = getattr(request.state, "internal_caller", None)
        if body.actor == "human":
            if caller is not None and caller.kind == "anima":
                denied = internal_authz_denied(
                    caller,
                    body.actor,
                    "server.internal_identity_mismatch",
                    path=request.url.path,
                )
                if denied is not None:
                    return denied
        else:
            denied = ensure_self(caller, body.actor, path=request.url.path)
            if denied is not None:
                return denied

        from core.anima.factory import validate_anima_name
        from core.tasks.board.board_actions import BoardActionError, run_board_action

        if body.actor != "human" and validate_anima_name(body.actor):
            return JSONResponse(status_code=400, content={"detail": "Invalid actor"})

        def _run() -> dict[str, Any]:
            try:
                result = run_board_action(**body.model_dump())
            except BoardActionError as exc:
                return {"ok": False, "error": exc.message, "exit_code": exc.exit_code, "payload": exc.payload}
            return {"ok": True, "result": result}

        try:
            return await asyncio.get_running_loop().run_in_executor(_native_executor, _run)
        except Exception as exc:
            logger.exception("internal task-board-action failed")
            return JSONResponse(status_code=500, content={"detail": str(exc)})

    @internal.post("/internal/update-task")
    async def internal_update_task(body: UpdateTaskPersistRequest, request: Request):
        """Persist a task update outside sandbox EROFS constraints."""
        denied = ensure_self(getattr(request.state, "internal_caller", None), body.anima_name, path=request.url.path)
        if denied is not None:
            return denied
        from core.anima.factory import validate_anima_name
        from core.paths import get_animas_dir
        from core.tasks.queue import TaskQueueManager

        if validate_anima_name(body.anima_name):
            return JSONResponse(status_code=400, content={"detail": "Invalid anima name"})
        if body.status == "in_progress":
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "status 'in_progress' is written only by the running TaskExec. "
                    "To (re)start a task, submit it with the submit_tasks tool. "
                    "To close it, use status done or cancelled."
                },
            )
        anima_dir = get_animas_dir() / body.anima_name
        if not anima_dir.is_dir():
            return JSONResponse(
                status_code=404,
                content={"detail": f"Anima directory not found: {body.anima_name}"},
            )

        def _persist() -> Any:
            from core.tasks.board.tasks import attempt_scope

            manager = TaskQueueManager(anima_dir)
            with attempt_scope(body.attempt_identity), manager.store.transaction():
                entry = manager.update_meta(body.task_id, body.meta, summary=body.summary)
                if entry is None:
                    return None
                entry = manager.update_status(body.task_id, body.status, summary=body.summary)
                if entry is None:
                    return None
                if body.resume:
                    return manager.store.resume(manager.anima_dir.name, body.task_id)
                return entry

        try:
            loop = asyncio.get_running_loop()
            entry = await loop.run_in_executor(_native_executor, _persist)
        except Exception as exc:
            logger.exception("internal update-task failed")
            return JSONResponse(status_code=500, content={"detail": str(exc)})
        if entry is None:
            return JSONResponse(status_code=404, content={"detail": f"Task not found: {body.task_id}"})
        return {"ok": True, "task": entry.model_dump(mode="json")}

    router.include_router(internal)
    return router
