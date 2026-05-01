from __future__ import annotations

"""Shared constants and helpers for the OpenCode Go provider."""

import os
from typing import Any

OPENCODE_GO_PROVIDER = "opencode-go"
OPENCODE_GO_API_BASE_URL = "https://opencode.ai/zen/go/v1"
OPENCODE_GO_MODELS_URL = f"{OPENCODE_GO_API_BASE_URL}/models"
OPENCODE_GO_API_KEY_ENV = "OPENCODE_API_KEY"

OPENCODE_GO_FALLBACK_MODELS: tuple[str, ...] = (
    "opencode-go/glm-5.1",
    "opencode-go/glm-5",
    "opencode-go/kimi-k2.6",
    "opencode-go/kimi-k2.5",
    "opencode-go/deepseek-v4-pro",
    "opencode-go/deepseek-v4-flash",
    "opencode-go/qwen3.6-plus",
    "opencode-go/qwen3.5-plus",
    "opencode-go/mimo-v2-pro",
    "opencode-go/mimo-v2-omni",
    "opencode-go/mimo-v2.5-pro",
    "opencode-go/mimo-v2.5",
    "opencode-go/minimax-m2.7",
    "opencode-go/minimax-m2.5",
)


def is_opencode_go_model(model: str) -> bool:
    return model.startswith(f"{OPENCODE_GO_PROVIDER}/")


def opencode_go_litellm_model(model: str) -> str:
    """Return the LiteLLM OpenAI-compatible model id for OpenCode Go."""
    if is_opencode_go_model(model):
        model_id = model.split("/", 1)[1]
        if model_id.startswith("minimax-m2."):
            return f"anthropic/{model_id}"
        return f"openai/{model_id}"
    return model


def opencode_go_model_id(raw_id: str) -> str:
    model = str(raw_id).strip()
    if not model:
        return ""
    if model.startswith(f"{OPENCODE_GO_PROVIDER}/"):
        return model
    return f"{OPENCODE_GO_PROVIDER}/{model}"


def opencode_go_api_key(configured: str | None = None) -> str:
    """Resolve OpenCode Go API key from config, abconfig, then env."""
    if configured:
        return configured
    try:
        from core.tools._base import resolve_env_style_credential

        value = resolve_env_style_credential(OPENCODE_GO_API_KEY_ENV)
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(OPENCODE_GO_API_KEY_ENV, "")


def with_opencode_go_defaults(credential: Any) -> dict[str, str | None]:
    """Return api key and base URL for an OpenCode Go credential-like object."""
    configured_key = getattr(credential, "api_key", "") if credential is not None else ""
    configured_base = getattr(credential, "base_url", None) if credential is not None else None
    return {
        "api_key": opencode_go_api_key(configured_key),
        "base_url": configured_base or OPENCODE_GO_API_BASE_URL,
    }
