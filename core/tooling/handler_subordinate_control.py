from __future__ import annotations

from core.tooling._handler_protocols import (
    _SubordinateControlHost,
)

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""SubordinateControlMixin — disable, enable, model, restart, ping, read_state."""

import json as _json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.i18n import t
from core.tooling.handler_base import _error_result
from core.tooling.org_helpers import OrgHelpersMixin, resolve_anima_name

if TYPE_CHECKING:
    from core.activity.logger import ActivityLogger

logger = logging.getLogger("animaworks.tool_handler")


class SubordinateControlMixin(OrgHelpersMixin):
    """Mixin for subordinate control tools: disable, enable, model, restart, ping, read_state."""

    # Declared for type-checker visibility
    _anima_dir: Path
    _anima_name: str
    _activity: ActivityLogger
    _process_supervisor: Any

    def _request_subordinate_control(
        self: _SubordinateControlHost,
        target_name: str,
        action: str,
        **values: Any,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Ask root to apply a descendant change, or write locally in offline CLI mode."""
        from core.anima.settings_store import settings_server_running
        from core.platform.process_role import get_process_role

        role = get_process_role()
        if role == "root" or (role == "cli" and not settings_server_running()):
            from core.anima.settings_store import update_status
            from core.config.model_config import smart_update_model, update_status_model
            from core.paths import get_animas_dir

            target_dir = get_animas_dir() / target_name
            changed = False
            result: dict[str, Any] = {}
            try:
                if action in {"enable", "disable"}:
                    enabled = action == "enable"

                    def set_enabled(status: dict[str, Any]) -> None:
                        nonlocal changed
                        if status.get("enabled", True) != enabled:
                            status["enabled"] = enabled
                            changed = True

                    update_status(target_dir, set_enabled)
                elif action == "request_restart":
                    update_status(target_dir, lambda status: status.__setitem__("restart_requested", True))
                    changed = True
                elif action == "set_model":
                    result = smart_update_model(target_dir, model=str(values.get("model") or ""))
                    changed = True
                elif action == "set_background_model":
                    update_status_model(
                        target_dir,
                        background_model=str(values.get("background_model") or ""),
                        background_credential=str(values.get("background_credential") or ""),
                    )
                    changed = True
            except (ValueError, OSError, FileNotFoundError) as exc:
                return None, _error_result("InvalidState", str(exc))
            return {"ok": True, "changed": changed, "result": result}, None

        from urllib.parse import quote

        from core.host_api import host_api, response_detail

        try:
            response = host_api.post(
                f"/api/internal/animas/{quote(target_name, safe='')}/control",
                json={"action": action, **values},
                timeout=30.0,
            )
        except Exception as exc:
            logger.warning("Root subordinate-control API failed for %s", target_name, exc_info=True)
            return None, _error_result("HostAPIError", f"Root settings API unavailable: {exc}")
        if response.status_code >= 400:
            error_type = {
                400: "InvalidArguments",
                401: "PermissionDenied",
                403: "PermissionDenied",
                404: "AnimaNotFound",
                409: "InvalidState",
            }.get(response.status_code, "HostAPIError")
            return None, _error_result(error_type, response_detail(response))
        try:
            payload = response.json()
        except Exception as exc:
            return None, _error_result("HostAPIError", f"Invalid root settings response: {exc}")
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            return None, _error_result("HostAPIError", "Unexpected root settings response")
        return payload, None

    def _handle_disable_subordinate(self: _SubordinateControlHost, args: dict[str, Any]) -> str:
        """Disable a subordinate anima (set enabled=false in status.json)."""
        target_name = resolve_anima_name(args.get("name", ""))
        reason = args.get("reason", "")

        if not target_name:
            return _error_result("InvalidArguments", "name is required")

        err = self._check_descendant(target_name)
        if err:
            return err

        response, error = self._request_subordinate_control(target_name, "disable")
        if error:
            return error
        if not response.get("changed"):
            return t("handler.already_disabled", target_name=target_name)
        log_summary = t("handler.disable_log_summary", target_name=target_name)
        if reason:
            log_summary += t("handler.disable_reason", reason=reason)
        self._activity.log(
            "tool_use",
            tool="disable_subordinate",
            summary=log_summary,
            meta={"target": target_name, "reason": reason},
        )

        logger.info(
            "disable_subordinate: %s disabled %s (reason=%s)",
            self._anima_name,
            target_name,
            reason or "(none)",
        )

        result = t("handler.disabled_success", target_name=target_name)
        if reason:
            result += "\n" + t("handler.reason_prefix", reason=reason)
        return result

    def _handle_enable_subordinate(self: _SubordinateControlHost, args: dict[str, Any]) -> str:
        """Enable a subordinate anima (set enabled=true in status.json)."""
        target_name = resolve_anima_name(args.get("name", ""))

        if not target_name:
            return _error_result("InvalidArguments", "name is required")

        err = self._check_descendant(target_name)
        if err:
            return err

        response, error = self._request_subordinate_control(target_name, "enable")
        if error:
            return error
        if not response.get("changed"):
            return t("handler.already_enabled", target_name=target_name)

        self._activity.log(
            "tool_use",
            tool="enable_subordinate",
            summary=t("handler.enable_log_summary", target_name=target_name),
            meta={"target": target_name},
        )

        logger.info(
            "enable_subordinate: %s enabled %s",
            self._anima_name,
            target_name,
        )

        return t("handler.enabled_success", target_name=target_name)

    def _handle_set_subordinate_model(self: _SubordinateControlHost, args: dict[str, Any]) -> str:
        """Change a subordinate anima's LLM model (updates status.json)."""
        from core.config.models import KNOWN_MODELS

        target_name = resolve_anima_name(args.get("name", ""))
        model = args.get("model", "").strip()
        reason = args.get("reason", "")

        if not target_name:
            return _error_result("InvalidArguments", "name is required")
        if not model:
            return _error_result("InvalidArguments", "model is required")

        err = self._check_descendant(target_name)
        if err:
            return err

        known_names = {m["name"] for m in KNOWN_MODELS}
        warn_msg = ""
        if model not in known_names:
            logger.warning(
                "set_subordinate_model: unknown model '%s' for '%s'. Not in KNOWN_MODELS — proceeding anyway.",
                model,
                target_name,
            )
            warn_msg = "\n" + t("handler.model_warning", model=model)

        response, error = self._request_subordinate_control(
            target_name,
            "set_model",
            model=model,
        )
        if error:
            return error
        update_result = response.get("result") or {}

        log_summary = t("handler.model_change_log", target_name=target_name, model=model)
        if reason:
            log_summary += t("handler.disable_reason", reason=reason)
        self._activity.log(
            "tool_use",
            tool="set_subordinate_model",
            summary=log_summary,
            meta={"target": target_name, "model": model, "reason": reason},
        )

        logger.info(
            "set_subordinate_model: %s changed %s model to %s (reason=%s)",
            self._anima_name,
            target_name,
            model,
            reason or "(none)",
        )

        result_msg = t("handler.model_changed", target_name=target_name, model=model)
        if update_result.get("family_changed"):
            result_msg += f"\n  credential: {update_result['credential']}, mode: {update_result['execution_mode']}"
        if reason:
            result_msg += "\n" + t("handler.reason_prefix", reason=reason)
        return result_msg + warn_msg

    def _handle_set_subordinate_background_model(self: _SubordinateControlHost, args: dict[str, Any]) -> str:
        """Change a subordinate's background model (heartbeat/cron)."""
        target_name = args.get("name", "")
        model = args.get("model", "")
        credential = args.get("credential")
        reason = args.get("reason", "")

        if not target_name:
            return _error_result("InvalidArguments", "name is required")

        err = self._check_descendant(target_name)
        if err:
            return err

        _, error = self._request_subordinate_control(
            target_name,
            "set_background_model",
            background_model=model if model else "",
            background_credential=credential if credential else "",
        )
        if error:
            return error

        log_summary = t(
            "handler.bg_model_change_log",
            target_name=target_name,
            model=model or t("handler.none_value"),
        )
        if reason:
            log_summary += t("handler.reason_prefix", reason=reason)
        self._activity.log(
            "tool_use",
            tool="set_subordinate_background_model",
            summary=log_summary,
            meta={"target": target_name, "model": model, "reason": reason},
        )

        logger.info(
            "set_subordinate_background_model: %s changed %s background_model to %s (reason=%s)",
            self._anima_name,
            target_name,
            model or "(clear)",
            reason or "(none)",
        )

        if model:
            return t("handler.bg_model_changed", target_name=target_name, model=model)
        return t("handler.bg_model_cleared", target_name=target_name)

    def _handle_restart_subordinate(self: _SubordinateControlHost, args: dict[str, Any]) -> str:
        """Request restart of a subordinate anima via sentinel flag in status.json."""
        target_name = resolve_anima_name(args.get("name", ""))
        reason = args.get("reason", "")

        if not target_name:
            return _error_result("InvalidArguments", "name is required")

        err = self._check_descendant(target_name)
        if err:
            return err

        _, error = self._request_subordinate_control(target_name, "request_restart")
        if error:
            return error

        log_summary = t("handler.restart_log", target_name=target_name)
        if reason:
            log_summary += t("handler.disable_reason", reason=reason)
        self._activity.log(
            "tool_use",
            tool="restart_subordinate",
            summary=log_summary,
            meta={"target": target_name, "reason": reason},
        )

        logger.info(
            "restart_subordinate: %s requested restart of %s (reason=%s)",
            self._anima_name,
            target_name,
            reason or "(none)",
        )

        result = t("handler.restart_success", target_name=target_name)
        if reason:
            result += "\n" + t("handler.reason_prefix", reason=reason)
        return result

    def _handle_ping_subordinate(self: _SubordinateControlHost, args: dict[str, Any]) -> str:
        """Ping subordinate(s) for liveness check."""
        from datetime import datetime

        from core.time_utils import ensure_aware, now_local

        target_name = args.get("name")

        if target_name:
            err = self._check_descendant(target_name)
            if err:
                return err
            targets = [target_name]
        else:
            targets = self._get_all_descendants()
            if not targets:
                return t("handler.no_subordinates")

        from core.paths import get_animas_dir

        animas_dir = get_animas_dir()
        results: list[dict[str, Any]] = []

        for name in targets:
            desc_dir = animas_dir / name
            result: dict[str, Any] = {
                "name": name,
                "alive": False,
                "process_status": "unknown",
                "last_activity": t("handler.last_activity_unknown"),
                "since": "",
            }

            if self._process_supervisor:
                try:
                    ps = self._process_supervisor.get_process_status(name)
                    if isinstance(ps, dict):
                        result["process_status"] = ps.get("status", "unknown")
                        result["alive"] = ps.get("status") == "running"
                    else:
                        result["process_status"] = str(ps)
                        result["alive"] = "running" in str(ps).lower()
                except Exception:
                    result["process_status"] = "not_found"
            else:
                from core.paths import get_data_dir

                sock = get_data_dir() / "run" / "sockets" / f"{name}.sock"
                if sock.exists():
                    result["alive"] = True
                    result["process_status"] = "running (socket exists)"
                else:
                    status_file = desc_dir / "status.json"
                    if status_file.exists():
                        try:
                            sdata = _json.loads(status_file.read_text(encoding="utf-8"))
                            result["process_status"] = "enabled" if sdata.get("enabled", True) else "disabled"
                        except Exception:
                            logger.debug("Failed to read status.json for %s", name, exc_info=True)

            try:
                recent = self._read_recent_activity(desc_dir, limit=1)
                if recent:
                    result["last_activity"] = recent[-1].ts
                    ts = ensure_aware(datetime.fromisoformat(recent[-1].ts))
                    elapsed = (now_local() - ts).total_seconds()
                    minutes = int(elapsed / 60)
                    if minutes < 60:
                        result["since"] = t("handler.since_minutes", minutes=minutes)
                    else:
                        hours = minutes // 60
                        result["since"] = t("handler.since_hours", hours=hours, minutes=minutes % 60)
                else:
                    result["last_activity"] = t("handler.last_activity_none")
            except Exception:
                logger.debug("Failed to read activity for %s", name, exc_info=True)

            results.append(result)

        self._activity.log(
            "tool_use",
            tool="ping_subordinate",
            summary=t("handler.ping_summary", target=t("handler.all_descendants") if not target_name else target_name),  # noqa: SIM212
        )

        return _json.dumps(results, ensure_ascii=False, indent=2)

    def _handle_read_subordinate_state(self: _SubordinateControlHost, args: dict[str, Any]) -> str:
        """Read a descendant's current task state."""
        target_name = args.get("name", "")
        if not target_name:
            return _error_result("InvalidArguments", "name is required")

        err = self._check_descendant(target_name)
        if err:
            return err

        from core.paths import get_animas_dir

        desc_dir = get_animas_dir() / target_name

        parts: list[str] = [t("handler.state_title", target_name=target_name), ""]

        task_file = desc_dir / "state" / "current_state.md"
        if task_file.exists():
            try:
                content = task_file.read_text(encoding="utf-8").strip()
                parts.append(t("handler.state_current_state"))
                parts.append(content if content else t("handler.state_none"))
            except Exception:
                parts.append(t("handler.state_current_state"))
                parts.append(t("handler.state_unreadable"))
        else:
            parts.append(t("handler.state_current_state"))
            parts.append(t("handler.state_none"))

        parts.append("")

        self._activity.log(
            "tool_use",
            tool="read_subordinate_state",
            summary=t("handler.state_read_summary", target_name=target_name),
        )

        return "\n".join(parts)
