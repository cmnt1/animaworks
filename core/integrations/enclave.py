# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Host-side tools for submitting and managing enclave ask jobs.

The host anima talks to an enclave gateway over its Unix socket. Questions
return a job ID immediately; status and cancellation are separate operations,
and completed results are also delivered to the caller's inbox by the host
server.
"""

from __future__ import annotations

import argparse
import logging
import math
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx

from core.i18n import t
from core.integrations._base import dispatch_by_table
from core.integrations._comm_cli import cli_main_safely

logger = logging.getLogger(__name__)


class EnclaveUnreachable(Exception):
    """Raised when an enclave gateway socket cannot be reached."""

    def __init__(self, enclave_name: str) -> None:
        super().__init__(enclave_name)
        self.enclave_name = enclave_name


class EnclavePermissionError(EnclaveUnreachable):
    """Raised when the socket is reachable but access is denied."""


# ── Execution Profile ─────────────────────────────────────

EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "enclave_ask": {"expected_seconds": 2, "background_eligible": False},
    "enclave_status": {"expected_seconds": 2, "background_eligible": False},
    "enclave_cancel": {"expected_seconds": 2, "background_eligible": False},
}

_HTTP_TIMEOUT_S = 30.0
_POLL_INTERVAL_S = 10.0
_TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled"})
_CASE_ID_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_case_id(value: str) -> str:
    """Make *value* safe for a gateway ``case_id`` (max 64 chars)."""
    cleaned = _CASE_ID_SAFE.sub("-", value)
    if not cleaned:
        return "case"
    return cleaned[:64]


def _default_case_id(anima_name: str) -> str:
    return _safe_case_id(f"{anima_name}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}")


def _anima_name_from_args(args: dict[str, Any]) -> str:
    anima_dir = args.get("anima_dir")
    if isinstance(anima_dir, str) and anima_dir:
        return Path(anima_dir).name
    return ""


def format_facts(facts: Any) -> list[str]:
    """Format enclave facts consistently for tool replies and inbox reports."""
    lines: list[str] = []
    if not isinstance(facts, list):
        return lines
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        text = str(fact.get("fact") or "")
        evidence_items = fact.get("evidence")
        evidence = ", ".join(str(item) for item in evidence_items) if isinstance(evidence_items, list) else ""
        if evidence:
            lines.append(t("enclave.tool.fact_line", text=text, evidence=evidence))
        else:
            lines.append(f"- {text}")
    return lines


def _audit_line(audit_id: Any) -> str:
    return t("enclave.tool.audit_id", audit_id=str(audit_id))


def _gateway_client(client_cfg: Any) -> httpx.Client:
    """Build a short-timeout HTTP client over the configured Unix socket."""
    transport = httpx.HTTPTransport(uds=client_cfg.socket_path)
    # timeout_s is kept in configuration for compatibility but is not a job
    # wait timeout. Every gateway request should return quickly.
    return httpx.Client(transport=transport, timeout=_HTTP_TIMEOUT_S)


def fetch_enclave_usage(
    enclave_name: str,
    client_cfg: Any,
    days: int,
    anima: str | None = None,
) -> dict[str, Any] | None:
    """Fetch token-usage summaries from an enclave gateway.

    Returns the full gateway response (``{"name", "days", "animas"}``) on
    success, ``None`` when the requested anima does not exist on the encore
    (HTTP 404).  Raises :class:`EnclavePermissionError` on a socket
    permission failure and :class:`EnclaveUnreachable` when the socket
    cannot be connected to at all.
    """
    params: dict[str, Any] = {"days": days}
    if anima:
        params["anima"] = anima
    try:
        with _gateway_client(client_cfg) as http:
            response = http.get("http://enclave/v1/usage", params=params)
    except PermissionError as exc:
        raise EnclavePermissionError(enclave_name) from exc
    except (OSError, httpx.TransportError) as exc:
        raise EnclaveUnreachable(enclave_name) from exc

    if response.status_code != 200:
        return None
    data = _response_json(response)
    return data


def _job_url(job_id: str) -> str:
    return f"http://enclave/v1/ask/{quote(job_id, safe='')}"


def _response_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        data = response.json()
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _response_error(response: httpx.Response) -> str:
    data = _response_json(response)
    audit_id = str(data.get("audit_id") or "") if data is not None else ""
    message = t("enclave.tool.failed", code=response.status_code)
    if audit_id:
        message = f"{message}\n{_audit_line(audit_id)}"
    return message


def _submission_message(enclave: str, job_id: str, status: str) -> str:
    status_command = f"animaworks-tool enclave status --enclave {enclave} --job-id {job_id}"
    return t(
        "enclave.tool.job_submitted",
        job_id=job_id,
        status=status,
        status_command=status_command,
    )


def _format_completed_result(data: dict[str, Any]) -> str:
    lines = format_facts(data.get("facts"))
    audit_id = data.get("audit_id")
    if audit_id:
        lines.append(_audit_line(audit_id))
    if not lines:
        lines.append(t("enclave.tool.job_done_no_facts", job_id=str(data.get("job_id") or "")))
    return "\n".join(lines)


def _format_job_status(data: dict[str, Any]) -> str:
    job_id = str(data.get("job_id") or "")
    status = str(data.get("status") or "unknown")
    case_id = str(data.get("case_id") or "")
    lines = [
        t("enclave.tool.job_status_header", job_id=job_id, status=status, case_id=case_id),
        t("enclave.tool.elapsed", elapsed=_format_elapsed(data.get("elapsed_s"))),
        t("enclave.tool.queued_ahead", queued_ahead=data.get("queued_ahead", 0)),
        t("enclave.tool.last_activity", last_activity_at=str(data.get("last_activity_at") or "-")),
    ]

    progress = data.get("progress")
    if isinstance(progress, list):
        for entry in progress[-5:]:
            if not isinstance(entry, dict):
                continue
            lines.append(
                t(
                    "enclave.tool.progress_line",
                    at=str(entry.get("at") or "-"),
                    text=str(entry.get("text") or ""),
                )
            )

    if status == "done":
        lines.extend(format_facts(data.get("facts")))
        if data.get("audit_id"):
            lines.append(_audit_line(data["audit_id"]))
    if data.get("error"):
        lines.append(t("enclave.tool.job_error", error=str(data["error"])))
    return "\n".join(lines)


def _format_elapsed(value: Any) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = 0.0
    if not math.isfinite(seconds):
        seconds = 0.0
    return f"{max(0.0, seconds):.1f}s"


def _wait_for_job(
    http: httpx.Client,
    *,
    enclave: str,
    job_id: str,
    anima_name: str,
    initial_status: str,
    wait_s: float,
) -> str:
    deadline = time.monotonic() + wait_s
    status = initial_status
    latest_data: dict[str, Any] | None = None

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            response = http.get(
                _job_url(job_id),
                params={"from_anima": anima_name},
                timeout=min(_HTTP_TIMEOUT_S, remaining),
            )
        except Exception:
            logger.warning("enclave_ask: status polling failed for job %s", job_id)
            break
        if response.status_code != 200:
            logger.warning("enclave_ask: status polling returned HTTP %d for job %s", response.status_code, job_id)
            break
        latest_data = _response_json(response)
        if latest_data is None:
            logger.warning("enclave_ask: invalid status response for job %s", job_id)
            break

        status = str(latest_data.get("status") or status)
        if status in _TERMINAL_STATUSES:
            if status == "done":
                return _format_completed_result(latest_data)
            return _format_job_status(latest_data)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(_POLL_INTERVAL_S, remaining))

    if latest_data is not None and latest_data.get("error"):
        status = str(latest_data.get("status") or status)
    return _submission_message(enclave, job_id, status)


def _ask(
    client_cfg: Any,
    question: str,
    case_id: str,
    anima_name: str,
    enclave: str,
    wait_s: Any = 0,
) -> str:
    """POST a question and optionally poll its job for a bounded period."""
    payload = {
        "request_id": uuid4().hex,
        "from_anima": anima_name,
        "case_id": case_id,
        "question": question,
    }
    try:
        wait_seconds = max(0.0, float(wait_s or 0))
    except (TypeError, ValueError):
        wait_seconds = 0.0
    if not math.isfinite(wait_seconds):
        wait_seconds = 0.0

    try:
        with _gateway_client(client_cfg) as http:
            response = http.post("http://enclave/v1/ask", json=payload)
            if response.status_code != 202:
                return _response_error(response)
            data = _response_json(response)
            if data is None or not isinstance(data.get("job_id"), str) or not data["job_id"]:
                return t("enclave.tool.unreachable")

            job_id = data["job_id"]
            status = str(data.get("status") or "queued")
            if wait_seconds > 0:
                return _wait_for_job(
                    http,
                    enclave=enclave,
                    job_id=job_id,
                    anima_name=anima_name,
                    initial_status=status,
                    wait_s=wait_seconds,
                )
            return _submission_message(enclave, job_id, status)
    except Exception:
        logger.warning("enclave_ask: could not reach gateway at %s", client_cfg.socket_path)
        return t("enclave.tool.unreachable")


def _request_context(args: dict[str, Any]) -> tuple[str, Any, str] | str:
    from core.config import load_config

    enclave = str(args.get("enclave") or "")
    client_cfg = load_config().enclaves.get(enclave)
    if client_cfg is None:
        return t("enclave.tool.unknown_enclave", enclave=enclave)

    anima_name = _anima_name_from_args(args)
    # An empty allow-list admits nobody (fail closed), for every job action.
    if not anima_name or anima_name not in client_cfg.allowed_animas:
        return t("enclave.tool.anima_not_allowed")
    return enclave, client_cfg, anima_name


def _dispatch_enclave_ask(args: dict[str, Any]) -> str:
    context = _request_context(args)
    if isinstance(context, str):
        return context
    enclave, client_cfg, anima_name = context

    question = str(args.get("question") or "")
    case_id = args.get("case_id") or _default_case_id(anima_name)
    return _ask(
        client_cfg,
        question,
        _safe_case_id(str(case_id)),
        anima_name,
        enclave,
        args.get("wait_s", 0),
    )


def _dispatch_enclave_status(args: dict[str, Any]) -> str:
    context = _request_context(args)
    if isinstance(context, str):
        return context
    _, client_cfg, anima_name = context
    job_id = str(args.get("job_id") or "")
    if not job_id:
        return t("enclave.tool.job_id_required")

    try:
        with _gateway_client(client_cfg) as http:
            response = http.get(_job_url(job_id), params={"from_anima": anima_name})
    except Exception:
        logger.warning("enclave_status: could not reach gateway at %s", client_cfg.socket_path)
        return t("enclave.tool.unreachable")
    if response.status_code != 200:
        return _response_error(response)
    data = _response_json(response)
    if data is None:
        return t("enclave.tool.unreachable")
    return _format_job_status(data)


def _dispatch_enclave_cancel(args: dict[str, Any]) -> str:
    context = _request_context(args)
    if isinstance(context, str):
        return context
    _, client_cfg, anima_name = context
    job_id = str(args.get("job_id") or "")
    if not job_id:
        return t("enclave.tool.job_id_required")

    try:
        with _gateway_client(client_cfg) as http:
            response = http.delete(_job_url(job_id), params={"from_anima": anima_name})
    except Exception:
        logger.warning("enclave_cancel: could not reach gateway at %s", client_cfg.socket_path)
        return t("enclave.tool.unreachable")
    if not response.is_success:
        return _response_error(response)

    data = _response_json(response)
    status = str(data.get("status") or "cancelled") if data is not None else "cancelled"
    return t("enclave.tool.job_cancelled", job_id=job_id, status=status)


_DISPATCH_HANDLERS = {
    "enclave_ask": _dispatch_enclave_ask,
    "enclave_status": _dispatch_enclave_status,
    "enclave_cancel": _dispatch_enclave_cancel,
}


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call by schema name."""
    return dispatch_by_table(_DISPATCH_HANDLERS, name, args)


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return Anthropic tool-use schemas for enclave ask job operations."""
    return [
        {
            "name": "enclave_ask",
            "description": t("enclave.tool.schema_description"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "enclave": {"type": "string", "description": t("enclave.tool.schema_enclave")},
                    "question": {"type": "string", "description": t("enclave.tool.schema_question")},
                    "case_id": {"type": "string", "description": t("enclave.tool.schema_case_id")},
                    "wait_s": {
                        "type": "integer",
                        "minimum": 0,
                        "description": t("enclave.tool.schema_wait_s"),
                    },
                },
                "required": ["enclave", "question"],
            },
        },
        {
            "name": "enclave_status",
            "description": t("enclave.tool.schema_status_description"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "enclave": {"type": "string", "description": t("enclave.tool.schema_enclave")},
                    "job_id": {"type": "string", "description": t("enclave.tool.schema_job_id")},
                },
                "required": ["enclave", "job_id"],
            },
        },
        {
            "name": "enclave_cancel",
            "description": t("enclave.tool.schema_cancel_description"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "enclave": {"type": "string", "description": t("enclave.tool.schema_enclave")},
                    "job_id": {"type": "string", "description": t("enclave.tool.schema_job_id")},
                },
                "required": ["enclave", "job_id"],
            },
        },
    ]


def get_cli_guide() -> str:
    """Return CLI guide text for the tool guide injection."""
    return """\
