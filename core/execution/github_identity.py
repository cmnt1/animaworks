# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""GitHub identity resolution for executor environments.

Injects ``GH_TOKEN`` from ``gh auth token -u <account>`` when the anima is
mapped in ``config.github_identities``.  This decouples push identity from
the host-wide ``~/.config/gh/hosts.yml`` active account.

``github_identities`` keys use two namespaces:

- ``anima:<name>`` — per-anima override (e.g. ``{"anima:sumire": "animaworks-reviewer"}``)
- company slug — company-wide default (e.g. ``{"fs": "animaworks-dev-team"}``)

Resolution order: per-anima override, then company mapping.
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
    """Return ``{"GH_TOKEN": ...}`` when anima or company maps to a GitHub account.

    Lookup order:

    1. ``identities["anima:<anima_dir.name>"]`` (per-anima override)
    2. ``identities[<company>]`` (company default)

    Never logs token values.  On missing config / mapping / token failure,
    returns an empty dict so callers fall back to legacy hosts.yml behaviour.
    """
    try:
        from core.config.anima_registry import read_anima_company
        from core.config.models import load_config

        cfg = load_config()
        identities = getattr(cfg, "github_identities", None) or {}
        if not isinstance(identities, dict):
            return {}

        account = _resolve_account(anima_dir, identities, read_anima_company)
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


def _resolve_account(
    anima_dir: Path,
    identities: dict,
    read_anima_company,
) -> str | None:
    """Pick GitHub account from identities map (per-anima then company)."""
    # 1. per-anima override (key namespace: anima:<name>)
    anima_key = f"anima:{anima_dir.name}"
    account = _normalize_account(identities.get(anima_key))
    if account:
        return account

    # 2. company-wide mapping (legacy)
    company = read_anima_company(anima_dir)
    if not company:
        return None
    return _normalize_account(identities.get(company))


def _normalize_account(value: object) -> str | None:
    if not value or not isinstance(value, str):
        return None
    account = value.strip()
    return account or None


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
