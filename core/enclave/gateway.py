# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Gateway: the ingress point of an enclave instance.

The gateway listens on a Unix socket and answers HTTP questions from the host
side.  Each request is bounded by a concurrency semaphore and a hard timeout,
routed to the enclave's ``entry_anima`` (``process_message``), and its answer
is pushed through the egress pipeline so that only masked facts plus their
evidence IDs leave the enclave.  All error responses are free of the original
question and answer bodies.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
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
from core.i18n import t

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


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
    """Holds the per-instance state (semaphore) for one enclave gateway."""

    def __init__(self, config: EnclaveConfig, data_dir: Path, get_supervisor: Callable[[], Any]) -> None:
        self.config = config
        self.data_dir = data_dir
        self.get_supervisor = get_supervisor
        self.semaphore = asyncio.Semaphore(config.max_concurrency)
        self.pipeline: EgressPipeline | None = None

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

    async def _handle_ask(self, body: AskRequest, request: Request) -> JSONResponse:
        async with self.semaphore:
            supervisor = self.get_supervisor()
            if supervisor.is_bootstrapping(self.config.entry_anima):
                return JSONResponse({"error": "entry_bootstrapping"}, status_code=503)

            instruction = t("enclave.gateway.answer_instruction")
            message = f"{instruction}\n\n{body.question}"
            try:
                answer = await supervisor.send_request(
                    anima_name=self.config.entry_anima,
                    method="process_message",
                    params={
                        "message": message,
                        "from_person": f"enclave:{body.from_anima}",
                        "intent": "question",
                        "thread_id": f"enclave-{body.case_id}",
                    },
                    timeout=self.config.request_timeout_s,
                )
            except Exception:
                logger.warning("enclave gateway: entry anima IPC failed", exc_info=True)
                return JSONResponse({"error": "entry_unavailable"}, status_code=502)

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
                return JSONResponse({"error": "answer_unparseable", "audit_id": audit_id}, status_code=422)

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
                return JSONResponse({"error": "egress_blocked", "audit_id": exc.audit_id}, status_code=422)
            except Exception:
                logger.warning("enclave gateway: egress pipeline raised", exc_info=True)
                return JSONResponse({"error": "egress_blocked"}, status_code=422)

            return JSONResponse(
                {
                    "request_id": body.request_id,
                    "audit_id": result.audit_id,
                    "facts": [{"fact": f.fact, "evidence": list(f.evidence)} for f in result.facts],
                }
            )

    async def ask(self, body: AskRequest, request: Request) -> JSONResponse:
        if not self._check_peer(request):
            return JSONResponse({"error": "unauthorized_peer"}, status_code=403)
        try:
            return await asyncio.wait_for(
                self._handle_ask(body, request),
                timeout=self.config.request_timeout_s,
            )
        except TimeoutError:
            return JSONResponse({"error": "timeout"}, status_code=504)


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

    app.include_router(router)
    return app


__all__ = ["AskRequest", "create_gateway_app", "_request_uid"]
