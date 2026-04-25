from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime
import importlib.util
import json
import logging
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config.local_llm import (
    apply_local_llm_presets_to_animas,
    normalize_ollama_base_url,
    normalize_ollama_model_name,
)
from core.config.models import (
    DEFAULT_LOCAL_LLM_BASE_URL,
    DEFAULT_LOCAL_LLM_PRESETS,
    DEFAULT_LOCAL_LLM_ROLE_PRESETS,
    KNOWN_MODELS,
    CredentialConfig,
    LocalLLMConfig,
    load_config,
    save_config,
)
from core.i18n import t
from core.paths import get_animas_dir, get_data_dir
from core.platform.claude_code import is_claude_code_available
from core.platform.codex import is_codex_cli_available, is_codex_login_available

logger = logging.getLogger("animaworks.routes.config")

ABCONFIG_ENV_FILE = Path(r"E:\OneDriveBiz\Tools\abconfig\Cnct_Env.py")
ABCONFIG_KEYS = {"openai_id", "openai_key", "claude_token", "claude_api", "nanogpt_api", "gemini_api"}
MODEL_CATALOG_CACHE_FILE = "model_catalog_cache.json"
MODEL_CATALOG_PROVIDERS = ("claude_code", "codex", "nanogpt", "google")


def _known_codex_models() -> list[str]:
    """Return UI-visible Codex model ids from the shared known-model catalog."""
    models = [
        str(item["name"])
        for item in KNOWN_MODELS
        if item.get("mode") == "C" and str(item.get("name", "")).startswith("codex/")
    ]
    return _unique_model_ids(["codex/gpt-5.5", *models])


def _known_claude_code_models() -> list[str]:
    """Return UI-visible Claude Code model ids from the shared known-model catalog."""
    return [
        str(item["name"])
        for item in KNOWN_MODELS
        if item.get("mode") == "S" and str(item.get("name", "")).startswith("claude-")
    ]


def _known_google_models() -> list[str]:
    return [
        "google/gemini-2.5-pro",
        "google/gemini-2.5-flash",
        "google/gemini-2.0-flash",
        "google/gemini-2.0-flash-lite",
    ]


def _load_abconfig_credentials() -> dict[str, str]:
    if not ABCONFIG_ENV_FILE.is_file():
        return {}
    try:
        spec = importlib.util.spec_from_file_location("_animaworks_abconfig_cnct_env", ABCONFIG_ENV_FILE)
        if spec is None or spec.loader is None:
            return {}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:
        logger.warning("Failed to load abconfig environment file: %s", ABCONFIG_ENV_FILE, exc_info=True)
        return {}
    return {key: value for key in ABCONFIG_KEYS if isinstance((value := getattr(module, key, "")), str) and value}


def _abconfig_value(key: str) -> str:
    return _load_abconfig_credentials().get(key, "")


def _first_secret(*values: str | None) -> str:
    for value in values:
        if value:
            return value
    return ""


