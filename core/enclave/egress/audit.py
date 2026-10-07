# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Audit logging for the egress pipeline.

One JSONL record is appended per pipeline run (success or failure) under
``data_dir/enclave/audit/egress/YYYYMMDD.jsonl`` (file 0600, directory
0700). The append is crash-safe via ``core.platform.atomic_io``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.enclave.egress.fs import ensure_dir_0700, ensure_file_0600
from core.enclave.egress.models import EgressRequest, Fact
from core.platform.atomic_io import append_jsonl_locked

logger = logging.getLogger(__name__)


def _fact_to_dict(fact: Fact) -> dict[str, Any]:
    return {"fact": fact.fact, "evidence": list(fact.evidence)}


def write_audit(
    data_dir: Path,
    *,
    audit_id: str,
    request: EgressRequest,
    input_facts: list[Fact],
    output_facts: list[Fact] | None,
    stages: list[dict[str, Any]],
    blocked: bool,
    reason: str | None,
) -> None:
    """Append one audit record for a pipeline run.

    ``reason`` carries only a stable category, never a text body.
    """
    base = data_dir / "enclave" / "audit" / "egress"
    ensure_dir_0700(base)
    path = base / f"{datetime.now(UTC).strftime('%Y%m%d')}.jsonl"
    ensure_file_0600(path)

    record: dict[str, Any] = {
        "audit_id": audit_id,
        "ts": datetime.now(UTC).isoformat(),
        "request_id": request.request_id,
        "case_id": request.case_id,
        "from_anima": request.from_anima,
        "input_facts": [_fact_to_dict(f) for f in input_facts],
        "output_facts": [_fact_to_dict(f) for f in output_facts] if output_facts is not None else None,
        "stages": stages,
        "blocked": blocked,
        "reason": reason,
    }
    append_jsonl_locked(path, record)
