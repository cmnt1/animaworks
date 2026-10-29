from __future__ import annotations

"""Configuration APIs, loaded lazily to keep package imports lightweight."""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "AnimaModelConfig": "core.config.schemas",
    "AnimaWorksConfig": "core.config.schemas",
    "BackgroundReviewConfig": "core.config.schemas",
    "CredentialConfig": "core.config.schemas",
    "HelperModelFallback": "core.config.schemas",
    "HelperModelRole": "core.config.schemas",
    "HelperModelsConfig": "core.config.schemas",
    "DEFAULT_MODEL_MODE_PATTERNS": "core.config.model_mode",
    "get_config_path": "core.config.io",
    "invalidate_cache": "core.config.io",
    "invalidate_vault_cache": "core.config.vault",
    "load_config": "core.config.io",
    "read_anima_supervisor": "core.config.anima_registry",
    "register_anima_in_config": "core.config.anima_registry",
    "resolve_anima_config": "core.config.resolver",
    "resolve_execution_mode": "core.config.model_mode",
    "ResolvedHelperModel": "core.config.helper_models",
    "resolve_helper_model": "core.config.helper_models",
    "validate_helper_model_credentials": "core.config.helper_models",
    "save_config": "core.config.io",
    "update_config": "core.config.io",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


__all__ = sorted(_EXPORTS)
