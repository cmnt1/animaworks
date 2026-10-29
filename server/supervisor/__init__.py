"""Server-level supervision APIs for managing Anima processes."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "HealthConfig": "server.supervisor.manager",
    "ProcessSupervisor": "server.supervisor.manager",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


__all__ = ["HealthConfig", "ProcessSupervisor"]
