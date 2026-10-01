# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Low-level environment access for process-role metadata."""

from __future__ import annotations

import os

PROCESS_ROLE_ENV = "ANIMAWORKS_PROCESS_ROLE"


def get_process_role_env() -> str | None:
    """Read the inherited process-role environment value, if present."""
    return os.environ.get(PROCESS_ROLE_ENV)


def set_process_role_env(role: str) -> None:
    """Set the process-role environment value inherited by future children."""
    os.environ[PROCESS_ROLE_ENV] = role
