from __future__ import annotations

"""Memory APIs, loaded only when explicitly requested."""

from importlib import import_module
from typing import Any

_EXPORTS = {"MemoryManager": "core.memory.manager"}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


__all__ = ["MemoryManager"]