### enclave — 隔離インスタンスへの質問

機密の質問を隔離された enclave に送り、job_id を受け取ります。状態・途中経過を確認でき、完了結果は inbox に届きます。

```bash
animaworks-tool enclave ask --enclave <名前> --question "<質問>" [--case-id <ID>] [--wait <秒>]
animaworks-tool enclave status --enclave <名前> --job-id <job_id>
animaworks-tool enclave cancel --enclave <名前> --job-id <job_id>
```

**例:**
```bash
animaworks-tool enclave ask --enclave pii --question "集計内容を確認して"
animaworks-tool enclave status --enclave pii --job-id <job_id>
```"""


@cli_main_safely
def cli_main(argv: list[str] | None = None) -> None:
    """Run the animaworks-tool enclave CLI.

    Sub-commands::

        ask --enclave NAME --question TEXT [--case-id ID] [--wait SECONDS]
        status --enclave NAME --job-id ID
        cancel --enclave NAME --job-id ID
    """
    parser = argparse.ArgumentParser(prog="animaworks-tool enclave", description="Manage enclave ask jobs")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ask = sub.add_parser("ask", help="Submit a question to the enclave")
    p_ask.add_argument("--enclave", required=True, help="Enclave config name")
    p_ask.add_argument("--question", required=True, help="Question to ask")
    p_ask.add_argument("--case-id", default="", help="Optional stable case id")
    p_ask.add_argument("--wait", dest="wait_s", type=int, default=0, help="Wait up to this many seconds for completion")
    p_ask.add_argument("-j", "--json", action="store_true", help="Output raw JSON (unused placeholder)")

    for command, help_text in (("status", "Show job status"), ("cancel", "Cancel a job")):
        job_parser = sub.add_parser(command, help=help_text)
        job_parser.add_argument("--enclave", required=True, help="Enclave config name")
        job_parser.add_argument("--job-id", required=True, help="Job ID returned by enclave ask")

    ns = parser.parse_args(argv)

    from core.platform.env import anima_dir_env

    args: dict[str, Any] = {
        "enclave": ns.enclave,
        "anima_dir": anima_dir_env() or "",
    }
    if ns.command == "ask":
        args.update(
            {
                "question": ns.question,
                "case_id": ns.case_id,
                "wait_s": ns.wait_s,
            }
        )
        schema_name = "enclave_ask"
    else:
        args["job_id"] = ns.job_id
        schema_name = f"enclave_{ns.command}"
    print(dispatch(schema_name, args))


__all__ = [
    "cli_main",
    "dispatch",
    "fetch_enclave_usage",
    "format_facts",
    "get_cli_guide",
    "get_tool_schemas",
    "EnclaveUnreachable",
    "EnclavePermissionError",
]
