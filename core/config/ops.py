# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Application operations for reading and updating AnimaWorks configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config.models import (
    AnimaModelConfig,
    AnimaWorksConfig,
    CredentialConfig,
    load_config,
    update_config,
)
from core.paths import get_animas_dir
from core.platform.status_store import update_status

# Legacy per-Anima fields that are now owned by each anima's ``status.json``.
_MODEL_FIELDS = frozenset(
    {
        "model",
        "fallback_model",
        "max_tokens",
        "credential",
        "context_threshold",
        "context_absolute_ceiling",
        "task_compaction_tokens",
        "task_compaction_max",
        "max_session_age_hours",
        "conversation_history_threshold",
        "execution_mode",
        "thinking",
        "heartbeat_interval_minutes",
        "supervisor",
        "speciality",
    }
)


def _flatten_dict(data: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Recursively flatten a nested mapping to dot-notation key-value pairs."""
    items: list[tuple[str, Any]] = []
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            items.extend(_flatten_dict(value, full_key))
        else:
            items.append((full_key, value))
    return items


def _mask_secret(key: str, value: Any) -> str:
    """Mask API key values, showing only the first eight characters."""
    if key.endswith("api_key") and isinstance(value, str) and value:
        return value[:8] + "..."
    return str(value)


def _coerce_value(value: str) -> Any:
    """Coerce a CLI string to a common scalar configuration type."""
    lower = value.lower()
    if lower in ("null", "none"):
        return None
    if lower == "true":
        return True
    if lower == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _set_nested(data: dict[str, Any], keys: list[str], value: Any) -> None:
    """Set a value in a nested mapping, creating intermediate dictionaries."""
    for key in keys[:-1]:
        if key not in data or not isinstance(data[key], dict):
            data[key] = {}
        data = data[key]
    data[keys[-1]] = value


def get_config_value(key: str) -> Any:
    """Return a configuration leaf addressed by a dot-notation key.

    Raises:
        KeyError: If any part of *key* is absent.
    """
    current: Any = load_config().model_dump()
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(key)
    return current


def list_config_values(section: str | None = None) -> list[tuple[str, Any]]:
    """Return flattened configuration values, optionally filtered by section."""
    values = _flatten_dict(load_config().model_dump())
    if section:
        values = [(key, value) for key, value in values if key.startswith(section)]
    return values


def legacy_model_status_target(key: str) -> tuple[str, str] | None:
    """Return an Anima/status field addressed through the legacy config path."""
    parts = key.split(".")
    if len(parts) >= 3 and parts[0] == "animas" and parts[2] in _MODEL_FIELDS:
        return parts[1], parts[2]
    return None


def set_config_value(key: str, value: Any) -> None:
    """Validate and persist a configuration value.

    Legacy ``animas.<name>.<status-field>`` keys write per-Anima status;
    ``heartbeat_interval_minutes`` is a root-owned scheduler override. Other
    values are validated through :class:`AnimaWorksConfig` and updated
    transactionally in ``config.json``.
    """
    target = legacy_model_status_target(key)
    if target is not None:
        anima_name, status_field = target
        if status_field == "heartbeat_interval_minutes":
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 1440:
                raise ValueError("heartbeat_interval_minutes must be an integer from 1 to 1440")
        if status_field in {"supervisor", "speciality"} and value is not None and not isinstance(value, str):
            raise ValueError(f"{status_field} must be a string or null")
        anima_dir = get_animas_dir() / anima_name
        if status_field in {"supervisor", "speciality"} and anima_name not in load_config().animas:
            raise KeyError(f"Anima not found in config: {anima_name}")
        update_status(anima_dir, lambda status: status.__setitem__(status_field, value))
        if status_field in {"supervisor", "speciality"}:

            def update_org_config(config: AnimaWorksConfig) -> None:
                anima_config = config.animas.get(anima_name)
                if anima_config is None:
                    raise KeyError(f"Anima not found in config: {anima_name}")
                setattr(anima_config, status_field, value)

            update_config(update_org_config)
        return

    parts = key.split(".")

    def apply_update(config: AnimaWorksConfig) -> AnimaWorksConfig:
        data = config.model_dump()
        # Auto-create scaffolds for new Anima entries.
        if len(parts) >= 3 and parts[0] == "animas":
            anima_name = parts[1]
            if anima_name not in data.get("animas", {}):
                data.setdefault("animas", {})[anima_name] = AnimaModelConfig().model_dump()

        # Auto-create scaffolds for new credential entries.
        if len(parts) >= 3 and parts[0] == "credentials":
            credential_name = parts[1]
            if credential_name not in data.get("credentials", {}):
                data.setdefault("credentials", {})[credential_name] = CredentialConfig().model_dump()

        _set_nested(data, parts, value)
        return AnimaWorksConfig.model_validate(data)

    update_config(apply_update)


def save_config_wizard(
    credential_updates: dict[str, CredentialConfig],
    anima_names: list[str],
    status_updates: dict[str, dict[str, str]],
    animas_dir: Path,
) -> None:
    """Persist the non-interactive portion of the configuration wizard."""

    def apply_update(config: AnimaWorksConfig) -> None:
        config.credentials.update(credential_updates)
        for anima_name in anima_names:
            config.animas.setdefault(anima_name, AnimaModelConfig())

    update_config(apply_update)
    for anima_name, values in status_updates.items():
        update_status(animas_dir / anima_name, lambda status, values=values: status.update(values))


__all__ = [
    "get_config_value",
    "legacy_model_status_target",
    "list_config_values",
    "save_config_wizard",
    "set_config_value",
]
