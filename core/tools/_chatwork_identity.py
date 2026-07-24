# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Chatwork identity and delegation resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from core.exceptions import ToolConfigError
from core.tools._base import resolve_env_style_credential


@dataclass(frozen=True)
class ChatworkIdentity:
    """Resolved Chatwork identity."""

    name: str
    token: str


def _resolve_anima_name(anima_dir: str | Path | None = None) -> str:
    resolved_dir = anima_dir or os.environ.get("ANIMAWORKS_ANIMA_DIR")
    if not resolved_dir:
        return "owner"
    return Path(resolved_dir).name


def _get_grant(anima_name: str, identity_name: str) -> str | None:
    from core.config.models import load_config

    config = load_config()
    return config.chatwork_tool.grants.get(anima_name, {}).get(identity_name)


def resolve_identity(
    as_identity: str | None = None,
    anima_dir: str | Path | None = None,
) -> ChatworkIdentity:
    """Resolve the primary or explicitly delegated Chatwork identity."""
    anima_name = _resolve_anima_name(anima_dir)
    identity_name = as_identity or anima_name

    if as_identity is not None and _get_grant(anima_name, as_identity) is None:
        raise ToolConfigError(f"Chatwork identity '{as_identity}' has not been delegated to anima '{anima_name}'.")

    token_key = f"CHATWORK_API_TOKEN__{identity_name}"
    token = resolve_env_style_credential(token_key)
    if not token:
        raise ToolConfigError(
            f"This anima has no assigned Chatwork account. Register {token_key} "
            "in the vault or configure delegation in chatwork_tool.grants."
        )
    return ChatworkIdentity(name=identity_name, token=token)


def check_write_allowed(
    as_identity: str | None,
    anima_dir: str | Path | None = None,
) -> None:
    """Reject writes through read-only delegated identities."""
    if as_identity is None:
        return

    anima_name = _resolve_anima_name(anima_dir)
    grant = _get_grant(anima_name, as_identity)
    if grant != "readwrite":
        if grant is None:
            raise ToolConfigError(f"Chatwork identity '{as_identity}' has not been delegated to anima '{anima_name}'.")
        raise ToolConfigError(f"Delegation to identity {as_identity} is read-only; write operations are not allowed.")