def _unique_model_ids(models: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for model in models:
        model_id = str(model).strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        result.append(model_id)
    return result


def _model_catalog_cache_path() -> Path:
    return get_data_dir() / MODEL_CATALOG_CACHE_FILE


def _load_model_catalog_cache() -> dict[str, object]:
    path = _model_catalog_cache_path()
    if not path.is_file():
        return {"version": 1, "providers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Failed to read model catalog cache from %s", path, exc_info=True)
        return {"version": 1, "providers": {}}
    if not isinstance(data, dict):
        return {"version": 1, "providers": {}}
    if not isinstance(data.get("providers"), dict):
        data["providers"] = {}
    return data


def _save_model_catalog_cache(data: dict[str, object]) -> None:
    path = _model_catalog_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cached_provider_models(provider: str) -> list[str]:
    cache = _load_model_catalog_cache()
    providers = cache.get("providers")
    if not isinstance(providers, dict):
        return []
    entry = providers.get(provider)
    if not isinstance(entry, dict):
        return []
    models = entry.get("models")
    if not isinstance(models, list):
        return []
    return _unique_model_ids([str(model) for model in models])


def _cache_provider_models(provider: str, models: list[str], *, status: str, message: str = "") -> None:
    cache = _load_model_catalog_cache()
    providers = cache.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        cache["providers"] = providers
    providers[provider] = {
        "models": _unique_model_ids(models),
        "status": status,
        "message": message,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _save_model_catalog_cache(cache)


def _models_for_provider(provider: str, fallback: list[str]) -> list[str]:
    return _unique_model_ids([*fallback, *_cached_provider_models(provider)])


class UpdateAnthropicAuthRequest(BaseModel):
    auth_mode: str = "api_key"
    api_key: str = ""


class UpdateOpenAIAuthRequest(BaseModel):
    auth_mode: str = "api_key"
    api_key: str = ""


class UpdateLocalLLMRequest(BaseModel):
    base_url: str = DEFAULT_LOCAL_LLM_BASE_URL
    default_model: str = DEFAULT_LOCAL_LLM_PRESETS["coding"]
    presets: dict[str, str] = {}
    role_presets: dict[str, str] = {}


class RefreshAvailableModelsRequest(BaseModel):
    providers: list[str] | None = None


def _mask_secrets(obj: object) -> object:
    """Recursively mask sensitive values in a config dict."""
    if isinstance(obj, dict):
        return {k: _mask_value(k, v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask_secrets(item) for item in obj]
    return obj


def _mask_value(key: str, value: object) -> object:
    """Mask a value if its key suggests it contains a secret."""
    if isinstance(value, str) and any(kw in key.lower() for kw in ("key", "token", "secret", "password")):
        if len(value) > 8:
            return value[:3] + "..." + value[-4:]
        return "***"
    if isinstance(value, (dict, list)):
        return _mask_secrets(value)
    return value


def _serialize_openai_auth() -> dict[str, object]:
    """Return current OpenAI auth config and runtime availability."""
    config = load_config()
    credential = config.credentials.get("openai", CredentialConfig())
    auth_mode = credential.type or "api_key"
    config_present = "openai" in config.credentials
    config_api_key_configured = bool(credential.api_key)
    env_api_key_configured = bool(os.environ.get("OPENAI_API_KEY"))
    codex_cli_available = is_codex_cli_available()
    codex_login_available = is_codex_login_available()

    configured = False
    if auth_mode == "codex_login":
        configured = codex_login_available
    elif auth_mode == "api_key":
        configured = config_api_key_configured or env_api_key_configured

    return {
        "auth_mode": auth_mode,
        "config_present": config_present,
        "config_api_key_configured": config_api_key_configured,
        "env_api_key_configured": env_api_key_configured,
        "codex_cli_available": codex_cli_available,
        "codex_login_available": codex_login_available,
        "configured": configured,
    }


def _serialize_anthropic_auth() -> dict[str, object]:
    """Return current Anthropic auth config and runtime availability."""
    config = load_config()
    credential = config.credentials.get("anthropic", CredentialConfig())
    auth_mode = credential.type or "api_key"
    config_present = "anthropic" in config.credentials
    config_api_key_configured = bool(credential.api_key)
    env_api_key_configured = bool(os.environ.get("ANTHROPIC_API_KEY"))
    claude_code_available = is_claude_code_available()

    configured = False
    if auth_mode == "claude_code_login":
        configured = claude_code_available
    elif auth_mode == "api_key":
        configured = config_api_key_configured or env_api_key_configured

    return {
        "auth_mode": auth_mode,
        "config_present": config_present,
        "config_api_key_configured": config_api_key_configured,
        "env_api_key_configured": env_api_key_configured,
        "claude_code_available": claude_code_available,
        "configured": configured,
    }


def _list_nanogpt_models(base_url: str, api_key: str) -> list[str]:
    """Fetch available model IDs from a nanoGPT-compatible /models endpoint."""
    response = httpx.get(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=httpx.Timeout(10.0, connect=5.0),
    )
    response.raise_for_status()
    data = response.json()
    return sorted({str(item.get("id", "")).strip() for item in data.get("data", []) if item.get("id")})


def _list_ollama_models(base_url: str) -> list[str]:
    response = httpx.get(
        f"{base_url}/api/tags",
        timeout=httpx.Timeout(10.0, connect=5.0),
    )
    response.raise_for_status()
    data = response.json()
    models = sorted(
        {
            normalize_ollama_model_name(str(item.get("name", "")).strip())
            for item in data.get("models", [])
            if item.get("name")
        }
    )
    return [model for model in models if model]


def _list_openai_models(api_key: str, organization: str = "") -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    if organization.startswith("org-"):
        headers["OpenAI-Organization"] = organization
    response = httpx.get(
        "https://api.openai.com/v1/models",
        headers=headers,
        timeout=httpx.Timeout(10.0, connect=5.0),
    )
    response.raise_for_status()
    data = response.json()
    ids = [
        str(item.get("id", "")).strip()
        for item in data.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]
    return _unique_model_ids([f"codex/{model_id}" for model_id in sorted(ids) if model_id.startswith(("gpt-", "o"))])


def _list_anthropic_models(api_key: str = "", auth_token: str = "") -> list[str]:
    headers = {"anthropic-version": "2023-06-01"}
    if api_key:
        headers["x-api-key"] = api_key
    elif auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    response = httpx.get(
        "https://api.anthropic.com/v1/models",
        headers=headers,
        timeout=httpx.Timeout(10.0, connect=5.0),
    )
    response.raise_for_status()
    data = response.json()
    return sorted(
        {
            str(item.get("id", "")).strip()
            for item in data.get("data", [])
            if isinstance(item, dict) and item.get("id")
        }
    )


def _list_google_models(api_key: str) -> list[str]:
    response = httpx.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": api_key},
        timeout=httpx.Timeout(10.0, connect=5.0),
    )
    response.raise_for_status()
    data = response.json()
    models: list[str] = []
    for item in data.get("models", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().removeprefix("models/")
        if name and name.startswith("gemini-"):
            models.append(f"google/{name}")
    return _unique_model_ids(sorted(models))


def _refresh_claude_code_models(config) -> dict[str, object]:
    credential = config.credentials.get("anthropic", CredentialConfig())
    fallback = _known_claude_code_models()
    api_key = _first_secret(credential.api_key, os.environ.get("ANTHROPIC_API_KEY"), _abconfig_value("claude_api"))
    auth_token = _first_secret(_abconfig_value("claude_token"))
    if not api_key and not auth_token:
        _cache_provider_models("claude_code", fallback, status="fallback", message="No Anthropic API key configured.")
        return {"provider": "claude_code", "status": "fallback", "source": "known", "dynamic": False, "count": len(fallback)}
    try:
        models = _list_anthropic_models(api_key=api_key, auth_token=auth_token)
    except Exception as exc:
        cached = _cached_provider_models("claude_code")
        if cached:
            return {
                "provider": "claude_code",
                "status": "cached",
                "source": "cache",
                "dynamic": False,
                "count": len(cached),
                "message": str(exc),
            }
        _cache_provider_models("claude_code", fallback, status="fallback", message=str(exc))
        return {
            "provider": "claude_code",
            "status": "fallback",
            "source": "known",
            "dynamic": False,
            "count": len(fallback),
            "message": str(exc),
        }
    _cache_provider_models("claude_code", models, status="ok")
    return {"provider": "claude_code", "status": "ok", "source": "api", "dynamic": True, "count": len(models)}


def _refresh_codex_models(config) -> dict[str, object]:
    credential = config.credentials.get("openai", CredentialConfig())
    fallback = _known_codex_models()
    api_key = _first_secret(credential.api_key, os.environ.get("OPENAI_API_KEY"), _abconfig_value("openai_key"))
    if not api_key:
        _cache_provider_models("codex", fallback, status="fallback", message="No OpenAI API key configured.")
        return {"provider": "codex", "status": "fallback", "source": "known", "dynamic": False, "count": len(fallback)}
    try:
        models = _list_openai_models(api_key, organization=_abconfig_value("openai_id"))
    except Exception as exc:
        cached = _cached_provider_models("codex")
        if cached:
            return {
                "provider": "codex",
                "status": "cached",
                "source": "cache",
                "dynamic": False,
                "count": len(cached),
                "message": str(exc),
            }
        _cache_provider_models("codex", fallback, status="fallback", message=str(exc))
        return {
            "provider": "codex",
            "status": "fallback",
            "source": "known",
            "dynamic": False,
            "count": len(fallback),
            "message": str(exc),
        }
    _cache_provider_models("codex", models, status="ok")
    return {"provider": "codex", "status": "ok", "source": "api", "dynamic": True, "count": len(models)}


def _refresh_nanogpt_models(config) -> dict[str, object]:
    credential = config.credentials.get("nanogpt", CredentialConfig())
    api_key = _first_secret(credential.api_key, os.environ.get("NANOGPT_API_KEY"), _abconfig_value("nanogpt_api"))
    if not api_key:
        cached = _cached_provider_models("nanogpt")
        return {
            "provider": "nanogpt",
            "status": "skipped",
            "source": "none",
            "dynamic": False,
            "count": len(cached),
            "message": "No nanoGPT API key configured.",
        }
    try:
        base_url = credential.base_url or "https://nano-gpt.com/api/subscription/v1"
        models = [f"nanogpt/{model}" for model in _list_nanogpt_models(base_url, api_key)]
    except Exception as exc:
        cached = _cached_provider_models("nanogpt")
        return {
            "provider": "nanogpt",
            "status": "cached" if cached else "error",
            "source": "cache" if cached else "none",
            "dynamic": False,
            "count": len(cached),
            "message": str(exc),
        }
    _cache_provider_models("nanogpt", models, status="ok")
    return {"provider": "nanogpt", "status": "ok", "source": "api", "dynamic": True, "count": len(models)}


def _refresh_google_models(config) -> dict[str, object]:
    credential = config.credentials.get("google") or config.credentials.get("gemini") or CredentialConfig()
    fallback = _known_google_models()
    api_key = _first_secret(credential.api_key, os.environ.get("GOOGLE_API_KEY"), _abconfig_value("gemini_api"))
    if not api_key:
        _cache_provider_models("google", fallback, status="fallback", message="No Google API key configured.")
        return {"provider": "google", "status": "fallback", "source": "known", "dynamic": False, "count": len(fallback)}
    try:
        models = _list_google_models(api_key)
    except Exception as exc:
        cached = _cached_provider_models("google")
        if cached:
            return {
                "provider": "google",
                "status": "cached",
                "source": "cache",
                "dynamic": False,
                "count": len(cached),
                "message": str(exc),
            }
        _cache_provider_models("google", fallback, status="fallback", message=str(exc))
        return {
            "provider": "google",
            "status": "fallback",
            "source": "known",
            "dynamic": False,
            "count": len(fallback),
            "message": str(exc),
        }
    _cache_provider_models("google", models, status="ok")
    return {"provider": "google", "status": "ok", "source": "api", "dynamic": True, "count": len(models)}


def _available_models_payload(config) -> list[dict[str, str]]:
    models: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(model_id: str, *, label: str, credential: str) -> None:
        if model_id in seen:
            return
        models.append({"id": model_id, "label": label, "credential": credential})
        seen.add(model_id)

    for provider, cred in config.credentials.items():
        if not cred.api_key and cred.type not in ("claude_code_login", "codex_login"):
            continue
        if provider == "anthropic":
            for model_id in _models_for_provider("claude_code", _known_claude_code_models()):
                add(model_id, label=f"Anthropic: {model_id}", credential="anthropic")
        elif provider == "openai":
            if cred.api_key:
                for model_id in (
                    "gpt-5.4",
                    "gpt-5.4-mini",
                    "gpt-5.4-nano",
                    "gpt-5",
                    "gpt-5-mini",
                    "gpt-5-nano",
                    "gpt-4.1",
                    "gpt-4.1-mini",
                    "gpt-4.1-nano",
                    "o3",
                    "o4-mini",
                ):
                    add(model_id, label=f"OpenAI: {model_id}", credential="openai")
            if cred.type == "codex_login" or cred.api_key:
                for model_id in _models_for_provider("codex", _known_codex_models()):
                    add(model_id, label=f"OpenAI: {model_id}", credential="openai")
        elif provider in ("google", "gemini"):
            for model_id in _models_for_provider("google", _known_google_models()):
                add(model_id, label=f"Google: {model_id.removeprefix('google/')}", credential="google")

    if is_codex_login_available():
        for model_id in _models_for_provider("codex", _known_codex_models()):
            add(model_id, label=f"OpenAI: {model_id}", credential="codex")

    nanogpt_cred = config.credentials.get("nanogpt")
    if nanogpt_cred and nanogpt_cred.api_key:
        nanogpt_models = _cached_provider_models("nanogpt")
        if not nanogpt_models:
            try:
                ngpt_base = nanogpt_cred.base_url or "https://nano-gpt.com/api/subscription/v1"
                nanogpt_models = [f"nanogpt/{model}" for model in _list_nanogpt_models(ngpt_base, nanogpt_cred.api_key)]
            except Exception:
                nanogpt_models = []
        for model_id in nanogpt_models:
            add(model_id, label=f"nanoGPT: {model_id.removeprefix('nanogpt/')}", credential="nanogpt")

    try:
        local_llm = LocalLLMConfig.model_validate(config.local_llm.model_dump())
        base_url = normalize_ollama_base_url(local_llm.base_url)
        for model in _list_ollama_models(base_url):
            model_id = f"ollama/{model}" if not model.startswith("ollama/") else model
            label = model.removeprefix("ollama/") if model.startswith("ollama/") else model
            add(model_id, label=label, credential="ollama")
    except Exception:
        pass

    return models


def _serialize_local_llm() -> dict[str, object]:
    config = load_config()
    local_llm = LocalLLMConfig.model_validate(config.local_llm.model_dump())
    base_url = normalize_ollama_base_url(local_llm.base_url)
    default_model = normalize_ollama_model_name(local_llm.default_model)
    presets = {name: normalize_ollama_model_name(model) for name, model in local_llm.presets.items()}

    available_models: list[str] = []
    reachable = False
    error: str | None = None
    try:
        available_models = _list_ollama_models(base_url)
        reachable = True
    except Exception as exc:  # pragma: no cover
        error = str(exc)

    ollama_credential = config.credentials.get("ollama")
    configured = (
        config.anima_defaults.credential == "ollama"
        and normalize_ollama_model_name(config.anima_defaults.model) == default_model
        and ollama_credential is not None
        and normalize_ollama_base_url(ollama_credential.base_url) == base_url
    )

    return {
        "base_url": base_url,
        "default_model": default_model,
        "presets": presets,
        "role_presets": dict(local_llm.role_presets),
        "recommended_presets": dict(DEFAULT_LOCAL_LLM_PRESETS),
        "recommended_role_presets": dict(DEFAULT_LOCAL_LLM_ROLE_PRESETS),
        "available_models": available_models,
        "reachable": reachable,
        "error": error,
        "configured": configured,
        "current_default_model": config.anima_defaults.model,
        "current_default_credential": config.anima_defaults.credential,
    }


def create_config_router() -> APIRouter:
    router = APIRouter()

    @router.get("/system/config")
    async def get_config(request: Request):
        """Read and return the AnimaWorks config with masked secrets."""
        config_path = Path.home() / ".animaworks" / "config.json"
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="Config file not found")

        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"Invalid config JSON: {exc}") from exc

        return _mask_secrets(config)

    @router.get("/system/init-status")
    async def init_status(request: Request):
        """Check initialization status of AnimaWorks."""
        base_dir = Path.home() / ".animaworks"
        config_path = base_dir / "config.json"
        animas_dir = base_dir / "animas"
        shared_dir = base_dir / "shared"

        # Count animas
        animas_count = 0
        if animas_dir.exists():
            for d in animas_dir.iterdir():
                if d.is_dir() and (d / "identity.md").exists():
                    animas_count += 1

        # Check API keys / subscription auth
        has_anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        anthropic_cred = load_config().credentials.get("anthropic", CredentialConfig())
        has_anthropic_subscription = anthropic_cred.type == "claude_code_login" and is_claude_code_available()
        has_anthropic = has_anthropic_key or has_anthropic_subscription
        has_openai = bool(os.environ.get("OPENAI_API_KEY"))
        has_codex_login = is_codex_login_available()
        has_openai_auth = has_openai or has_codex_login
        google_cred = load_config().credentials.get("google", CredentialConfig())
        has_google = bool(os.environ.get("GOOGLE_API_KEY")) or bool(google_cred.api_key)

        config_exists = config_path.exists()
        initialized = config_exists and animas_count > 0

        return {
            "checks": [
                {"label": t("config.config_file"), "ok": config_exists},
                {
                    "label": t("config.anima_registration"),
                    "ok": animas_count > 0,
                    "detail": t("config.anima_count_detail", count=animas_count),
                },
                {"label": t("config.shared_dir"), "ok": shared_dir.exists()},
                {"label": t("config.anthropic_auth"), "ok": has_anthropic},
                {"label": t("config.openai_auth"), "ok": has_openai_auth},
                {"label": t("config.google_api_key"), "ok": has_google},
                {"label": t("config.init_complete"), "ok": initialized},
            ],
            "config_exists": config_exists,
            "animas_count": animas_count,
            "api_keys": {
                "anthropic": has_anthropic,
                "openai": has_openai_auth,
                "codex_login": has_codex_login,
                "google": has_google,
            },
            "shared_dir_exists": shared_dir.exists(),
            "initialized": initialized,
        }

    @router.get("/settings/anthropic-auth")
    async def get_anthropic_auth(request: Request):
        """Return current Anthropic auth mode and runtime availability."""
        return _serialize_anthropic_auth()

    @router.get("/settings/openai-auth")
    async def get_openai_auth(request: Request):
        """Return current OpenAI auth mode and runtime availability."""
        return _serialize_openai_auth()

    @router.get("/settings/local-llm")
    async def get_local_llm(request: Request):
        """Return local Ollama-backed model settings and runtime availability."""
        return _serialize_local_llm()

    @router.get("/system/available-models")
    async def get_available_models(request: Request):
        """Return all available models (cloud + local) for UI dropdowns."""
        config = load_config()
        return {"models": _available_models_payload(config)}

    @router.post("/system/available-models/refresh")
    async def refresh_available_models(body: RefreshAvailableModelsRequest = RefreshAvailableModelsRequest()):
        """Refresh provider model catalogs and return the updated dropdown payload."""
        config = load_config()
        requested = body.providers or list(MODEL_CATALOG_PROVIDERS)
        providers = [provider for provider in requested if provider in MODEL_CATALOG_PROVIDERS]
        if not providers:
            raise HTTPException(status_code=400, detail="No supported providers requested.")

        results: list[dict[str, object]] = []
        for provider in providers:
            if provider == "claude_code":
                results.append(_refresh_claude_code_models(config))
            elif provider == "codex":
                results.append(_refresh_codex_models(config))
            elif provider == "nanogpt":
                results.append(_refresh_nanogpt_models(config))
            elif provider == "google":
                results.append(_refresh_google_models(config))

        return {
            "providers": results,
            "models": _available_models_payload(config),
        }

    @router.get("/system/available-tools")
    async def get_available_tools(request: Request):
        """Return available external tool module names (minus disabled services)."""
        try:
            from core.tooling.permissions import _disabled_service_tools
            from core.tools import TOOL_MODULES

            tools = sorted(set(TOOL_MODULES.keys()) - _disabled_service_tools())
        except Exception:
            tools = []
        return {"tools": tools}

    @router.get("/system/org-info")
    async def get_org_info(request: Request):
        """Return existing departments, titles, and anima names for team builder."""
        animas_dir = get_animas_dir()
        departments: set[str] = set()
        titles: set[str] = set()
        animas: list[dict[str, str]] = []

        if animas_dir.exists():
            for d in sorted(animas_dir.iterdir()):
                if not d.is_dir() or not (d / "identity.md").exists():
                    continue
                name = d.name
                status_path = d / "status.json"
                dept = ""
                title = ""
                if status_path.exists():
                    try:
                        sdata = json.loads(status_path.read_text(encoding="utf-8"))
                        dept = sdata.get("department", "")
                        title = sdata.get("title", "")
                    except Exception:
                        pass
                if dept:
                    departments.add(dept)
                if title:
                    titles.add(title)
                animas.append({"name": name, "department": dept, "title": title})

        return {
            "departments": sorted(departments),
            "titles": sorted(titles),
            "animas": animas,
        }

    @router.put("/settings/anthropic-auth")
    async def update_anthropic_auth(body: UpdateAnthropicAuthRequest, request: Request):
        """Persist Anthropic auth mode in config.json for the settings UI."""
        auth_mode = body.auth_mode.strip()
        if auth_mode not in ("api_key", "claude_code_login"):
            raise HTTPException(status_code=400, detail="Invalid auth mode. Must be 'api_key' or 'claude_code_login'.")

        config = load_config()
        current = config.credentials.get("anthropic", CredentialConfig())

        if auth_mode == "claude_code_login":
            if not is_claude_code_available():
                raise HTTPException(status_code=400, detail="Claude Code CLI is not installed.")
            config.credentials["anthropic"] = CredentialConfig(
                type="claude_code_login",
                api_key="",
                base_url=current.base_url,
                keys=dict(current.keys),
            )
            config.anima_defaults.mode_s_auth = "max"
            logger.info("Anthropic auth set to subscription (claude_code_login), mode_s_auth=max")
        else:
            api_key = body.api_key.strip()
            if not api_key:
                raise HTTPException(status_code=400, detail="API key is required for api_key mode.")
            config.credentials["anthropic"] = CredentialConfig(
                type="api_key",
                api_key=api_key,
                base_url=current.base_url,
                keys=dict(current.keys),
            )

        save_config(config)
        return _serialize_anthropic_auth()

    @router.put("/settings/openai-auth")
    async def update_openai_auth(body: UpdateOpenAIAuthRequest, request: Request):
        """Persist OpenAI auth mode in config.json for the settings UI."""
        auth_mode = body.auth_mode.strip()
        if auth_mode not in ("api_key", "codex_login"):
            raise HTTPException(status_code=400, detail=t("config.openai_auth_invalid_mode"))

        config = load_config()
        current = config.credentials.get("openai", CredentialConfig())

        if auth_mode == "codex_login":
            if not is_codex_cli_available():
                raise HTTPException(status_code=400, detail=t("config.codex_cli_not_installed"))
            if not is_codex_login_available():
                raise HTTPException(status_code=400, detail=t("config.codex_login_not_available"))
            config.credentials["openai"] = CredentialConfig(
                type="codex_login",
                api_key="",
                base_url=current.base_url,
                keys=dict(current.keys),
            )
        else:
            api_key = body.api_key.strip()
            if not api_key:
                raise HTTPException(status_code=400, detail=t("config.openai_api_key_required"))
            config.credentials["openai"] = CredentialConfig(
                type="api_key",
                api_key=api_key,
                base_url=current.base_url,
                keys=dict(current.keys),
            )

        save_config(config)
        return _serialize_openai_auth()

    @router.put("/settings/local-llm")
    async def update_local_llm(body: UpdateLocalLLMRequest, request: Request):
        """Persist local LLM settings and make Ollama the default execution target."""
        base_url = normalize_ollama_base_url(body.base_url)
        config = load_config()
        current_local_llm = LocalLLMConfig.model_validate(config.local_llm.model_dump())

        default_model = normalize_ollama_model_name(body.default_model)
        presets = dict(current_local_llm.presets)
        for name, model in body.presets.items():
            if name in presets and model.strip():
                presets[name] = normalize_ollama_model_name(model)

        role_presets = dict(current_local_llm.role_presets)
        for role_name, preset_name in body.role_presets.items():
            if role_name in role_presets and preset_name in presets:
                role_presets[role_name] = preset_name

        available_models = set(_list_ollama_models(base_url))
        requested_models = {default_model, *presets.values()}
        missing = sorted(model for model in requested_models if model not in available_models)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Ollama models not found on {base_url}: {', '.join(missing)}",
            )

        config.local_llm = LocalLLMConfig(
            base_url=base_url,
            default_model=default_model,
            presets=presets,
            role_presets=role_presets,
        )
        config.credentials["ollama"] = CredentialConfig(
            type="ollama",
            api_key="",
            base_url=base_url,
        )
        config.anima_defaults.model = default_model
        config.anima_defaults.credential = "ollama"

        save_config(config)
        return _serialize_local_llm()

    @router.post("/settings/local-llm/apply-role-presets")
    async def apply_local_llm_role_presets(request: Request):
        """Apply the configured role-based local LLM presets to existing animas."""
        config = load_config()
        updated = apply_local_llm_presets_to_animas(get_animas_dir(), config)
        return {"updated": updated, "count": len(updated)}

    # ── Discord channel membership ────────────────────────────

    @router.get("/discord/channel-members")
    async def get_discord_channel_members():
        """Return all Discord channel membership mappings."""
        config = load_config()
        return config.external_messaging.discord.channel_members

    @router.put("/discord/channel-members/{channel_id}")
    async def put_discord_channel_members(channel_id: str, request: Request):
        """Update Anima members for a Discord channel."""
        body = await request.json()
        members = body.get("members")
        if not isinstance(members, list):
            raise HTTPException(status_code=400, detail="members must be a list of anima names")
        if not all(isinstance(m, str) and m.strip() for m in members):
            raise HTTPException(status_code=400, detail="each member must be a non-empty string")

        config = load_config()
        known_animas = set(config.animas.keys())
        unknown = [m for m in members if m not in known_animas]
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown anima(s): {', '.join(unknown)}")

        members = [m.strip() for m in members]
        if members:
            config.external_messaging.discord.channel_members[channel_id] = members
        else:
            config.external_messaging.discord.channel_members.pop(channel_id, None)
        save_config(config)

        # Mirror membership to shared/channels/{board}.meta.json so
        # is_channel_member() (which is the source of truth for post_channel
        # ACL) reflects the UI-configured roster. Without this mirror the
        # two systems drift: config.json governs gateway routing while
        # meta.json governs posting ACL, and UI edits would only affect
        # the former.
        try:
            from core.messenger import ChannelMeta, load_channel_meta, save_channel_meta
            from core.paths import get_shared_dir

            board_name = config.external_messaging.discord.board_mapping.get(channel_id)
            if board_name:
                shared_dir = get_shared_dir()
                meta = load_channel_meta(shared_dir, board_name) or ChannelMeta(members=[])
                meta.members = list(members)
                save_channel_meta(shared_dir, board_name, meta)
        except Exception:
            logger.warning(
                "Failed to mirror channel members to meta.json for %s",
                channel_id,
                exc_info=True,
            )

        # Reload gateway routing if available
        gw = getattr(request.app.state, "discord_gateway_manager", None)
        if gw:
            try:
                gw.reload()
            except Exception:
                logger.debug("Discord gateway reload after member update failed", exc_info=True)

        return {"channel_id": channel_id, "members": members}

    @router.get("/discord/channels")
    async def get_discord_channels():
        """List Discord guild channels with membership info."""
        config = load_config()
        discord_cfg = config.external_messaging.discord
        guild_id = discord_cfg.guild_id
        if not guild_id:
            return {"channels": [], "error": "guild_id not configured"}

        try:
            from core.tools._base import get_credential
            from core.tools._discord_client import DiscordClient

            token = get_credential("discord", "discord", env_var="DISCORD_BOT_TOKEN")
            client = DiscordClient(token=token)
            try:
                raw_channels = client.get_guild_channels(guild_id)
            finally:
                client.close()
        except Exception as exc:
            logger.warning("Failed to fetch Discord channels: %s", exc)
            return {"channels": [], "error": str(exc)}

        channel_members = discord_cfg.channel_members
        board_mapping = discord_cfg.board_mapping
        channels = []
        for ch in raw_channels:
            if ch.get("type") != 0:  # text channels only
                continue
            ch_id = str(ch["id"])
            channels.append(
                {
                    "id": ch_id,
                    "name": ch.get("name", ""),
                    "parent_id": str(ch.get("parent_id", "") or ""),
                    "members": channel_members.get(ch_id, []),
                    "board": board_mapping.get(ch_id, ""),
                }
            )
        return {"channels": channels}

    return router
