from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Public API for RAG corruption detection and automatic repair."""

from core.memory.rag.repair_service import (
    RAGRepairService,
    _reset_for_testing,
    get_repair_service,
    record_chroma_error,
)
from core.memory.rag.repair_types import RepairResult
from core.memory.rag.repair_utils import (
    classify_corruption_error,
    collection_owner,
    get_repair_lock_path,
    is_repair_locked,
)

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
