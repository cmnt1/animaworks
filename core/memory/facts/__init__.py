from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Atomic facts: storage, extraction, invalidation and the entity index.

The main names are re-exported lazily, so importing a submodule does not
load the whole package.
"""

import importlib
from typing import Any

__all__ = [
    "FactRecord",
    "facts_dir",
    "fact_file_for_record",
    "FactRecordUpdate",
    "is_valid_until_active",
    "is_fact_active",
    "fact_entity_names",
    "read_fact_records",
    "iter_fact_records",
    "iter_active_fact_records",
    "rewrite_fact_records",
    "find_fact_record",
    "update_fact_record_by_id",
    "update_fact_records_and_append",
    "append_fact_records",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        return getattr(importlib.import_module("core.memory.facts.store"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
