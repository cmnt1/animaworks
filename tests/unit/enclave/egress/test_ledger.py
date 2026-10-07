# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the known-value ledger."""

from __future__ import annotations

from pathlib import Path

from core.enclave.egress.ledger import record_known_values


def test_record_known_values_writes_and_counts(tmp_path: Path) -> None:
    n = record_known_values(tmp_path, ["山田太郎", "千代田区"], source="tool")
    assert n == 2

    path = tmp_path / "enclave" / "ledger" / "known_values.jsonl"
    assert path.exists()
    assert (path.stat().st_mode & 0o777) == 0o600
    assert (tmp_path / "enclave" / "ledger").stat().st_mode & 0o777 == 0o700
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_record_known_values_skips_duplicates(tmp_path: Path) -> None:
    record_known_values(tmp_path, ["山田太郎"], source="tool")
    n = record_known_values(tmp_path, ["山田太郎", "山田 太郎"], source="tool")
    # Normalized duplicates (incl. whitespace variants) are not written again.
    assert n == 0
    path = tmp_path / "enclave" / "ledger" / "known_values.jsonl"
    assert path.read_text(encoding="utf-8").count("\n") == 1
