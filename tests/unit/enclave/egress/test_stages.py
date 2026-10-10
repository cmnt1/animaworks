# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for individual egress stages (pseudonymize, masker, regex-denylist, command)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.enclave.egress.config import load_egress_config
from core.enclave.egress.models import Fact
from core.enclave.egress.stages import EgressStageError, run_stage


def _stage(stack: dict) -> object:
    cfg = load_egress_config({"stages": [stack]})
    return cfg.stages[0]


# ---------------------------------------------------------------------------
# pseudonymize_ids
# ---------------------------------------------------------------------------


def test_pseudonymize_same_case_is_consistent(tmp_path: Path) -> None:
    stage = _stage({"type": "pseudonymize_ids", "patterns": [{"name": "c", "regex": r"\bC\d{6}\b", "prefix": "P"}]})
    facts = [Fact("C123456 と C123456 と C654321", [])]
    new, count = run_stage(stage, facts, data_dir=tmp_path, case_id="caseA")
    assert new[0].fact == "P-001 と P-001 と P-002"
    assert count == 3

    # Re-running the same case yields the same pseudonyms.
    again, _ = run_stage(stage, facts, data_dir=tmp_path, case_id="caseA")
    assert again[0].fact == "P-001 と P-001 と P-002"


def test_pseudonymize_different_cases_are_independent(tmp_path: Path) -> None:
    stage = _stage({"type": "pseudonymize_ids", "patterns": [{"name": "c", "regex": r"\bC\d{6}\b", "prefix": "P"}]})
    facts = [Fact("C123456", [])]
    run_stage(stage, facts, data_dir=tmp_path, case_id="caseA")
    new, _ = run_stage(stage, facts, data_dir=tmp_path, case_id="caseB")
    assert new[0].fact == "P-001"


def test_pseudonymize_writes_mode_0600_and_dir_0700(tmp_path: Path) -> None:
    stage = _stage({"type": "pseudonymize_ids", "patterns": [{"name": "c", "regex": r"\bC\d{6}\b", "prefix": "P"}]})
    run_stage(stage, [Fact("C123456", [])], data_dir=tmp_path, case_id="caseA")
    path = tmp_path / "enclave" / "pseudonyms" / "caseA.json"
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600
    assert (tmp_path / "enclave" / "pseudonyms").stat().st_mode & 0o777 == 0o700


def test_pseudonymize_applies_to_evidence(tmp_path: Path) -> None:
    stage = _stage({"type": "pseudonymize_ids", "patterns": [{"name": "c", "regex": r"\bC\d{6}\b", "prefix": "P"}]})
    facts = [Fact("C111111", ["C111111 の証跡"])]
    new, _ = run_stage(stage, facts, data_dir=tmp_path, case_id="caseA")
    assert new[0].evidence == ["P-001 の証跡"]


def test_pseudonymize_rejects_bad_case_id(tmp_path: Path) -> None:
    stage = _stage({"type": "pseudonymize_ids", "patterns": [{"name": "c", "regex": r"\bC\d{6}\b", "prefix": "P"}]})
    with pytest.raises(EgressStageError) as exc:
        run_stage(stage, [Fact("C123456", [])], data_dir=tmp_path, case_id="bad case id")
    assert exc.value.reason == "invalid_case_id"


# ---------------------------------------------------------------------------
# regex_denylist
# ---------------------------------------------------------------------------


def test_regex_denylist_redact() -> None:
    stage = _stage({"type": "regex_denylist", "patterns": [{"regex": r"\d{2,4}-\d{2,4}-\d{3,4}", "action": "redact"}]})
    new, count = run_stage(stage, [Fact("電話 090-1234-5678 です", [])], data_dir=Path("."), case_id="x")
    assert new[0].fact == "電話 [REDACTED] です"
    assert count == 1


def test_regex_denylist_block_on_match() -> None:
    stage = _stage({"type": "regex_denylist", "patterns": [{"regex": r"(?:秘密|極秘)", "action": "block"}]})
    with pytest.raises(EgressStageError) as exc:
        run_stage(stage, [Fact("これは極秘の情報です", [])], data_dir=Path("."), case_id="x")
    assert exc.value.reason == "denylist_match"


def test_regex_denylist_no_match_passes() -> None:
    stage = _stage({"type": "regex_denylist", "patterns": [{"regex": r"極秘", "action": "block"}]})
    new, count = run_stage(stage, [Fact("公開情報", [])], data_dir=Path("."), case_id="x")
    assert new[0].fact == "公開情報"
    assert count == 0


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------


def test_command_normal_roundtrip() -> None:
    script = (
        "import json,sys;"
        "data=json.load(sys.stdin);"
        "out={'facts':[{'fact':f['fact']+'!','evidence':f['evidence']} for f in data['facts']]};"
        "json.dump(out,sys.stdout)"
    )
    stage = _stage({"type": "command", "argv": [sys.executable, "-c", script], "timeout_s": 10})
    new, count = run_stage(stage, [Fact("あ", ["ev"])], data_dir=Path("."), case_id="x")
    assert new[0].fact == "あ!"
    assert new[0].evidence == ["ev"]
    assert count == 0


def test_command_nonzero_exit_blocks() -> None:
    script = "import sys; sys.exit(3)"
    stage = _stage({"type": "command", "argv": [sys.executable, "-c", script], "timeout_s": 10})
    with pytest.raises(EgressStageError) as exc:
        run_stage(stage, [Fact("あ", [])], data_dir=Path("."), case_id="x")
    assert exc.value.reason == "command_nonzero_exit"


def test_command_timeout_blocks() -> None:
    script = "import time; time.sleep(5)"
    stage = _stage({"type": "command", "argv": [sys.executable, "-c", script], "timeout_s": 1})
    with pytest.raises(EgressStageError) as exc:
        run_stage(stage, [Fact("あ", [])], data_dir=Path("."), case_id="x")
    assert exc.value.reason == "command_timeout"


def test_command_invalid_json_blocks() -> None:
    script = "import sys; sys.stdout.write('not json')"
    stage = _stage({"type": "command", "argv": [sys.executable, "-c", script], "timeout_s": 10})
    with pytest.raises(EgressStageError) as exc:
        run_stage(stage, [Fact("あ", [])], data_dir=Path("."), case_id="x")
    assert exc.value.reason == "command_invalid_json"
