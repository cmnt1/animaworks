from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Compatibility exports for the unified vector client."""

from core.memory.rag.vector_client import VectorClient, VectorStoreRetryableError, VectorTransport

HttpVectorStore = VectorClient

__all__ = ["HttpVectorStore", "VectorStoreRetryableError", "VectorTransport"]
