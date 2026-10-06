# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the egress audit writer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from core.enclave.egress.audit import write_audit
from core.enclave.egress.models import EgressRequest, Fact


def test_write_audit_creates_0600_record(tmp_path: Path) -> None:
    req = EgressRequest(request_id="r1", case_id="caseA", from_anima="anima", facts=[Fact("値", ["証跡"])])
    write_audit(
        tmp_path,
        audit_id="abc123",
        request=req,
        input_facts=req.facts,
        output_facts=[Fact("値", ["証跡"])],
        stages=[{"type": "masker", "ok": True, "replacements": 2, "error": None}],
        blocked=False,
        reason=None,
    )

    day = datetime.now(UTC).strftime("%Y%m%d")
    path = tmp_path / "enclave" / "audit" / "egress" / f"{day}.jsonl"
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600
    assert (tmp_path / "enclave" / "audit" / "egress").stat().st_mode & 0o777 == 0o700

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["audit_id"] == "abc123"
    assert record["request_id"] == "r1"
    assert record["case_id"] == "caseA"
    assert record["from_anima"] == "anima"
    assert record["input_facts"][0]["fact"] == "値"
    assert record["output_facts"][0]["evidence"] == ["証跡"]
    assert record["blocked"] is False
    assert record["reason"] is None


def test_write_audit_blocked_outputs_null(tmp_path: Path) -> None:
    req = EgressRequest(request_id="r2", case_id="caseB", from_anima="anima", facts=[Fact("値", [])])
    write_audit(
        tmp_path,
        audit_id="blocked1",
        request=req,
        input_facts=req.facts,
        output_facts=None,
        stages=[{"type": "regex_denylist", "ok": False, "replacements": 0, "error": "denylist_match"}],
        blocked=True,
        reason="denylist_match",
    )
    day = datetime.now(UTC).strftime("%Y%m%d")
    path = tmp_path / "enclave" / "audit" / "egress" / f"{day}.jsonl"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["output_facts"] is None
    assert record["blocked"] is True
    assert record["reason"] == "denylist_match"
