# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the egress pipeline (fail-closed behavior + audit)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.enclave.egress.config import load_egress_config
from core.enclave.egress.models import EgressBlockedError, EgressRequest, Fact
from core.enclave.egress.pipeline import EgressPipeline


def _audit_records(data_dir: Path) -> list[dict]:
    files = list((data_dir / "enclave" / "audit" / "egress").glob("*.jsonl"))
    records: list[dict] = []
    for path in files:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def _req(facts: list[Fact], case: str = "caseA") -> EgressRequest:
    return EgressRequest(request_id="r1", case_id=case, from_anima="anima", facts=facts)


def test_pipeline_success_writes_audit(tmp_path: Path) -> None:
    cfg = load_egress_config(
        {"stages": [{"type": "regex_denylist", "patterns": [{"regex": r"X\d+", "action": "redact"}]}]}
    )
    pipe = EgressPipeline(cfg, tmp_path)
    result = pipe.run(_req([Fact("IDはX123です", [])]))
    assert result.facts[0].fact == "IDは[REDACTED]です"
    assert len(result.audit_id) == 32

    records = _audit_records(tmp_path)
    assert len(records) == 1
    assert records[0]["blocked"] is False
    assert records[0]["output_facts"][0]["fact"] == "IDは[REDACTED]です"
    assert records[0]["request_id"] == "r1"
    assert records[0]["case_id"] == "caseA"
    assert records[0]["stages"][0]["ok"] is True


def test_pipeline_stage_error_blocks_with_audit(tmp_path: Path) -> None:
    cfg = load_egress_config(
        {"stages": [{"type": "regex_denylist", "patterns": [{"regex": "極秘", "action": "block"}]}]}
    )
    pipe = EgressPipeline(cfg, tmp_path)
    with pytest.raises(EgressBlockedError) as exc:
        pipe.run(_req([Fact("これは極秘です", [])]))
    assert exc.value.reason == "denylist_match"

    records = _audit_records(tmp_path)
    assert len(records) == 1
    assert records[0]["blocked"] is True
    assert records[0]["output_facts"] is None
    assert records[0]["reason"] == "denylist_match"
    assert records[0]["stages"][0]["ok"] is False
    assert records[0]["stages"][0]["error"] == "denylist_match"


def test_pipeline_blocks_too_many_facts(tmp_path: Path) -> None:
    cfg = load_egress_config({"stages": [{"type": "regex_denylist", "patterns": []}], "max_facts": 1})
    pipe = EgressPipeline(cfg, tmp_path)
    with pytest.raises(EgressBlockedError) as exc:
        pipe.run(_req([Fact("あ", []), Fact("い", [])]))
    assert exc.value.reason == "too_many_facts"
    assert _audit_records(tmp_path)[0]["blocked"] is True


def test_pipeline_blocks_on_bad_command_structure(tmp_path: Path) -> None:
    script = "import json,sys;json.dump({'facts':[{'fact': 123, 'evidence': []}]},sys.stdout)"
    cfg = load_egress_config({"stages": [{"type": "command", "argv": [sys.executable, "-c", script], "timeout_s": 10}]})
    pipe = EgressPipeline(cfg, tmp_path)
    with pytest.raises(EgressBlockedError) as exc:
        pipe.run(_req([Fact("あ", [])]))
    assert exc.value.reason == "command_invalid_structure"


def test_pipeline_masker_stage_masks_pii(tmp_path: Path) -> None:
    cfg = load_egress_config(
        {
            "stages": [
                {"type": "masker", "profile": "default"},
                {"type": "regex_denylist", "patterns": [{"regex": r"極秘", "action": "block"}]},
            ]
        }
    )
    pipe = EgressPipeline(cfg, tmp_path)
    result = pipe.run(_req([Fact("山田太郎は東京に住む 電話 090-1234-5678", [])]))
    assert "山田" not in result.facts[0].fact
    assert "090-1234-5678" not in result.facts[0].fact
    assert "[MASK-PER]" in result.facts[0].fact
    assert "[MASK-PHONE]" in result.facts[0].fact
    assert _audit_records(tmp_path)[0]["blocked"] is False
