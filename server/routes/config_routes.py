from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config.io import get_config_path
from core.config.model_catalog import validate_chat_model  # noqa: F401
from core.config.model_discovery import discover_models
from core.config.models import CredentialConfig, load_config, update_config
from core.i18n import t
from core.platform.claude_code import is_claude_code_available
from core.platform.codex import is_codex_cli_available, is_codex_login_available

logger = logging.getLogger("animaworks.routes.config")


class UpdateAnthropicAuthRequest(BaseModel):
    auth_mode: str = "api_key"
    api_key: str = ""


class UpdateOpenAIAuthRequest(BaseModel):
    auth_mode: str = "api_key"
    api_key: str = ""


class UpdateConfigValueRequest(BaseModel):
    key: str
    value: Any


class SaveConfigWizardRequest(BaseModel):
    credentials: dict[str, dict[str, Any]]
    anima_names: list[str]
    status_updates: dict[str, dict[str, str]]


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
        if not value:
            # An unset secret stays visibly unset ("***" would read as configured).
            return value
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


def create_config_router() -> APIRouter:
    router = APIRouter()

    @router.get("/system/config")
    async def get_config(request: Request):
        """Read and return the AnimaWorks config with masked secrets."""
        config_path = get_config_path()
        if not config_path.exists():
            raise HTTPException(status_code=404, detail="Config file not found")

        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"Invalid config JSON: {exc}") from exc

        return _mask_secrets(config)

    @router.put("/system/config/value")
    async def update_config_value(body: UpdateConfigValueRequest, request: Request):
        """Apply one validated CLI config-set operation through the root server."""
        from core.config.ops import legacy_model_status_target, set_config_value

        if not body.key.strip() or any(not part for part in body.key.split(".")):
            raise HTTPException(status_code=400, detail="key must be a non-empty dot-notation path")
        activity_update = None
        if body.key == "activity_level":
            from server.supervisor.activity_schedule import apply_activity_schedule

            if not isinstance(body.value, int) or isinstance(body.value, bool) or not 10 <= body.value <= 400:
                raise HTTPException(status_code=400, detail="activity_level must be int 10-400")
            activity_update = await asyncio.to_thread(apply_activity_schedule, activity_level=body.value)
        elif body.key == "activity_schedule":
            from core.config.models import ActivityScheduleEntry
            from server.supervisor.activity_schedule import apply_activity_schedule

            if not isinstance(body.value, list) or len(body.value) > 24:
                raise HTTPException(status_code=400, detail="activity_schedule must be a list with at most 24 entries")
            try:
                entries = [ActivityScheduleEntry.model_validate(value) for value in body.value]
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            activity_update = await asyncio.to_thread(apply_activity_schedule, activity_schedule=entries)

        target = legacy_model_status_target(body.key)
        if target is not None:
            from core.anima.factory import validate_anima_name

            anima_name, _field = target
            name_error = validate_anima_name(anima_name)
            if name_error:
                raise HTTPException(status_code=400, detail=name_error)
        try:
            if activity_update is None:
                await asyncio.to_thread(set_config_value, body.key, body.value)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to update config value %s", body.key)
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        supervisor = getattr(request.app.state, "supervisor", None)
        if activity_update is not None and supervisor is not None:
            methods: list[str] = []
            if activity_update.activity_level_changed:
                methods.append("reschedule_heartbeat")
            if body.key == "activity_schedule" and activity_update.activity_schedule_changed:
                methods.append("reload_activity_schedule")
            for name in list(getattr(supervisor, "processes", {})):
                for method in methods:
                    try:
                        await supervisor.send_request(name, method, {}, timeout=10.0)
                    except Exception:
                        logger.warning("Failed to send %s to %s after config update", method, name, exc_info=True)
        elif body.key == "heartbeat.interval_minutes" and supervisor is not None:
            for name in list(getattr(supervisor, "processes", {})):
                try:
                    await supervisor.send_request(name, "reschedule_heartbeat", {}, timeout=10.0)
                except Exception:
                    logger.warning("Failed to reschedule heartbeat for %s after config update", name, exc_info=True)
        elif target is not None and supervisor is not None:
            anima_name, status_field = target
            if anima_name in getattr(supervisor, "processes", {}) and status_field not in {"supervisor", "speciality"}:
                method = "reschedule_heartbeat" if status_field == "heartbeat_interval_minutes" else "reload_config"
                try:
                    await supervisor.send_request(anima_name, method, {}, timeout=10.0)
                except Exception:
                    logger.info("Settings reload deferred until next start for anima=%s", anima_name, exc_info=True)
        return {"ok": True, "key": body.key, "status_target": target}

    @router.put("/system/config/wizard")
    async def save_config_wizard(body: SaveConfigWizardRequest, request: Request):
        """Apply the interactive CLI wizard changes on the root server."""
        from core.config.models import CredentialConfig
        from core.config.ops import save_config_wizard as persist_config_wizard
        from core.paths import get_animas_dir

        try:
            credentials = {name: CredentialConfig.model_validate(payload) for name, payload in body.credentials.items()}
            await asyncio.to_thread(
                persist_config_wizard,
                credentials,
                body.anima_names,
                body.status_updates,
                get_animas_dir(),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to persist config wizard changes")
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        supervisor = getattr(request.app.state, "supervisor", None)
        if supervisor is not None:
            for anima_name in body.status_updates:
                if anima_name not in getattr(supervisor, "processes", {}):
                    continue
                try:
                    await supervisor.send_request(anima_name, "reload_config", {}, timeout=10.0)
                except Exception:
                    logger.info("Config reload deferred until next start for anima=%s", anima_name, exc_info=True)
        return {"ok": True, "updated_animas": list(body.status_updates)}

    @router.get("/settings/anthropic-auth")
    async def get_anthropic_auth(request: Request):
        """Return current Anthropic auth mode and runtime availability."""
        return _serialize_anthropic_auth()

    @router.get("/settings/openai-auth")
    async def get_openai_auth(request: Request):
        """Return current OpenAI auth mode and runtime availability."""
        return _serialize_openai_auth()

    @router.get("/system/available-models")
    def get_available_models(request: Request, refresh: bool = False):
        """Return all available models (cloud + local) for UI dropdowns.

        Sync (non-async) so FastAPI runs it in a threadpool: model discovery
        uses blocking subprocess / ``httpx`` calls that would otherwise stall
        the whole event loop for up to the per-probe timeout.

        ``refresh`` forces a fresh probe instead of the cached catalog.
        """
        models = discover_models(refresh=refresh)
        payload = [
            {
                "id": m.id,
                "label": m.label,
                "credential": m.group.lower(),
                "mode": m.mode,
                "model": m.model,
                "group": m.group,
                "note": m.note,
                "source": m.source,
            }
            for m in models
        ]
        groups = list(dict.fromkeys(m.group for m in models))
        return {
            "models": payload,
            "groups": groups,
            "generated_at": datetime.now(UTC).astimezone().isoformat(),
        }

    @router.get("/system/available-tools")
    async def get_available_tools(request: Request):
        """Return available external tool module names (minus disabled services)."""
        try:
            from core.integrations import TOOL_MODULES
            from core.tooling.permissions import _disabled_service_tools

            tools = sorted(set(TOOL_MODULES.keys()) - _disabled_service_tools())
        except Exception:
            tools = []
        return {"tools": tools}

    @router.put("/settings/anthropic-auth")
    async def update_anthropic_auth(body: UpdateAnthropicAuthRequest, request: Request):
        """Persist Anthropic auth mode in config.json for the settings UI."""
        auth_mode = body.auth_mode.strip()
        if auth_mode not in ("api_key", "claude_code_login"):
            raise HTTPException(status_code=400, detail="Invalid auth mode. Must be 'api_key' or 'claude_code_login'.")

        if auth_mode == "claude_code_login" and not is_claude_code_available():
            raise HTTPException(status_code=400, detail="Claude Code CLI is not installed.")
        api_key = body.api_key.strip()
        if auth_mode == "api_key" and not api_key:
            raise HTTPException(status_code=400, detail="API key is required for api_key mode.")

        def apply_anthropic_auth(config):
            current = config.credentials.get("anthropic", CredentialConfig())
            if auth_mode == "claude_code_login":
                config.credentials["anthropic"] = CredentialConfig(
                    type="claude_code_login",
                    api_key="",
                    base_url=current.base_url,
                    keys=dict(current.keys),
                )
                config.anima_defaults.mode_s_auth = "max"
            else:
                config.credentials["anthropic"] = CredentialConfig(
                    type="api_key",
                    api_key=api_key,
                    base_url=current.base_url,
                    keys=dict(current.keys),
                )
            return config

        update_config(apply_anthropic_auth)
        if auth_mode == "claude_code_login":
            logger.info("Anthropic auth set to subscription (claude_code_login), mode_s_auth=max")
        return _serialize_anthropic_auth()

    @router.put("/settings/openai-auth")
    async def update_openai_auth(body: UpdateOpenAIAuthRequest, request: Request):
        """Persist OpenAI auth mode in config.json for the settings UI."""
        auth_mode = body.auth_mode.strip()
        if auth_mode not in ("api_key", "codex_login"):
            raise HTTPException(status_code=400, detail=t("config.openai_auth_invalid_mode"))

        if auth_mode == "codex_login":
            if not is_codex_cli_available():
                raise HTTPException(status_code=400, detail=t("config.codex_cli_not_installed"))
            if not is_codex_login_available():
                raise HTTPException(status_code=400, detail=t("config.codex_login_not_available"))
        api_key = body.api_key.strip()
        if auth_mode == "api_key" and not api_key:
            raise HTTPException(status_code=400, detail=t("config.openai_api_key_required"))

        def apply_openai_auth(config):
            current = config.credentials.get("openai", CredentialConfig())
            config.credentials["openai"] = CredentialConfig(
                type="codex_login" if auth_mode == "codex_login" else "api_key",
                api_key="" if auth_mode == "codex_login" else api_key,
                base_url=current.base_url,
                keys=dict(current.keys),
            )
            return config

        update_config(apply_openai_auth)
        return _serialize_openai_auth()

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

        members = [m.strip() for m in members]

        def update_channel_members(config):
            unknown = [member for member in members if member not in config.animas]
            if unknown:
                raise HTTPException(status_code=400, detail=f"unknown anima(s): {', '.join(unknown)}")
            channel_members = config.external_messaging.discord.channel_members
            if members:
                channel_members[channel_id] = members
            else:
                channel_members.pop(channel_id, None)
            return config

        update_config(update_channel_members)

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
            from core.credentials import get_credential
            from core.integrations._discord_client import DiscordClient

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
