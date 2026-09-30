from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""RAG (Retrieval-Augmented Generation) subsystem.

Provides dense vector search capabilities with:
- Vector similarity search (semantic)
- Temporal decay scoring
"""

from core.memory.rag.indexer import IndexDirectoryResult, MemoryIndexer
from core.memory.rag.retriever import MemoryRetriever
from core.memory.rag.store import ChromaVectorStore, VectorStore

__all__ = [
    "VectorStore",
    "ChromaVectorStore",
    "MemoryIndexer",
    "IndexDirectoryResult",
    "MemoryRetriever",
]
