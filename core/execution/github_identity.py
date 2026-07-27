# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Company-fixed GitHub identity resolution for executor environments.

Injects ``GH_TOKEN`` from ``gh auth token -u <account>`` when the anima's
company is mapped in ``config.github_identities``.  This decouples push
identity from the host-wide ``~/.config/gh/hosts.yml`` active account.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger("animaworks.execution.github_identity")

_CACHE_TTL_SECONDS = 15 * 60  # 15 minutes; follow gh token refresh
_cache_lock = threading.Lock()
# account -> (token, expires_at_monotonic)
_token_cache: dict[str, tuple[str, float]] = {}

__all__ = ["resolve_github_token_env"]


def resolve_github_token_env(anima_dir: Path) -> dict[str, str]:
    """Return ``{"GH_TOKEN": ...}`` when company maps to a GitHub account.

    Never logs token values.  On missing config / company / token failure,
    returns an empty dict so callers fall back to legacy hosts.yml behaviour.
    """
    try:
        from core.config.anima_registry import read_anima_company
        from core.config.models import load_config

        company = read_anima_company(anima_dir)
        if not company:
            return {}

        cfg = load_config()
        identities = getattr(cfg, "github_identities", None) or {}
        if not isinstance(identities, dict):
            return {}

        account = identities.get(company)
        if not account or not isinstance(account, str):
            return {}
        account = account.strip()
        if not account:
            return {}

        token = _get_token_for_account(account)
        if not token:
            return {}
        return {"GH_TOKEN": token}
    except Exception:
        logger.warning(
            "github_identity: failed to resolve GH_TOKEN for anima_dir=%s; falling back",
            anima_dir,
            exc_info=True,
        )
        return {}


def _get_token_for_account(account: str) -> str | None:
    """Fetch and cache a gh auth token for *account*. Never log the token."""
    now = time.monotonic()
    with _cache_lock:
        cached = _token_cache.get(account)
        if cached is not None:
            token, expires_at = cached
            if now < expires_at and token:
                return token

    token = _fetch_gh_token(account)
    if not token:
        return None

    with _cache_lock:
        _token_cache[account] = (token, time.monotonic() + _CACHE_TTL_SECONDS)
    return token


def _fetch_gh_token(account: str) -> str | None:
    """Run ``gh auth token -u <account>``. Returns None on failure."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token", "-u", account],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning(
            "github_identity: gh auth token failed for account=%s: %s",
            account,
            type(exc).__name__,
        )
        return None

    if result.returncode != 0:
        # Do not log stderr — may contain sensitive hints.
        logger.warning(
            "github_identity: gh auth token exited %s for account=%s",
            result.returncode,
            account,
        )
        return None

    token = (result.stdout or "").strip()
    if not token:
        logger.warning(
            "github_identity: empty token for account=%s",
            account,
        )
        return None
    return token


def _clear_token_cache() -> None:
    """Test helper: clear the in-process token cache."""
    with _cache_lock:
        _token_cache.clear()
