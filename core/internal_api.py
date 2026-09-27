from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_HEADER = "X-AnimaWorks-Internal-Auth"


def _operator_token_file() -> Path:
    from core.paths import get_data_dir

    return get_data_dir() / "run" / "internal_api.auth"


def internal_api_headers() -> dict[str, str]:
    """Return the internal API auth header for outbound httpx calls.

    Precedence: the `ANIMAWORKS_INTERNAL_AUTH` env var (set on anima and
    tool subprocesses by the server) first, then the operator token file
    (for human-driven CLI runs).  If neither is available we return an
    empty dict, keeping compatibility with servers running in off/log mode.
    """
    token = os.environ.get("ANIMAWORKS_INTERNAL_AUTH")
    if token:
        return {_HEADER: token}
    try:
        operator_token = _operator_token_file().read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return {}
    if operator_token:
        return {_HEADER: operator_token}
    return {}
