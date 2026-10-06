# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Configuration resolution: status.json merge with anima_defaults."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.config.local_llm import is_local_llm_default, resolve_local_llm_role_model
from core.config.schemas import AnimaDefaults, AnimaModelConfig, AnimaWorksConfig, CredentialConfig

logger = logging.getLogger("animaworks.config")

STATUS_JSON_FIELD_MAP: dict[str, str] = {
    "model": "model",
    "background_model": "background_model",
    "background_credential": "background_credential",
    "context_threshold": "context_threshold",
    "context_absolute_ceiling": "context_absolute_ceiling",
    "task_compaction_tokens": "task_compaction_tokens",
    "task_compaction_max": "task_compaction_max",
    "max_session_age_hours": "max_session_age_hours",
    "conversation_history_threshold": "conversation_history_threshold",
    "credential": "credential",
    "execution_mode": "execution_mode",
    "supervisor": "supervisor",
    "speciality": "speciality",
    "max_tokens": "max_tokens",
    "fallback_model": "fallback_model",
    "fallback_models": "fallback_models",
    "thinking": "thinking",
    "thinking_effort": "thinking_effort",
    "background_thinking_effort": "background_thinking_effort",
    "voice_thinking_effort": "voice_thinking_effort",
    "mode_s_auth": "mode_s_auth",
    "default_workspace": "default_workspace",
    "consolidation_enabled": "consolidation_enabled",
    "heartbeat_enabled": "heartbeat_enabled",
    "token_budget_monthly": "token_budget_monthly",
    "extra_mcp_servers": "extra_mcp_servers",
}
STATUS_JSON_NULLABLE_FIELDS = frozenset({"supervisor", "speciality", "token_budget_monthly"})


def is_root_memory_owner(anima_dir: Path) -> bool:
    """Always return True for phase3-fixed; retained only until RAG legacy branches are removed in R07."""
    del anima_dir
    return True


def _load_status_json(anima_dir: Path) -> dict[str, Any]:
    """Load ModelConfig-relevant fields from anima's status.json.

    Returns a dict with field names matching AnimaDefaults fields.
    Missing or invalid files return an empty dict.
    """
    from core.platform.status_store import read_status

    data = read_status(anima_dir)

    # Map status.json fields to AnimaModelConfig field names
    result: dict[str, Any] = {}
    # Fields where None is a valid explicit value (e.g. supervisor=null
    # means "top-level / no supervisor").  Empty string is still "not set".
    for status_key, config_key in STATUS_JSON_FIELD_MAP.items():
        if status_key in data:
            value = data[status_key]
            if value is None and status_key in STATUS_JSON_NULLABLE_FIELDS or value not in (None, ""):
                result[config_key] = value
    return result


def _load_status_role(anima_dir: Path | None) -> str:
    """Read the role from status.json, defaulting to ``general``."""
    if anima_dir is None:
        return "general"
    from core.platform.status_store import read_status

    data = read_status(anima_dir)
    role = data.get("role")
    return role if isinstance(role, str) and role.strip() else "general"


def resolve_anima_config(
    config: AnimaWorksConfig,
    anima_name: str,
    anima_dir: Path | None = None,
) -> tuple[AnimaDefaults, CredentialConfig]:
    """Merge status.json with *anima_defaults* (3-layer merge).

    Resolution uses a 3-layer priority (strongest first):

      1. ``status.json`` in *anima_dir* (SSoT for all fields including org)
      2. ``config.json`` per-anima (``config.animas``) — fallback for
         ``supervisor``, ``speciality``, ``heartbeat_enabled``, and
         ``token_budget_monthly`` only
      3. ``config.json`` anima_defaults (global defaults)

    For ``supervisor``, ``speciality``, and ``token_budget_monthly``, explicit
    ``null`` in status.json is respected.

    When *anima_dir* is ``None``, layer 1 is skipped (no status.json).

    Returns:
        A ``(resolved_defaults, credential)`` tuple.

    Raises:
        KeyError: If the resolved credential name is not in
            ``config.credentials``.
    """
    anima_entry = config.animas.get(anima_name, AnimaModelConfig())
    defaults = config.anima_defaults

    status_values = _load_status_json(anima_dir) if anima_dir else {}
    role = _load_status_role(anima_dir)

    # Merge priority (strongest first):
    #   1. status.json (including explicit null for supervisor/speciality)
    #   2. config.animas (fallback for selected per-Anima fields only)
    #   3. anima_defaults (global defaults)
    resolved: dict[str, Any] = {}
    for field_name in AnimaDefaults.model_fields:
        if field_name in status_values:
            resolved[field_name] = status_values[field_name]
        elif field_name == "model" and is_local_llm_default(config):
            resolved[field_name] = resolve_local_llm_role_model(config.local_llm, role)
        elif field_name == "credential" and is_local_llm_default(config):
            resolved[field_name] = "ollama"
        elif field_name in ("supervisor", "speciality", "heartbeat_enabled", "token_budget_monthly"):
            # Fallback to config.animas for fields exposed as per-Anima config
            anima_value = getattr(anima_entry, field_name)
            if anima_value is not None:
                resolved[field_name] = anima_value
            else:
                resolved[field_name] = getattr(defaults, field_name)
        else:
            resolved[field_name] = getattr(defaults, field_name)

    resolved_defaults = AnimaDefaults.model_validate(resolved)

    credential_name = resolved_defaults.credential
    if credential_name not in config.credentials:
        raise KeyError(f"Credential '{credential_name}' (for anima '{anima_name}') not found in config.credentials")

    credential = config.credentials[credential_name]
    return resolved_defaults, credential


__all__ = [
    "_load_status_json",
    "resolve_anima_config",
    "is_root_memory_owner",
]
