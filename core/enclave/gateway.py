# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Gateway: the ingress point of an enclave instance.

The gateway listens on a Unix socket and answers HTTP questions from the host
side.  ``POST /v1/ask`` returns a ``202`` with a ``job_id`` immediately
instead of holding the request open; the question is then routed to the
enclave's ``entry_anima`` (``process_message``) as a background task whose
concurrency is bounded by a semaphore.  The answer is pushed through the
egress pipeline so only masked facts plus their evidence IDs leave the
enclave.  All error responses are free of the original question and answer
bodies.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.enclave.config import EnclaveConfig
from core.enclave.egress import EgressBlockedError, EgressRequest, Fact
from core.enclave.egress.audit import write_audit
from core.enclave.egress.config import load_egress_config
from core.enclave.egress.pipeline import EgressPipeline
from core.enclave.egress.stages import EgressStageError, run_stage
from core.enclave.jobs import EnclaveJob, EnclaveJobStore, make_thread_id, utcnow_iso
from core.i18n import t

logger = logging.getLogger(__name__)

_MASKED_LINE = "(masked)"


class AskRequest(BaseModel):
    """Inbound question from the host side."""

    request_id: str
    from_anima: str
    case_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    question: str = Field(min_length=1, max_length=8000)
    # Name of an entry in ``EnclaveConfig.model_profiles``; "" means the default.
    model_profile: str = Field(default="", pattern=r"^[A-Za-z0-9_.-]{0,32}$")


def _request_uid(request: Request) -> int | None:
    """Return the peer uid announced via SO_PEERCRED, or ``None``.

    ``None`` means the peer identity could not be established and the request
    is rejected (fail-closed) rather than trusted.
    """
    extensions = request.scope.get("extensions") or {}
    cred = extensions.get("peercred") or {}
    uid = cred.get("uid")
    return uid if isinstance(uid, int) else None


UsageReader = Callable[[Path, int], dict[str, Any]]


def _valid_anima_name(name: str) -> bool:
    """Return whether *name* is a safe single anima folder name."""
    if not name:
        return False
    return not (("/" in name) or ("\\" in name) or (".." in name))


# Mirrors core.execution.loop_guards.FINAL_RESPONSE_ERROR_TEXT (enclave must not
# import execution); tests assert the two stay equal.
_FINAL_RESPONSE_ERROR_TEXT = "Unable to generate a final response. Please try again."


def _engine_error_reason(text: str) -> str:
    """Map an engine placeholder answer to a failure reason ("" if it is a real answer)."""
    if text == _FINAL_RESPONSE_ERROR_TEXT:
        return "answer_unfinished"
    if text.startswith("[Error: prompt too large"):
        return "context_overflow"
    return ""


def _write_block_audit(
    data_dir: Path,
    *,
    request_id: str,
    case_id: str,
    from_anima: str,
    audit_id: str,
    reason: str,
) -> None:
    """Record a blocked run in the egress audit trail (no answer body)."""
    write_audit(
        data_dir,
        audit_id=audit_id,
        request=EgressRequest(request_id=request_id, case_id=case_id, from_anima=from_anima, facts=[]),
        input_facts=[],
        output_facts=None,
        stages=[],
        blocked=True,
        reason=reason,
    )


