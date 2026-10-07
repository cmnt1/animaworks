# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""enclave_ask tool — ask an isolated enclave instance from the host side.

The host anima calls this tool to query an enclave gateway over its Unix
socket.  The gateway returns only masked facts plus evidence IDs; this tool
presents them as a short bullet list with the run's ``audit_id``.  Access is
limited to the animas listed in the enclave's ``allowed_animas``.
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from core.i18n import t
from core.integrations._base import dispatch_by_table
from core.integrations._comm_cli import cli_main_safely

logger = logging.getLogger(__name__)

# ── Execution Profile ─────────────────────────────────────

EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "enclave_ask": {"expected_seconds": 60, "background_eligible": True},
}

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


def _ask(client_cfg: Any, question: str, case_id: str, anima_name: str) -> str:
    """POST a question to the enclave gateway and format the reply."""
    payload = {
        "request_id": uuid4().hex,
        "from_anima": anima_name,
        "case_id": case_id,
        "question": question,
    }
    transport = httpx.HTTPTransport(uds=client_cfg.socket_path)
    try:
        with httpx.Client(transport=transport, timeout=float(client_cfg.timeout_s)) as http:
            resp = http.post("http://enclave/v1/ask", json=payload)
    except Exception:
        logger.warning("enclave_ask: could not reach gateway at %s", client_cfg.socket_path)
        return t("enclave.tool.unreachable")

    if resp.status_code == 200:
        try:
            data = resp.json()
        except Exception:
            return t("enclave.tool.unreachable")
        facts = data.get("facts") if isinstance(data, dict) else None
        audit_id = data.get("audit_id") if isinstance(data, dict) else ""
        lines: list[str] = []
        if isinstance(facts, list):
            for fact in facts:
                if not isinstance(fact, dict):
                    continue
                text = fact.get("fact", "")
                evidence = ", ".join(str(e) for e in (fact.get("evidence") or []))
                if evidence:
                    lines.append(t("enclave.tool.fact_line", text=text, evidence=evidence))
                else:
                    lines.append(f"- {text}")
        lines.append(f"audit_id: {audit_id}")
        return "\n".join(lines)

    audit_id = ""
    try:
        body = resp.json()
        if isinstance(body, dict):
            audit_id = str(body.get("audit_id") or "")
    except Exception:
        logger.debug("enclave_ask: non-JSON error body from enclave", exc_info=True)
    msg = t("enclave.tool.failed", code=resp.status_code)
    if audit_id:
        msg = f"{msg} (audit_id: {audit_id})"
    return msg


def _dispatch_enclave_ask(args: dict[str, Any]) -> str:
    from core.config import load_config

    enclave = str(args.get("enclave") or "")
    question = str(args.get("question") or "")
    client_cfg = load_config().enclaves.get(enclave)
    if client_cfg is None:
        return t("enclave.tool.unknown_enclave", enclave=enclave)

    anima_name = _anima_name_from_args(args)
    # An empty allow-list admits nobody (fail closed), not everybody.
    if not anima_name or anima_name not in client_cfg.allowed_animas:
        return t("enclave.tool.anima_not_allowed")

    case_id = args.get("case_id") or _default_case_id(anima_name)
    return _ask(client_cfg, question, _safe_case_id(str(case_id)), anima_name)


_DISPATCH_HANDLERS = {"enclave_ask": _dispatch_enclave_ask}


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call by schema name."""
    return dispatch_by_table(_DISPATCH_HANDLERS, name, args)


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return Anthropic tool_use schemas for the enclave_ask tool."""
    return [
        {
            "name": "enclave_ask",
            "description": t("enclave.tool.schema_description"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "enclave": {
                        "type": "string",
                        "description": t("enclave.tool.schema_enclave"),
                    },
                    "question": {
                        "type": "string",
                        "description": t("enclave.tool.schema_question"),
                    },
                    "case_id": {
                        "type": "string",
                        "description": t("enclave.tool.schema_case_id"),
                    },
                },
                "required": ["enclave", "question"],
            },
        }
    ]


def get_cli_guide() -> str:
    """Return CLI guide text for the tool guide injection."""
    return """\
### enclave — 隔離インスタンスへの質問

機密の質問を隔離された enclave に送り、事実と根拠IDだけの回答を得ます。

```bash
animaworks-tool enclave ask --enclave <名前> --question "<質問>" [--case-id <ID>]
```

**例:**
```bash
animaworks-tool enclave ask --enclave pii --question "この利用者の属性を要約して"
```"""


@cli_main_safely
def cli_main(argv: list[str] | None = None) -> None:
    """Run the animaworks-tool enclave CLI.

    Sub-commands::

        ask --enclave NAME --question TEXT [--case-id ID]
    """
    parser = argparse.ArgumentParser(prog="animaworks-tool enclave", description="Ask an enclave instance")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ask = sub.add_parser("ask", help="Ask the enclave a question")
    p_ask.add_argument("--enclave", required=True, help="Enclave config name")
    p_ask.add_argument("--question", required=True, help="Question to ask")
    p_ask.add_argument("--case-id", default="", help="Optional stable case id")
    p_ask.add_argument("-j", "--json", action="store_true", help="Output raw JSON (unused placeholder)")

    ns = parser.parse_args(argv)

    from core.platform.env import anima_dir_env

    args: dict[str, Any] = {
        "enclave": ns.enclave,
        "question": ns.question,
        "case_id": ns.case_id,
        "anima_dir": anima_dir_env() or "",
    }
    print(dispatch("enclave_ask", args))


__all__ = ["cli_main", "dispatch", "get_cli_guide", "get_tool_schemas"]
