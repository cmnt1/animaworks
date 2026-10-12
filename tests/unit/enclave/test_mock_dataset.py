# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for deterministic enclave mock data generation."""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.enclave.make_mock_dataset import generate_mock_dataset


def _read_jsonl(path: Path) -> list[dict[str, str]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_mock_dataset_counts_fields_and_id_formats(tmp_path: Path) -> None:
    customers_path, tickets_path = generate_mock_dataset(tmp_path / "mock")
    customers = _read_jsonl(customers_path)
    tickets = _read_jsonl(tickets_path)

    assert len(customers) == 100
    assert len(tickets) == 300
    assert all(re.fullmatch(r"C\d{6}", record["customer_id"]) for record in customers)
    assert all(re.fullmatch(r"TK\d{6}", record["ticket_id"]) for record in tickets)
    assert all({"name", "kana", "address", "phone", "email", "plan"} <= record.keys() for record in customers)
    assert all({"customer_id", "created_at", "category", "body"} <= record.keys() for record in tickets)

    customers_by_id = {record["customer_id"]: record for record in customers}
    assert all(record["customer_id"] in customers_by_id for record in tickets)
    assert any(customers_by_id[record["customer_id"]]["name"] in record["body"] for record in tickets)
    assert any(customers_by_id[record["customer_id"]]["phone"] in record["body"] for record in tickets)


def test_mock_dataset_is_reproducible_with_fixed_seed(tmp_path: Path) -> None:
    first_customers, first_tickets = generate_mock_dataset(tmp_path / "first")
    second_customers, second_tickets = generate_mock_dataset(tmp_path / "second")

    assert first_customers.read_bytes() == second_customers.read_bytes()
    assert first_tickets.read_bytes() == second_tickets.read_bytes()
