"""Locate the Jev (TypeSafe System One) API key and its local spend ledger.

Jev's public API is a single ``POST /v1/systemone``; there is no balance,
billing or account endpoint, and the response carries no credit headers.  The
dashboard therefore reconciles a user-entered baseline balance against a
ledger that every Jev caller appends to.  This module only answers *where*
the key and that ledger live — the accounting itself is in
``core.jev_credits``.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

JEV_SECRETS_PATH_ENV = "ANIMAWORKS_JEV_SECRETS_PATH"
JEV_LEDGER_DIR_ENV = "JEV_USAGE_LEDGER_DIR"
_DEFAULT_ABCONFIG_DIR = Path("E:/OneDriveBiz/Tools/abconfig")
_LEDGER_DIR_NAME = "jev_usage"


def abconfig_dir() -> Path:
    """Return the directory holding the shared credentials and ledger."""
    bridge = os.environ.get("ANIMAWORKS_ABCONFIG_PATH")
    return Path(bridge).parent if bridge else _DEFAULT_ABCONFIG_DIR


def _secrets_path() -> Path:
    explicit = os.environ.get(JEV_SECRETS_PATH_ENV)
    return Path(explicit) if explicit else abconfig_dir() / "secrets_local.py"


def jev_api_key(configured: str | None = None) -> str:
    """Return the Jev API key, or ``""`` when none is configured.

    Reads the ``jev_key`` literal out of ``secrets_local.py`` without importing
    it, so a rotated key takes effect on the next call and the unrelated
    secrets in that file are never executed.  Unlike the nanoGPT reader this
    never raises: the key is only used to tell "Jev is set up" from "Jev is
    not", and a broken secrets file must not take the dashboard down.
    """
    env = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if env:
        return env
    try:
        source = _secrets_path().read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return (configured or "").strip()

    value: object = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not any(isinstance(target, ast.Name) and target.id == "jev_key" for target in targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            value = None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return (configured or "").strip()


def jev_ledger_dir(configured: str | None = None) -> Path:
    """Return the spend-ledger directory (env override > config > abconfig).

    Writers outside this repository resolve the same directory from
    ``JEV_USAGE_LEDGER_DIR`` or the abconfig default, so the two sides agree
    without sharing code.
    """
    env = os.environ.get(JEV_LEDGER_DIR_ENV, "").strip()
    if env:
        return Path(env)
    if configured and configured.strip():
        return Path(configured.strip())
    return abconfig_dir() / _LEDGER_DIR_NAME
