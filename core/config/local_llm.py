# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Helpers for local Ollama-backed model defaults and role presets."""

from __future__ import annotations

from typing import Any

from core.config.schemas import (
    DEFAULT_LOCAL_LLM_BASE_URL,
    DEFAULT_LOCAL_LLM_PRESETS,
    LocalLLMConfig,
)


def normalize_ollama_base_url(base_url: str | None) -> str:
    normalized = (base_url or DEFAULT_LOCAL_LLM_BASE_URL).strip() or DEFAULT_LOCAL_LLM_BASE_URL
    normalized = normalized.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3].rstrip("/")
    return normalized


def normalize_ollama_model_name(model: str) -> str:
    normalized = model.strip()
    if not normalized:
        return ""
    if normalized.startswith("ollama/"):
        return normalized
    return f"ollama/{normalized}"


def resolve_local_llm_role_preset(local_llm: LocalLLMConfig, role: str | None) -> str:
    role_name = (role or "administration").strip() or "administration"
    return local_llm.role_presets.get(role_name, local_llm.role_presets.get("administration", "general"))


def resolve_local_llm_role_model(local_llm: LocalLLMConfig, role: str | None) -> str:
    preset_name = resolve_local_llm_role_preset(local_llm, role)
    model = local_llm.presets.get(preset_name) or DEFAULT_LOCAL_LLM_PRESETS[preset_name]
    return normalize_ollama_model_name(model)


def is_local_llm_default(config: Any) -> bool:
    return getattr(config.anima_defaults, "credential", None) == "ollama"


def apply_local_llm_role_to_status(status_data: dict[str, Any], config: Any, role: str | None) -> bool:
    """Apply the configured local LLM model/credential for *role* to status data."""
    if not is_local_llm_default(config):
        return False
    status_data["model"] = resolve_local_llm_role_model(config.local_llm, role)
    status_data["credential"] = "ollama"
    return True


__all__ = [
    "apply_local_llm_role_to_status",
    "is_local_llm_default",
    "normalize_ollama_base_url",
    "normalize_ollama_model_name",
    "resolve_local_llm_role_model",
    "resolve_local_llm_role_preset",
]