class _Gateway:
    """Holds the per-instance state (semaphore + job store) for one gateway."""

    def __init__(
        self,
        config: EnclaveConfig,
        data_dir: Path,
        get_supervisor: Callable[[], Any],
        usage_reader: UsageReader | None = None,
    ) -> None:
        self.config = config
        self.data_dir = data_dir
        self.get_supervisor = get_supervisor
        self.usage_reader = usage_reader
        self.semaphore = asyncio.Semaphore(config.max_concurrency)
        self.pipeline: EgressPipeline | None = None
        self._tasks: set[asyncio.Task] = set()
        self.jobs = EnclaveJobStore(data_dir)
        self.jobs.restart_mark_failed()
        self.jobs.cleanup()

    def _egress(self) -> EgressPipeline:
        if self.pipeline is None:
            self.pipeline = EgressPipeline(
                config=load_egress_config(self.config.egress),
                data_dir=self.data_dir,
            )
        return self.pipeline

    def _check_peer(self, request: Request) -> bool:
        uid = _request_uid(request)
        return uid is not None and uid in self.config.allowed_peer_uids

    def _job_timeout(self) -> float | None:
        """Resolve the per-job completion timeout.

        ``0`` (the default) means unlimited; a positive value lets a long
        job fail with ``status=failed`` / ``error=timeout``.
        """
        if self.config.request_timeout_s and self.config.request_timeout_s > 0:
            return float(self.config.request_timeout_s)
        return None

    # ------------------------------------------------------------------
    # Job execution
    # ------------------------------------------------------------------

    def _mask_progress_text(self, text: str, case_id: str) -> str:
        """Run one progress line through the egress stages without auditing."""
        try:
            config = load_egress_config(self.config.egress)
        except Exception as exc:  # fail closed: never return unmasked text
            logger.warning("enclave gateway: could not mask progress (%s)", type(exc).__name__)
            return _MASKED_LINE
        current = [Fact(fact=text)]
        for stage in config.stages:
            try:
                current, _ = run_stage(stage, current, data_dir=self.data_dir, case_id=case_id)
            except EgressStageError:
                return _MASKED_LINE
            except Exception:
                return _MASKED_LINE
        return current[0].fact if current else _MASKED_LINE

    def _job_view(self, job: EnclaveJob, *, with_undelivered: bool = False) -> dict[str, Any]:
        """Build the public JSON view of a job (progress masked by egress)."""
        now_ts = time.time()
        try:
            created_ts = datetime.fromisoformat(job.created_at).timestamp() if job.created_at else None
        except (ValueError, TypeError):
            created_ts = None
        elapsed_s = int(now_ts - created_ts) if created_ts else None

        progress = self.jobs.read_progress(job.job_id)
        last_activity = max(
            (v for v in (job.last_activity_at, job.started_at, progress[-1].get("at") if progress else None) if v),
            default=None,
        )
        try:
            last_ts = datetime.fromisoformat(last_activity).timestamp() if last_activity else None
        except (ValueError, TypeError):
            last_ts = None

        view: dict[str, Any] = {
            "job_id": job.job_id,
            "case_id": job.case_id,
            "from_anima": job.from_anima,
            "status": job.status,
            "model_profile": job.model_profile,
            "queued_ahead": self._queued_ahead(job),
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "elapsed_s": elapsed_s,
            "last_activity_at": last_activity if last_ts else None,
            "progress": [
                {"at": entry["at"], "text": self._mask_progress_text(entry.get("text", ""), job.case_id)}
                for entry in progress
            ],
        }
        if with_undelivered:
            view["undelivered"] = not job.delivered
        if job.facts:
            view["facts"] = job.facts
        if job.audit_id:
            view["audit_id"] = job.audit_id
        if job.error:
            view["error"] = job.error
        return view

    def _queued_ahead(self, job: EnclaveJob) -> int:
        if job.status not in ("queued", "running"):
            return 0
        try:
            created_ts = datetime.fromisoformat(job.created_at).timestamp()
        except (ValueError, TypeError):
            return 0
        count = 0
        for other in self.jobs.list_all():
            if other.job_id == job.job_id:
                continue
            if other.status not in ("queued", "running"):
                continue
            try:
                other_ts = datetime.fromisoformat(other.created_at).timestamp()
            except (ValueError, TypeError):
                continue
            if other_ts <= created_ts:
                count += 1
        return count

    def _mark_failed(self, job: EnclaveJob, error: str, audit_id: str | None = None) -> None:
        """Transition *job* to failed with a stable error category."""
        self._mark_finished(job, "failed", error, audit_id)

    def _mark_finished(self, job: EnclaveJob, status: str, error: str = "", audit_id: str | None = None) -> None:
        if job.status == "cancelled":
            return  # a cancel wins over a late result
        job.status = status
        job.error = error
        job.audit_id = job.audit_id or (audit_id or "")
        job.finished_at = utcnow_iso()
        job.last_activity_at = utcnow_iso()
        self.jobs.save(job)

    async def _run_job(self, job: EnclaveJob, body: AskRequest) -> None:
        """Execute one ask job: route to the entry anima and store the result."""
        async with self.semaphore:
            current = self.jobs.load(job.job_id)
            if current is None or current.status != "queued":
                return  # deleted or cancelled while waiting
            job.status = "running"
            job.started_at = utcnow_iso()
            job.last_activity_at = utcnow_iso()
            self.jobs.save(job)

            supervisor = self.get_supervisor()
            if supervisor.is_bootstrapping(self.config.entry_anima):
                self._mark_failed(job, "entry_bootstrapping")
                return

            instruction = t("enclave.gateway.answer_instruction")
            progress_instr = t("enclave.gateway.progress_instruction", job_id=job.job_id)
            message = f"{instruction}\n\n{progress_instr}\n\n{body.question}"

            try:
                answer = await supervisor.send_request(
                    anima_name=self.config.entry_anima,
                    method="process_message",
                    params={
                        "message": message,
                        "from_person": f"enclave:{body.from_anima}",
                        "intent": "question",
                        "thread_id": job.thread_id,
                        **({"model": model} if (model := self.config.model_profiles.get(job.model_profile)) else {}),
                    },
                    timeout=self._job_timeout(),
                )
            except TimeoutError:
                logger.warning("enclave gateway: job %s timed out", job.job_id)
                self._mark_failed(job, "timeout")
                return
            except Exception:
                logger.warning("enclave gateway: entry anima IPC failed (job %s)", job.job_id, exc_info=True)
                self._mark_failed(job, "entry_unavailable")
                return

            if job.status == "cancelled":
                return
            answer_text = answer.get("response") if isinstance(answer, dict) else None
            # The whole answer goes out as one fact, JSON or not; the masker
            # is the only gate on its content.
            text = answer_text.strip() if isinstance(answer_text, str) else ""
            facts = [Fact(fact=text, evidence=[])] if text else None
            engine_error = _engine_error_reason(text)
            if engine_error:
                self._mark_failed(job, engine_error)
                return
            if facts is None:
                audit_id = uuid4().hex
                _write_block_audit(
                    self.data_dir,
                    request_id=body.request_id,
                    case_id=body.case_id,
                    from_anima=body.from_anima,
                    audit_id=audit_id,
                    reason="answer_empty",
                )
                self._mark_failed(job, "answer_empty", audit_id=audit_id)
                return

            try:
                result = self._egress().run(
                    EgressRequest(
                        request_id=body.request_id,
                        case_id=body.case_id,
                        from_anima=body.from_anima,
                        facts=facts,
                    )
                )
            except EgressBlockedError as exc:
                self._mark_failed(job, "egress_blocked", audit_id=exc.audit_id)
                return
            except Exception:
                logger.warning("enclave gateway: egress pipeline raised (job %s)", job.job_id, exc_info=True)
                self._mark_failed(job, "egress_blocked")
                return

            if job.status == "cancelled":
                return
            job.facts = [{"fact": f.fact, "evidence": list(f.evidence)} for f in result.facts]
            job.audit_id = result.audit_id
            job.status = "done"
            job.finished_at = utcnow_iso()
            job.last_activity_at = utcnow_iso()
            self.jobs.save(job)

    # ------------------------------------------------------------------
    # HTTP handlers
    # ------------------------------------------------------------------

    async def ask(self, body: AskRequest, request: Request) -> JSONResponse:
        if not self._check_peer(request):
            return JSONResponse({"error": "unauthorized_peer"}, status_code=403)
        profile = body.model_profile or self.config.default_model_profile
        if profile and profile not in self.config.model_profiles:
            return JSONResponse(
                {"error": "unknown_model_profile", "available": sorted(self.config.model_profiles)},
                status_code=400,
            )
        existing = self.jobs.find_active(body.from_anima, body.case_id)
        if existing is not None:
            return JSONResponse(
                {"job_id": existing.job_id, "status": existing.status, "deduplicated": True},
                status_code=202,
            )
        now = utcnow_iso()
        job = EnclaveJob(
            job_id=uuid4().hex,
            case_id=body.case_id,
            from_anima=body.from_anima,
            question=body.question,
            thread_id=make_thread_id(body.case_id),
            status="queued",
            model_profile=profile,
            created_at=now,
            last_activity_at=now,
        )
        self.jobs.save(job)
        task = asyncio.create_task(self._run_job(job, body))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return JSONResponse({"job_id": job.job_id, "status": "queued"}, status_code=202)

    async def status(self, job_id: str, from_anima: str, request: Request) -> JSONResponse:
        if not self._check_peer(request):
            return JSONResponse({"error": "unauthorized_peer"}, status_code=403)
        job = self.jobs.load(job_id)
        if job is None or job.from_anima != from_anima:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return JSONResponse(self._job_view(job))

    async def cancel(self, job_id: str, from_anima: str, request: Request) -> JSONResponse:
        if not self._check_peer(request):
            return JSONResponse({"error": "unauthorized_peer"}, status_code=403)
        job = self.jobs.load(job_id)
        if job is None or job.from_anima != from_anima:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if job.status in ("done", "failed", "cancelled"):
            return JSONResponse({"job_id": job.job_id, "status": job.status})
        if job.status == "running":
            try:
                supervisor = self.get_supervisor()
                await supervisor.send_request(
                    anima_name=self.config.entry_anima,
                    method="interrupt",
                    params={"thread_id": job.thread_id},
                    timeout=30.0,
                )
            except Exception:
                logger.warning("enclave gateway: interrupt failed for job %s", job.job_id, exc_info=True)
        self._mark_finished(job, "cancelled")
        return JSONResponse({"job_id": job.job_id, "status": "cancelled"})

    async def usage(self, days: int, anima: str | None, request: Request) -> JSONResponse:
        """Return per-anima token usage (tokens + cost, no conversation text)."""
        if not self._check_peer(request):
            return JSONResponse({"error": "unauthorized_peer"}, status_code=403)
        if self.usage_reader is None:
            return JSONResponse({"error": "usage_unavailable"}, status_code=503)
        if days < 1 or days > 366:
            return JSONResponse({"error": "invalid_days"}, status_code=400)

        if anima is not None:
            if not _valid_anima_name(anima):
                return JSONResponse({"error": "invalid_anima"}, status_code=400)
            anima_dir = self.data_dir / "animas" / anima
            if not (anima_dir / "token_usage").is_dir():
                return JSONResponse({"error": "not_found"}, status_code=404)
            result = await asyncio.to_thread(self.usage_reader, anima_dir, days)
            return JSONResponse({"name": self.config.name, "days": days, "animas": {anima: result}})

        animas_root = self.data_dir / "animas"
        animas: dict[str, Any] = {}
        if animas_root.is_dir():
            for item in sorted(p for p in animas_root.iterdir() if p.is_dir() and (p / "token_usage").is_dir()):
                animas[item.name] = await asyncio.to_thread(self.usage_reader, item, days)
        return JSONResponse({"name": self.config.name, "days": days, "animas": animas})

    async def list_undelivered(self, from_anima: str | None, request: Request) -> JSONResponse:
        if not self._check_peer(request):
            return JSONResponse({"error": "unauthorized_peer"}, status_code=403)
        jobs = []
        for job in self.jobs.list_all():
            if job.status not in ("done", "failed", "cancelled"):
                continue
            if job.delivered:
                continue
            if from_anima and job.from_anima != from_anima:
                continue
            jobs.append(self._job_view(job, with_undelivered=True))
        return JSONResponse({"jobs": jobs})

    async def ack(self, job_id: str, request: Request) -> JSONResponse:
        if not self._check_peer(request):
            return JSONResponse({"error": "unauthorized_peer"}, status_code=403)
        job = self.jobs.load(job_id)
        if job is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        job.delivered = True
        self.jobs.save(job)
        return JSONResponse({"job_id": job.job_id, "delivered": True})


