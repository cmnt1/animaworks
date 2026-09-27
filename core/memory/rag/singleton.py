from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Compatibility facade for the split RAG embedding and vector registries."""

from core.memory.rag.embedding import (
    EmbeddingPriority,
    EmbeddingPurpose,
    generate_embeddings,
    get_embedding_e5_prefix_enabled,
    get_embedding_model,
    get_embedding_model_name,
    thread_safe_encode,
)
from core.memory.rag.vector_registry import (
    configure_owner_transport,
    configure_owner_vector_access,
    configure_server_vector_access,
    get_vector_store,
)


def _reset_for_testing() -> None:
    """Reset both split registries for compatibility with existing tests."""
    from core.memory.rag import embedding, vector_registry

    embedding._reset_for_testing()
    vector_registry._reset_for_testing()


__all__ = [
    "EmbeddingPriority",
    "EmbeddingPurpose",
    "_reset_for_testing",
    "configure_owner_transport",
    "configure_owner_vector_access",
    "configure_server_vector_access",
    "generate_embeddings",
    "get_embedding_e5_prefix_enabled",
    "get_embedding_model",
    "get_embedding_model_name",
    "get_vector_store",
    "thread_safe_encode",
]
