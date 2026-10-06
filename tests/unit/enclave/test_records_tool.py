# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for enclave-local JSONL records tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import invalidate_cache
from core.integrations.enclave_records import enclave_records_get, enclave_records_search
from core.tooling.policy.registry import TOOL_MODULES, get_tool_modules
from tests.helpers.filesystem import DEFAULT_TEST_CONFIG


def _write_config(data_dir: Path, *, enabled: bool = True, dataset_path: str = "data/customers.jsonl") -> None:
    config: dict[str, Any] = dict(DEFAULT_TEST_CONFIG)
    config["enclave"] = {
        "enabled": enabled,
        "datasets": {
            "customers": {
                "path": dataset_path,
                "id_field": "customer_id",
                "sensitive_fields": ["name", "phone", "email"],
                "searchable_fields": ["customer_id", "name", "email"],
            }
        },
    }
    (data_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    invalidate_cache()


def _write_dataset(data_dir: Path) -> None:
    dataset_path = data_dir / "data" / "customers.jsonl"
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "customer_id": "C000001",
            "name": "青葉 葵",
            "phone": "000-0000-0001",
            "email": "customer001@example.invalid",
            "note": "not searchable",
        },
        {
            "customer_id": "C000002",
            "name": "水野 凛",
            "phone": "000-0000-0002",
            "email": "customer002@example.invalid",
            "note": "also not searchable",
        },
    ]
    dataset_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def test_search_returns_matches_and_registers_sensitive_values(data_dir: Path) -> None:
    _write_dataset(data_dir)
    _write_config(data_dir)

    results = enclave_records_search("customers", "C000001")

    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["name"] == "青葉 葵"
    ledger_path = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert {item["value"] for item in ledger} == {
        "青葉 葵",
        "000-0000-0001",
        "customer001@example.invalid",
    }
    assert {item["source"] for item in ledger} == {"dataset:customers"}


def test_search_only_uses_configured_searchable_fields(data_dir: Path) -> None:
    _write_dataset(data_dir)
    _write_config(data_dir)

    results = enclave_records_search("customers", "not searchable")

    assert results == []
    assert not (data_dir / "enclave" / "ledger" / "known_values.jsonl").exists()


def test_get_returns_record_and_registers_sensitive_values(data_dir: Path) -> None:
    _write_dataset(data_dir)
    _write_config(data_dir)

    record = enclave_records_get("customers", "C000002")

    assert isinstance(record, dict)
    assert record["email"] == "customer002@example.invalid"
    ledger_path = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert {item["value"] for item in ledger} == {
        "水野 凛",
        "000-0000-0002",
        "customer002@example.invalid",
    }


def test_dataset_path_outside_data_dir_is_rejected(data_dir: Path) -> None:
    _write_dataset(data_dir)
    outside_path = data_dir.parent / "outside.jsonl"
    outside_path.write_text('{"customer_id":"C999999","name":"must not be returned"}\n', encoding="utf-8")
    _write_config(data_dir, dataset_path="../outside.jsonl")

    result = enclave_records_get("customers", "C999999")

    assert isinstance(result, str)
    assert "安全に参照" in result
    assert "must not be returned" not in result
    assert not (data_dir / "enclave" / "ledger" / "known_values.jsonl").exists()


def test_disabled_enclave_returns_enclave_only_error(data_dir: Path) -> None:
    _write_dataset(data_dir)
    _write_config(data_dir, enabled=False)

    result = enclave_records_search("customers", "C000001")

    assert isinstance(result, str)
    assert "enclave 内でだけ" in result
    assert "enclave_records" not in TOOL_MODULES
    assert "enclave_records" not in get_tool_modules()


def test_enabled_enclave_registers_records_tools_only_for_its_runtime() -> None:
    assert "enclave_records" not in TOOL_MODULES
    assert "enclave_records" not in get_tool_modules(enclave_enabled=False)
    assert "enclave_records" in get_tool_modules(enclave_enabled=True)


def test_records_tool_is_registered_only_in_enclave_mode(data_dir: Path) -> None:
    from core.config.models import PermissionsConfig
    from core.tooling.permissions import get_permitted_tools
    from core.tooling.policy.registry import TOOL_MODULES, get_tool_modules
    from core.tooling.policy.schemas.loader import load_external_schemas

    _write_config(data_dir, enabled=False)
    assert "enclave_records" not in TOOL_MODULES
    assert "enclave_records" not in get_tool_modules()
    assert "enclave_records" not in get_permitted_tools(PermissionsConfig())
    assert load_external_schemas(["enclave_records"]) == []

    _write_config(data_dir, enabled=True)
    assert get_tool_modules()["enclave_records"] == "core.integrations.enclave_records"
    assert "enclave_records" in get_permitted_tools(PermissionsConfig())
    schema_names = {schema["name"] for schema in load_external_schemas(["enclave_records"])}
    assert schema_names == {"enclave_records_search", "enclave_records_get"}
