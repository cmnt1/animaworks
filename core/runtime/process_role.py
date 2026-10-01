# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Process role metadata shared by AnimaWorks process entry points."""

from __future__ import annotations

from typing import Literal, cast

from core.platform.process_role import (
    PROCESS_ROLE_ENV as PROCESS_ROLE_ENV,
)
from core.platform.process_role import (
    get_process_role_env,
    set_process_role_env,
)

ProcessRole = Literal["root", "anima", "task_runner", "cli", "mcp"]
_VALID_PROCESS_ROLES = frozenset({"root", "anima", "task_runner", "cli", "mcp"})


def set_process_role(role: ProcessRole) -> None:
    """Set this process's role and propagate it to subsequently spawned children."""
    if role not in _VALID_PROCESS_ROLES:
        raise ValueError(f"Unknown process role: {role!r}")
    set_process_role_env(role)


def get_process_role() -> ProcessRole:
    """Return the current role, defaulting to ``cli`` when unset or invalid."""
    role = get_process_role_env()
    if role not in _VALID_PROCESS_ROLES:
        return "cli"
    return cast(ProcessRole, role)
