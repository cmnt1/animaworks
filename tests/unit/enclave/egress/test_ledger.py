# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the known-value ledger."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from core.enclave.egress.ledger import _load_recorded, record_known_values


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


def test_load_recorded_cache_reads_appended_rows(tmp_path: Path) -> None:
    record_known_values(tmp_path, ["山田太郎"], source="tool")
    assert "山田太郎" in _load_recorded(tmp_path)

    path = tmp_path / "enclave" / "ledger" / "known_values.jsonl"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"value": "千代田区", "source": "external"}, ensure_ascii=False) + "\n")

    recorded = _load_recorded(tmp_path)
    assert "山田太郎" in recorded
    assert "千代田区" in recorded


def test_record_known_values_keeps_cache_warm_for_unchanged_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import core.enclave.egress.ledger as ledger

    record_known_values(tmp_path, ["山田太郎"], source="tool")
    record_known_values(tmp_path, ["山田太郎"], source="tool")
    monkeypatch.setattr(ledger, "_add_recorded_line", lambda *_args: pytest.fail("cache should avoid rereading"))

    assert record_known_values(tmp_path, ["山田太郎"], source="tool") == 0


@pytest.mark.slow
@pytest.mark.performance
def test_load_recorded_second_read_of_100k_rows_is_cached(tmp_path: Path) -> None:
    path = tmp_path / "enclave" / "ledger" / "known_values.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        "".join(
            json.dumps({"value": f"value-{index:06d}", "source": "test"}, ensure_ascii=False) + "\n"
            for index in range(100_000)
        ),
        encoding="utf-8",
    )

    first = _load_recorded(tmp_path)
    assert len(first) == 100_000

    started = time.perf_counter()
    second = _load_recorded(tmp_path)
    elapsed = time.perf_counter() - started

    assert len(second) == 100_000
    assert elapsed < 0.1
