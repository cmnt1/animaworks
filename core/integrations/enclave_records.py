# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Read configured JSONL datasets from inside an enclave runtime."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from core.enclave.config import EnclaveDatasetConfig
from core.enclave.raw_store import try_save_raw
from core.i18n import t
from core.integrations._base import dispatch_by_table

logger = logging.getLogger(__name__)

_MAX_SEARCH_LIMIT = 100


class _EnclaveDisabledError(ValueError):
    """Raised when a records tool is called outside an enabled enclave."""


class _DatasetNotConfiguredError(ValueError):
    """Raised when a dataset name is absent from enclave configuration."""


class _DatasetPathError(ValueError):
    """Raised when a dataset path is invalid or escapes the data directory."""


def _resolve_dataset_path(data_dir: Path, dataset: EnclaveDatasetConfig) -> Path:
    """Resolve a configured JSONL path and enforce the data-directory boundary."""
    relative_path = Path(dataset.path)
    if relative_path.is_absolute():
        raise _DatasetPathError("dataset path must be relative")

    try:
        root = data_dir.resolve()
        resolved = (root / relative_path).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _DatasetPathError("dataset path cannot be resolved") from exc

    if not resolved.is_relative_to(root):
        raise _DatasetPathError("dataset path escapes the data directory")
    if resolved.suffix.lower() != ".jsonl" or not resolved.is_file():
        raise _DatasetPathError("dataset must be a JSONL file")
    return resolved


def _dataset_context(dataset_name: str) -> tuple[Path, Path, EnclaveDatasetConfig]:
    """Load an enabled enclave dataset and return its data root and file path."""
    from core.config import load_config
    from core.paths import get_data_dir

    config = load_config()
    if config.enclave.enabled is not True:
        raise _EnclaveDisabledError

    dataset = config.enclave.datasets.get(dataset_name)
    if dataset is None:
        raise _DatasetNotConfiguredError

    data_dir = get_data_dir()
    return data_dir, _resolve_dataset_path(data_dir, dataset), dataset


def _iter_records(path: Path, dataset_name: str) -> Iterator[dict[str, Any]]:
    """Yield JSON object records, skipping malformed lines without logging data."""
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSONL record in dataset %s at line %d", dataset_name, line_number)
                continue
            if isinstance(record, dict):
                yield record


def _tool_error(exc: Exception, dataset_name: str) -> str:
    if isinstance(exc, _EnclaveDisabledError):
        return t("enclave.records.only")
    if isinstance(exc, _DatasetNotConfiguredError):
        return t("enclave.records.dataset_not_configured", dataset=dataset_name)
    logger.warning("Could not read enclave dataset %s (%s)", dataset_name, type(exc).__name__)
    return t("enclave.records.unavailable")


def enclave_records_search(dataset: str, query: str, limit: int = 20) -> dict[str, Any] | str:
    """Search configured searchable fields and save matching records privately."""
    if not isinstance(dataset, str) or not dataset:
        return t("enclave.records.dataset_required")
    if not isinstance(query, str) or not query.strip():
        return t("enclave.records.query_required")
    if isinstance(limit, bool) or not isinstance(limit, int):
        return t("enclave.records.limit_integer")

    try:
        _, path, dataset_config = _dataset_context(dataset)
        needle = query.strip().casefold()
        matches: list[dict[str, Any]] = []
        for record in _iter_records(path, dataset):
            for field in dataset_config.searchable_fields:
                value = record.get(field)
                if isinstance(value, str) and needle in value.casefold():
                    matches.append(record)
                    break
            if len(matches) >= max(1, min(limit, _MAX_SEARCH_LIMIT)):
                break
        result: dict[str, Any] = {"records": matches}
        raw_path = try_save_raw("enclave_records_search", matches)
        if raw_path is not None:
            result["raw_path"] = str(raw_path)
        return result
    except Exception as exc:
        return _tool_error(exc, dataset)


def enclave_records_get(dataset: str, record_id: str) -> dict[str, Any] | str:
    """Fetch one record by its configured ID field."""
    if not isinstance(dataset, str) or not dataset:
        return t("enclave.records.dataset_required")
    if not isinstance(record_id, str) or not record_id:
        return t("enclave.records.id_required")

    try:
        _, path, dataset_config = _dataset_context(dataset)
        for record in _iter_records(path, dataset):
            value = record.get(dataset_config.id_field)
            if isinstance(value, (str, int, float)) and str(value) == record_id:
                result: dict[str, Any] = {"record": record}
                raw_path = try_save_raw("enclave_records_get", record)
                if raw_path is not None:
                    result["raw_path"] = str(raw_path)
                return result
        return t("enclave.records.not_found", record_id=record_id)
    except Exception as exc:
        return _tool_error(exc, dataset)


def _dispatch_search(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_records_search(
        dataset=args.get("dataset", ""),
        query=args.get("query", ""),
        limit=args.get("limit", 20),
    )


def _dispatch_get(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_records_get(
        dataset=args.get("dataset", ""),
        record_id=args.get("record_id", ""),
    )


_DISPATCH_HANDLERS = {
    "enclave_records_search": _dispatch_search,
    "enclave_records_get": _dispatch_get,
}


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a records tool call by its schema name."""
    return dispatch_by_table(_DISPATCH_HANDLERS, name, args)


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return tool schemas for searching and fetching enclave datasets."""
    return [
        {
            "name": "enclave_records_search",
            "description": t("enclave.records.schema_search"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "dataset": {"type": "string", "description": t("enclave.records.schema_dataset")},
                    "query": {"type": "string", "description": t("enclave.records.schema_query")},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": _MAX_SEARCH_LIMIT,
                        "default": 20,
                        "description": t("enclave.records.schema_limit"),
                    },
                },
                "required": ["dataset", "query"],
            },
        },
        {
            "name": "enclave_records_get",
            "description": t("enclave.records.schema_get"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "dataset": {"type": "string", "description": t("enclave.records.schema_dataset")},
                    "record_id": {"type": "string", "description": t("enclave.records.schema_record_id")},
                },
                "required": ["dataset", "record_id"],
            },
        },
    ]


__all__ = ["dispatch", "enclave_records_get", "enclave_records_search", "get_tool_schemas"]
