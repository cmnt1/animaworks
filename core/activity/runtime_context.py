from __future__ import annotations

"""Runtime-session context port for activity logging."""

from collections.abc import Callable
from typing import Protocol


class RuntimeSessionContextLike(Protocol):
    """Structural subset of an execution context used by activity entries."""

    trigger: str
    session_type: str


RuntimeSessionProvider = Callable[[], RuntimeSessionContextLike | None]
_runtime_session_provider: RuntimeSessionProvider | None = None


def set_runtime_session_provider(provider: RuntimeSessionProvider | None) -> None:
    """Inject the active-session lookup without depending on its owner package."""
    global _runtime_session_provider
    _runtime_session_provider = provider


def current_runtime_session() -> RuntimeSessionContextLike | None:
    """Return the active session from the injected execution-context provider."""
    if _runtime_session_provider is None:
        return None
    return _runtime_session_provider()
