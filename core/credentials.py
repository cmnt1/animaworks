from __future__ import annotations

from core.platform.env import get_env

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Shared credential lookup and resolution helpers."""

import importlib.util
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.exceptions import ToolConfigError

logger = logging.getLogger("animaworks.credentials")

# Optional local abconfig bridge. Set ANIMAWORKS_ABCONFIG_PATH to the
# absolute path of Cnct_Env.py; secrets_local.py is loaded from the same dir.
# When unset, the abconfig credential stage is skipped entirely.
_DEFAULT_ABCONFIG_PATH = Path(r"E:\OneDriveBiz\Tools\abconfig\Cnct_Env.py")
_ABCONFIG_ENV_VAR = "ANIMAWORKS_ABCONFIG_PATH"
_ABCONFIG_KEY_MAP = {
    "SLACK_BOT_TOKEN": "slack_bot_token",
    "SLACK_APP_TOKEN": "slack_app_token",
    "DISCORD_BOT_TOKEN": "DISCORD_BOT_TOKEN",
    "OPENCODE_API_KEY": "opencode_api",
    "OPENCODE_GO_WORKSPACE_ID": "opencode_go_workspace_id",
    "OPENCODE_GO_AUTH_COOKIE": "opencode_go_auth_cookie",
    "BSKY_IDENTIFIER": "BSKY_IDENTIFIER",
    "BSKY_APP_PASSWORD": "BSKY_APP_PASSWORD",
}


def get_env_or_fail(key: str, tool_name: str) -> str:
    """Get an environment variable, raising a clear error if missing."""
    val = os.environ.get(key)
    if not val:
        raise ToolConfigError(
            f"Tool '{tool_name}' requires environment variable {key}. Set it in .env or the shell environment."
        )
    return val


def get_credential(
    credential_name: str,
    tool_name: str,
    key_name: str = "api_key",
    env_var: str | None = None,
) -> str:
    """Resolve a credential via config → vault → legacy file → local/env cascade.

    Args:
        credential_name: Key in config.json ``credentials`` dict
            (e.g. ``"chatwork"``).
        tool_name: Human-readable tool name for error messages.
        key_name: Which key to retrieve. ``"api_key"`` reads the primary
            ``api_key`` field; anything else reads from ``keys[key_name]``.
        env_var: Fallback environment variable name.

    Returns:
        The resolved credential string.

    Raises:
        ToolConfigError: If no configured source provides a value.
    """
    from core.config.models import load_config

    # 1. config.json
    config = load_config()
    cred = config.credentials.get(credential_name)
    if key_name == "api_key" and (credential_name == "nanogpt" or env_var == "NANOGPT_API_KEY"):
        from core.config.nanogpt import nanogpt_api_key

        current_key = nanogpt_api_key(cred.api_key if cred else None)
        if current_key:
            return current_key
    if cred:
        if key_name == "api_key" and cred.api_key:
            _log_resolved(credential_name, key_name, "config.json", cred.api_key)
            return cred.api_key
        if key_name != "api_key" and key_name in cred.keys and cred.keys[key_name]:
            val = cred.keys[key_name]
            _log_resolved(credential_name, key_name, "config.json", val)
            return val

    # 2. vault.json (encrypted credential store)
    if env_var:
        val = _lookup_vault_credential(env_var)
        if val:
            _log_resolved(credential_name, key_name, "vault.json", val)
            return val

    # 3. shared/credentials.json (legacy, pre-migration)
    if env_var:
        val = _lookup_shared_credentials(env_var)
        if val:
            _log_resolved(credential_name, key_name, "shared/credentials.json", val)
            return val

    # 4. Local abconfig bridge (secrets_local.py via ANIMAWORKS_ABCONFIG_PATH)
    if env_var:
        val = _lookup_abconfig_credential(env_var)
        if val:
            abconfig_path = get_env(_ABCONFIG_ENV_VAR, str(_DEFAULT_ABCONFIG_PATH))
            _log_resolved(credential_name, key_name, abconfig_path, val)
            return val

    # 5. Environment variable fallback
    if env_var:
        val = os.environ.get(env_var)
        if val:
            _log_resolved(credential_name, key_name, f"env:{env_var}", val)
            return val

    # 6. Error with guidance
    sources = [f"config.json credentials.{credential_name}.{key_name}"]
    if env_var:
        sources.append("vault.json")
        abconfig_path = get_env(_ABCONFIG_ENV_VAR, str(_DEFAULT_ABCONFIG_PATH))
        if abconfig_path and env_var in _ABCONFIG_KEY_MAP:
            sources.append(abconfig_path)
        sources.append(f"environment variable {env_var}")
    raise ToolConfigError(
        f"Tool '{tool_name}' requires credential '{credential_name}'. Set it in: {' or '.join(sources)}"
    )


def check_missing_slack_tokens() -> list[str]:
    """Return registered Animas without a token in vault, shared storage, or env."""
    try:
        from core.config.models import load_config

        config = load_config()
    except Exception:
        return []

    missing: list[str] = []
    for anima_name in sorted(config.animas):
        key = f"SLACK_BOT_TOKEN__{anima_name}"
        token = _lookup_vault_credential(key) or _lookup_shared_credentials(key) or os.environ.get(key)
        if not token:
            missing.append(anima_name)
    return missing


def _lookup_vault_credential(key: str) -> str | None:
    """Look up a key in the vault's ``shared`` section."""
    try:
        from core.config.vault import get_vault_manager

        vm = get_vault_manager()
        return vm.get("shared", key)
    except Exception:
        return None


