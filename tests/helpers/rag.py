from __future__ import annotations

"""Shared reset helper for the independent RAG singleton owners in tests."""


def reset_rag_state() -> None:
    """Reset embedding-model and vector-store registries for test isolation."""
    from core.memory.rag.embedding import _reset_for_testing as reset_embedding
    from core.memory.rag.vector_registry import _reset_for_testing as reset_vector_registry

    reset_embedding()
    reset_vector_registry()
