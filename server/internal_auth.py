from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import hmac
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request

from core.anima.factory import validate_anima_name
from core.config.io import load_config
from core.i18n import t

logger = logging.getLogger("animaworks.server.internal_auth")

_ANIMA = b"anima:"
_OPERATOR = b"operator"


@dataclass(frozen=True)
class InternalCaller:
    """Verified identity of an `/api/internal/*` caller."""

    kind: Literal["anima", "operator"]
    name: str


class InternalAuth:
    """Holds the server's internal secret and derives per-caller tokens.

    The secret lives only in process memory (never written to disk) and is
    regenerated on every server start.  Tokens are `name.hmac(secret, name)`
    so an anima can never forge another caller's token.
    """

    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    @classmethod
    def generate(cls) -> InternalAuth:
        return cls(secrets.token_bytes(32))

    def _token(self, kind: bytes, name: bytes) -> str:
        digest = hmac.new(self._secret, kind + name, "sha256").hexdigest()
        return f"{name.decode('utf-8')}.{digest}"

    def token_for_anima(self, name: str) -> str:
        return self._token(_ANIMA, name.encode("utf-8"))

    def operator_token(self) -> str:
        return "operator." + hmac.new(self._secret, _OPERATOR, "sha256").hexdigest()

    def verify(self, header_value: str | None) -> InternalCaller | None:
        if not header_value:
            return None
        token = header_value.strip()
        if "." not in token:
            return None
        name, _, digest = token.partition(".")
        if not name:
            return None
        if name == "operator":
            expected = hmac.new(self._secret, _OPERATOR, "sha256").hexdigest()
            if hmac.compare_digest(digest, expected):
                return InternalCaller(kind="operator", name="operator")
            # Fall through: an anima may legitimately be named "operator".
        # Anima name must be valid, otherwise it cannot name a real anima.
        if validate_anima_name(name) is not None:
            return None
        expected = self._token(_ANIMA, name.encode("utf-8"))
        if hmac.compare_digest(token, expected):
            return InternalCaller(kind="anima", name=name)
        return None


def write_operator_token(path: Path) -> None:
    """Persist the operator token for human-driven CLI clients (only the owner can read)."""
    auth = _current_auth
    if auth is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, auth.operator_token().encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def remove_operator_token(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


# Module-level slot used by write_operator_token/remove_operator_token.  It is
# set by the server lifespan so CLI helper paths don't need to import app state.
_current_auth: InternalAuth | None = None


def set_current_auth(auth: InternalAuth | None) -> None:
    global _current_auth
    _current_auth = auth


def require_internal_caller(request: Request) -> InternalCaller | None:
    """FastAPI dependency that verifies the internal auth header.

    Returns the verified caller (or None when the mode is off / log and the
    check failed).  In enforce mode a missing/invalid header yields 401.
    """
    auth: InternalAuth | None = getattr(request.app.state, "internal_auth", None)
    mode: str = "enforce"
    try:
        mode = load_config().server.internal_api_auth
    except Exception:
        logger.warning("internal_api_auth_mode_unreadable", exc_info=True)
    if mode == "off":
        return None

    header = request.headers.get("X-AnimaWorks-Internal-Auth")
    caller = auth.verify(header) if auth is not None else None
    if caller is not None:
        request.state.internal_caller = caller
        return caller

    if mode == "log":
        logger.warning(
            "internal_api_auth_missing path=%s client=%s",
            request.url.path,
            request.client.host if request.client else "?",
        )
        return None
    raise HTTPException(status_code=401, detail=t("server.internal_auth_required"))
