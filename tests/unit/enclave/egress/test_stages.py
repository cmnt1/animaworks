# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for individual egress stages (pseudonymize, known-values,
regex-denylist, command)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.enclave.egress.config import load_egress_config
from core.enclave.egress.models import Fact
from core.enclave.egress.stages import EgressStageError, run_stage


def _stage(stack: dict) -> object:
    cfg = load_egress_config({"stages": [stack]})
    return cfg.stages[0]


def _write(values: list[str], path: Path) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps({"name": value}) + "\n")


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
# known_values
# ---------------------------------------------------------------------------


def test_known_values_normalizes_katakana_to_hiragana(tmp_path: Path) -> None:
    _write(["ヤマダタロウ"], tmp_path / "v.jsonl")
    stage = _stage({"type": "known_values", "sources": [{"path": "v.jsonl", "format": "jsonl", "fields": ["name"]}]})
    new, _ = run_stage(stage, [Fact("顧客はヤマダタロウと申します", [])], data_dir=tmp_path, case_id="x")
    assert new[0].fact == "顧客は[REDACTED]と申します"


def test_known_values_normalizes_full_width_to_half_width(tmp_path: Path) -> None:
    _write(["０９０１２３４"], tmp_path / "v.jsonl")
    stage = _stage({"type": "known_values", "sources": [{"path": "v.jsonl", "format": "jsonl", "fields": ["name"]}]})
    new, _ = run_stage(stage, [Fact("連絡先は０９０１２３４です", [])], data_dir=tmp_path, case_id="x")
    assert new[0].fact == "連絡先は[REDACTED]です"


def test_known_values_normalizes_whitespace(tmp_path: Path) -> None:
    _write(["山田 太郎"], tmp_path / "v.jsonl")
    stage = _stage({"type": "known_values", "sources": [{"path": "v.jsonl", "format": "jsonl", "fields": ["name"]}]})
    new, _ = run_stage(stage, [Fact("山田 太郎さん", [])], data_dir=tmp_path, case_id="x")
    assert new[0].fact == "[REDACTED]さん"


def test_known_values_ngram_partial_match(tmp_path: Path) -> None:
    _write(["東京都千代田区一番町"], tmp_path / "v.jsonl")
    stage = _stage(
        {
            "type": "known_values",
            "sources": [{"path": "v.jsonl", "format": "jsonl", "fields": ["name"]}],
            "min_length": 2,
            "ngram": 6,
        }
    )
    new, _ = run_stage(stage, [Fact("千代田区一番の住所に住む", [])], data_dir=tmp_path, case_id="x")
    assert new[0].fact == "[REDACTED]の住所に住む"


def test_known_values_ignores_values_below_min_length(tmp_path: Path) -> None:
    _write(["山"], tmp_path / "v.jsonl")
    stage = _stage(
        {
            "type": "known_values",
            "sources": [{"path": "v.jsonl", "format": "jsonl", "fields": ["name"]}],
            "min_length": 2,
        }
    )
    new, _ = run_stage(stage, [Fact("山に登る", [])], data_dir=tmp_path, case_id="x")
    assert new[0].fact == "山に登る"


def test_known_values_replacement_does_not_shift_positions(tmp_path: Path) -> None:
    _write(["山田太郎"], tmp_path / "v.jsonl")
    stage = _stage({"type": "known_values", "sources": [{"path": "v.jsonl", "format": "jsonl", "fields": ["name"]}]})
    new, _ = run_stage(stage, [Fact("本日、山田太郎様がご来店。", [])], data_dir=tmp_path, case_id="x")
    assert new[0].fact == "本日、[REDACTED]様がご来店。"


def test_known_values_source_missing_blocks(tmp_path: Path) -> None:
    stage = _stage({"type": "known_values", "sources": [{"path": "nope.jsonl", "format": "jsonl", "fields": ["name"]}]})
    with pytest.raises(EgressStageError) as exc:
        run_stage(stage, [Fact("何か", [])], data_dir=tmp_path, case_id="x")
    assert exc.value.reason == "known_values_source_missing"


def test_known_values_reads_from_ledger(tmp_path: Path) -> None:
    from core.enclave.egress.ledger import record_known_values

    record_known_values(tmp_path, ["東京都世田谷区"], source="test")
    stage = _stage({"type": "known_values", "sources": []})
    new, _ = run_stage(stage, [Fact("転居先は東京都世田谷区です", [])], data_dir=tmp_path, case_id="x")
    assert new[0].fact == "転居先は[REDACTED]です"


def test_known_values_redacts_overlapping_values(tmp_path: Path) -> None:
    _write(["山田花子", "花子様邸"], tmp_path / "v.jsonl")
    stage = _stage({"type": "known_values", "sources": [{"path": "v.jsonl", "format": "jsonl", "fields": ["name"]}]})
    new, _ = run_stage(stage, [Fact("訪問先は山田花子様邸です", [])], data_dir=tmp_path, case_id="x")
    assert new[0].fact == "訪問先は[REDACTED]です"


def test_known_values_corrupt_ledger_blocks(tmp_path: Path) -> None:
    ledger = tmp_path / "enclave" / "ledger" / "known_values.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("{not json\n", encoding="utf-8")
    stage = _stage({"type": "known_values", "sources": []})
    with pytest.raises(EgressStageError) as exc:
        run_stage(stage, [Fact("text", [])], data_dir=tmp_path, case_id="x")
    assert exc.value.reason == "known_values_ledger_corrupt"


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
