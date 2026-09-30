from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Public API for RAG corruption detection and automatic repair."""

from .detect import (
    RAGRepairService,
    _reset_for_testing,
    classify_corruption_error,
    collection_owner,
    get_repair_lock_path,
    get_repair_service,
    is_repair_locked,
    record_chroma_error,
)
from .types import RepairResult

__all__ = [
    "RAGRepairService",
    "RepairResult",
    "_reset_for_testing",
    "classify_corruption_error",
    "collection_owner",
    "get_repair_lock_path",
    "get_repair_service",
    "is_repair_locked",
    "record_chroma_error",
]