def create_gateway_app(
    *,
    get_supervisor: Callable[[], Any],
    config: EnclaveConfig,
    data_dir: Path,
    usage_reader: UsageReader | None = None,
) -> FastAPI:
    """Build the FastAPI application that serves one enclave instance.

    *usage_reader* summarises one anima dir's token usage for ``/v1/usage``.
    It is injected by the server layer so this module stays below
    ``core.usage``; without it the endpoint answers 503.
    """
    gateway = _Gateway(config, data_dir, get_supervisor, usage_reader)
    app = FastAPI(title=f"enclave-{config.name}", docs_url=None, redoc_url=None, openapi_url=None)
    router = APIRouter()

    @router.get("/v1/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "name": config.name}

    @router.post("/v1/ask")
    async def ask(body: AskRequest, request: Request) -> JSONResponse:
        return await gateway.ask(body, request)

    @router.get("/v1/ask/{job_id}")
    async def ask_status(job_id: str, request: Request, from_anima: str = "") -> JSONResponse:
        return await gateway.status(job_id, from_anima, request)

    @router.delete("/v1/ask/{job_id}")
    async def ask_cancel(job_id: str, request: Request, from_anima: str = "") -> JSONResponse:
        return await gateway.cancel(job_id, from_anima, request)

    @router.post("/v1/ask/{job_id}/ack")
    async def ask_ack(job_id: str, request: Request) -> JSONResponse:
        return await gateway.ack(job_id, request)

    @router.get("/v1/jobs")
    async def jobs_list(request: Request, from_anima: str = "", undelivered: int = 0) -> JSONResponse:
        return await gateway.list_undelivered(from_anima or None, request)

    @router.get("/v1/usage")
    async def usage(request: Request, days: int = 30, anima: str | None = None) -> JSONResponse:
        return await gateway.usage(days, anima, request)

    app.include_router(router)
    return app


__all__ = ["AskRequest", "create_gateway_app", "_request_uid"]