def _lookup_shared_credentials(key: str) -> str | None:
    """Look up a key in the shared credentials file.

    Reads ``{data_dir}/shared/credentials.json`` (a flat key-value JSON)
    and returns the value for *key*, or ``None`` if not found.
    """
    from core.paths import get_data_dir

    cred_file = get_data_dir() / "shared" / "credentials.json"
    if not cred_file.is_file():
        return None
    try:
        raw = cred_file.read_text(encoding="utf-8")
        if not raw.strip():
            return None
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s", cred_file, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("Failed to read %s: expected a JSON object", cred_file)
        return None
    val = data.get(key)
    return val if val else None


def _lookup_abconfig_credential(key: str) -> str | None:
    """Look up credential keys from the local abconfig secrets file.

    ``Cnct_Env.py`` imports heavy desktop/database dependencies, so we avoid
    importing it directly at server startup. Instead we treat its sibling
    ``secrets_local.py`` as the source of truth for the tokens exposed there.
    """
    attr_name = _ABCONFIG_KEY_MAP.get(key)
    if not attr_name:
        return None

    secrets = _load_abconfig_secrets()
    if secrets is None:
        return None

    val = getattr(secrets, attr_name, None)
    return val if isinstance(val, str) and val else None


def resolve_env_style_credential(key: str) -> str | None:
    """Resolve a raw env-style credential key via the standard cascade.

    This is intended for ad-hoc env-style keys such as per-Anima Slack
    tokens (for example ``SLACK_BOT_TOKEN__kanna``) that do not map to a
    ``config.json credentials.<name>`` entry.
    """
    val = _lookup_vault_credential(key)
    if val:
        return val

    val = _lookup_shared_credentials(key)
    if val:
        return val

    val = _lookup_abconfig_credential(key)
    if val:
        return val

    val = os.environ.get(key)
    return val if val else None


def _load_abconfig_secrets() -> Any | None:
    """Load the secrets module selected by the current abconfig path env var."""
    raw = get_env(_ABCONFIG_ENV_VAR, str(_DEFAULT_ABCONFIG_PATH))
    return _load_abconfig_secrets_from_path(raw) if raw else None


@lru_cache(maxsize=4)
def _load_abconfig_secrets_from_path(raw: str) -> Any | None:
    """Load ``secrets_local.py`` next to the supplied ``Cnct_Env.py`` path."""
    cnct_env_path = Path(raw)
    if not cnct_env_path.is_file():
        logger.debug("abconfig path not found: %s", cnct_env_path)
        return None

    secrets_path = cnct_env_path.with_name("secrets_local.py")
    if not secrets_path.is_file():
        logger.debug("abconfig secrets file not found: %s", secrets_path)
        return None

    try:
        spec = importlib.util.spec_from_file_location("animaworks_abconfig_secrets", secrets_path)
        if spec is None or spec.loader is None:
            logger.warning("Failed to create import spec for %s", secrets_path)
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        logger.warning("Failed to load tokens from %s", secrets_path, exc_info=True)
        return None


def _log_resolved(
    credential_name: str,
    key_name: str,
    source: str,
    value: str,
) -> None:
    """Log credential resolution with masked value."""
    masked = value[:4] + "****" if len(value) > 4 else "****"
    logger.debug(
        "Credential '%s.%s' resolved from %s: %s",
        credential_name,
        key_name,
        source,
        masked,
    )


__all__ = [
    "check_missing_slack_tokens",
    "get_credential",
    "get_env_or_fail",
    "resolve_env_style_credential",
]
