# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Operational helpers for enclave health checks and audit summaries."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


def check_gateway_health(socket_path: str, *, timeout: float = 2.0) -> bool:
    """Return whether a Unix-socket gateway answers its health endpoint."""
    if not socket_path or not Path(socket_path).is_socket():
        return False

    try:
        transport = httpx.HTTPTransport(uds=socket_path)
        with httpx.Client(transport=transport, timeout=httpx.Timeout(timeout, connect=timeout)) as client:
            response = client.get("http://enclave/v1/health")
        if response.status_code != 200:
            return False
        payload = response.json()
    except Exception as exc:
        logger.debug("Enclave health check failed (%s)", type(exc).__name__)
        return False

    return isinstance(payload, dict) and payload.get("ok") is True


def count_today_egress_audits(data_dir: Path) -> dict[str, int]:
    """Count successful and blocked egress audits for the current UTC day.

    Audit payloads contain request and answer facts. This helper deliberately
    returns only aggregate counts and never logs or returns record contents.
    """
    today = datetime.now(UTC).strftime("%Y%m%d")
    audit_path = data_dir / "enclave" / "audit" / "egress" / f"{today}.jsonl"
    counts = {"ok": 0, "blocked": 0}
    if not audit_path.is_file():
        return counts

    try:
        with audit_path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed enclave audit record")
                    continue
                if not isinstance(record, dict):
                    continue
                blocked = record.get("blocked")
                if blocked is True:
                    counts["blocked"] += 1
                elif blocked is False:
                    counts["ok"] += 1
    except OSError:
        logger.warning("Could not read today's enclave audit log", exc_info=True)

    return counts


__all__ = ["check_gateway_health", "count_today_egress_audits"]
