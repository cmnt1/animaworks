from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import importlib
import logging
from pathlib import Path

from core.platform.env import get_env

logger = logging.getLogger(__name__)

_HEADER = "X-AnimaWorks-Internal-Auth"


def _operator_token_file() -> Path:
    from core.paths import get_data_dir

    return get_data_dir() / "run" / "internal_api.auth"


class _HostAPIProxy:
    """Lazy access to the centralized host client without widening core layers."""

    def __getattr__(self, name: str):
        client = importlib.import_module("core.host_api").host_api
        return getattr(client, name)


host_api = _HostAPIProxy()


def internal_api_headers() -> dict[str, str]:
    """Return the internal API auth header for outbound httpx calls.

    Precedence: the `ANIMAWORKS_INTERNAL_AUTH` env var (set on anima and
    tool subprocesses by the server) first, then the operator token file
    (for human-driven CLI runs).  If neither is available we return an
    empty dict, keeping compatibility with servers running in off/log mode.
    """
    token = get_env("ANIMAWORKS_INTERNAL_AUTH")
    if token:
        return {_HEADER: token}
    try:
        operator_token = _operator_token_file().read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return {}
    if operator_token:
        return {_HEADER: operator_token}
    return {}
