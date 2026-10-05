# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Process role metadata shared by AnimaWorks process entry points."""

from __future__ import annotations

from core.platform.process_role import (
    PROCESS_ROLE_ENV,
    ProcessRole,
    get_process_role,
    get_process_role_env,
    set_process_role,
    set_process_role_env,
)

__all__ = [
    "PROCESS_ROLE_ENV",
    "ProcessRole",
    "get_process_role",
    "get_process_role_env",
    "set_process_role",
    "set_process_role_env",
]
