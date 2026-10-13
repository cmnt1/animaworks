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
import json
import logging
import re
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

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

_MASKED_LINE = "(masked)"


class AskRequest(BaseModel):
    """Inbound question from the host side."""

    request_id: str
    from_anima: str
    case_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    question: str = Field(min_length=1, max_length=8000)


def _request_uid(request: Request) -> int | None:
    """Return the peer uid announced via SO_PEERCRED, or ``None``.

    ``None`` means the peer identity could not be established and the request
    is rejected (fail-closed) rather than trusted.
    """
    extensions = request.scope.get("extensions") or {}
    cred = extensions.get("peercred") or {}
    uid = cred.get("uid")
    return uid if isinstance(uid, int) else None


def _balanced_json(text: str, start: int) -> str:
    """Return the smallest ``{...}`` substring starting at *start*."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("unbalanced json")


def _extract_answer_json(text: str) -> Any:
    """Extract a JSON object from an anima answer string.

    Tries, in order: the whole trimmed string, a fenced code block, and the
    substring from the first ``{`` to its matching ``}``.  Raises
    :class:`ValueError` when no valid JSON object can be recovered.
    """
    if not isinstance(text, str):
        raise ValueError("empty answer")
    stripped = text.strip()
    if stripped:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    match = _JSON_FENCE_RE.search(text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start != -1:
        try:
            return json.loads(_balanced_json(text, start))
        except json.JSONDecodeError:
            pass
    raise ValueError("no json object in answer")


def _parse_facts(parsed: Any) -> list[Fact]:
    """Convert a parsed answer into a list of :class:`Fact`.

    Raises :class:`ValueError` when the structure is invalid.
    """
    if not isinstance(parsed, dict):
        raise ValueError("answer not an object")
    raw_facts = parsed.get("facts")
    if not isinstance(raw_facts, list):
        raise ValueError("facts not a list")
    facts: list[Fact] = []
    for item in raw_facts:
        if not isinstance(item, dict):
            raise ValueError("fact not an object")
        fact = item.get("fact")
        evidence = item.get("evidence", [])
        if not isinstance(fact, str):
            raise ValueError("fact not a string")
        if not isinstance(evidence, list) or not all(isinstance(e, str) for e in evidence):
            raise ValueError("evidence not a string list")
        facts.append(Fact(fact=fact, evidence=list(evidence)))
    return facts


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

    def __init__(self, config: EnclaveConfig, data_dir: Path, get_supervisor: Callable[[], Any]) -> None:
        self.config = config
        self.data_dir = data_dir
        self.get_supervisor = get_supervisor
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
            try:
                parsed = _extract_answer_json(answer_text)
                facts = _parse_facts(parsed)
            except (ValueError, TypeError):
                audit_id = uuid4().hex
                _write_block_audit(
                    self.data_dir,
                    request_id=body.request_id,
                    case_id=body.case_id,
                    from_anima=body.from_anima,
                    audit_id=audit_id,
                    reason="answer_unparseable",
                )
                self._mark_failed(job, "answer_unparseable", audit_id=audit_id)
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
) -> FastAPI:
    """Build the FastAPI application that serves one enclave instance."""
    gateway = _Gateway(config, data_dir, get_supervisor)
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

    app.include_router(router)
    return app


__all__ = ["AskRequest", "create_gateway_app", "_request_uid"]
