from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config.models import CredentialConfig, load_config, save_config
from core.i18n import t
from core.platform.codex import is_codex_cli_available, is_codex_login_available

logger = logging.getLogger("animaworks.routes.config")


class UpdateOpenAIAuthRequest(BaseModel):
    auth_mode: str = "api_key"
    api_key: str = ""


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

        # Check API keys from environment
        has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
        has_openai = bool(os.environ.get("OPENAI_API_KEY"))
        has_codex_login = is_codex_login_available()
        has_openai_auth = has_openai or has_codex_login
        has_google = bool(os.environ.get("GOOGLE_API_KEY"))

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
                {"label": t("config.anthropic_api_key"), "ok": has_anthropic},
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

    @router.get("/settings/openai-auth")
    async def get_openai_auth(request: Request):
        """Return current OpenAI auth mode and runtime availability."""
        return _serialize_openai_auth()

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

    return router
