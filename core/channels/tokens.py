"""Per-Anima external-channel token resolution."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger("animaworks.tools")

_TOKEN_KEYS = {
    "slack": "SLACK_BOT_TOKEN",
    "discord": "DISCORD_BOT_TOKEN",
    "chatwork": "CHATWORK_API_TOKEN",
}


def resolve_per_anima_token(
    service: str,
    anima_dir_or_name: str | Path | None,
    *,
    credential_lookup: Callable[[str], str | None] | None = None,
    log: bool = False,
) -> str | None:
    """Resolve a per-Anima channel token, or return ``None`` for shared fallback.

    ``credential_lookup`` lets legacy callers preserve their precise credential
    cascade while sharing the service key/path normalization and logging logic.
    Without it, Slack and Chatwork use vault → shared credentials → environment,
    while Discord intentionally uses vault → shared credentials only.
    """
    if not anima_dir_or_name:
        return None

    try:
        token_prefix = _TOKEN_KEYS[service]
    except KeyError:
        raise ValueError(f"Unsupported channel token service: {service}") from None

    anima_name = Path(anima_dir_or_name).name
    if not anima_name:
        return None
    per_anima_key = f"{token_prefix}__{anima_name}"

    token = (
        credential_lookup(per_anima_key) if credential_lookup is not None else _lookup_default(service, per_anima_key)
    )
    if not token:
        return None

    if log and service in {"slack", "discord"}:
        logger.debug("Using per-Anima %s token for '%s'", service.capitalize(), anima_name)
    return token


def _lookup_default(service: str, key: str) -> str | None:
    token = _lookup_vault_credential(key)
    if token:
        return token

    token = _lookup_shared_credentials(key)
    if token:
        return token

    # The legacy Discord copies did not consult .env or process env. Per-Anima
    # Slack/Chatwork keys use the env-style cascade, whose abconfig map currently
    # contains only shared (non-per-Anima) keys.
    if service in {"slack", "chatwork"}:
        return os.environ.get(key) or None
    return None


def _lookup_vault_credential(key: str) -> str | None:
    try:
        from core.config.vault import get_vault_manager

        return get_vault_manager().get("shared", key)
    except Exception:
        return None


def _lookup_shared_credentials(key: str) -> str | None:
    from core.paths import get_data_dir

    credentials_path = get_data_dir() / "shared" / "credentials.json"
    if not credentials_path.is_file():
        return None
    try:
        raw = credentials_path.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s", credentials_path, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("Failed to read %s: expected a JSON object", credentials_path)
        return None
    value = data.get(key)
    return value if isinstance(value, str) and value else None
