# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Enclave mode: an isolated runtime instance that bind to a dedicated socket.

When ``enclave.enabled`` is set, the server refuses to start unless a set of
security guards (see :mod:`core.enclave.guards`) pass — e.g. no external
egress, full-access file permissions, or un-trusted auth.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from core.enclave.config import EnclaveClientConfig, EnclaveConfig

# The guard module imports ``core.config`` and ``core.auth``; defer it so that
# ``core.config.schemas`` (which imports EnclaveConfig) can load without a
# circular import.  The module is imported lazily on first attribute access.
_GUARD_EXPORTS = ("EnclaveViolationError", "collect_enclave_violations", "enforce_enclave_runtime")


def __getattr__(name: str) -> Any:
    if name in _GUARD_EXPORTS:
        guards = import_module("core.enclave.guards")
        value = getattr(guards, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EnclaveClientConfig",
    "EnclaveConfig",
    "EnclaveViolationError",
    "collect_enclave_violations",
    "enforce_enclave_runtime",
]
