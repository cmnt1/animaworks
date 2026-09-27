from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Configured service endpoints used by RAG clients and child processes."""

import os
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class RagEndpoints:
    """URLs for the vector, embedding, and reranking services."""

    vector_url: str | None = None
    embed_url: str | None = None
    rerank_url: str | None = None

    @classmethod
    def from_env(cls) -> RagEndpoints:
        """Read configured endpoints from the process environment."""
        return cls(
            vector_url=_env_url("ANIMAWORKS_VECTOR_URL"),
            embed_url=_env_url("ANIMAWORKS_EMBED_URL"),
            rerank_url=_env_url("ANIMAWORKS_RERANK_URL"),
        )

    @classmethod
    def for_server(cls, port: int, host: str = "127.0.0.1") -> RagEndpoints:
        """Build the internal API URLs for a local server."""
        base = f"http://{host}:{port}/api/internal"
        return cls(
            vector_url=f"{base}/vector",
            embed_url=f"{base}/embed",
            rerank_url=f"{base}/rerank",
        )


_configured: RagEndpoints | None = None
_env_cache: RagEndpoints | None = None
_lock = threading.Lock()


def _env_url(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def configure_endpoints(endpoints: RagEndpoints | None) -> None:
    """Override the configured endpoints; ``None`` restores environment lookup."""
    global _configured, _env_cache
    with _lock:
        _configured = endpoints
        _env_cache = None


def get_endpoints() -> RagEndpoints:
    """Return the explicit endpoint configuration or a cached environment snapshot."""
    global _env_cache
    with _lock:
        if _configured is not None:
            return _configured
        if _env_cache is None:
            _env_cache = RagEndpoints.from_env()
        return _env_cache


def child_env(endpoints: RagEndpoints) -> dict[str, str]:
    """Return the configured endpoint variables to pass to a spawned process."""
    values = {
        "ANIMAWORKS_VECTOR_URL": endpoints.vector_url,
        "ANIMAWORKS_EMBED_URL": endpoints.embed_url,
        "ANIMAWORKS_RERANK_URL": endpoints.rerank_url,
    }
    return {name: value for name, value in values.items() if value is not None}
