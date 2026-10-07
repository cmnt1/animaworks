from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config.models import PermissionsConfig

"""Shared permission engine for external tool access control.

Both the MCP server (``core.mcp.server``) and the executor layer
(``core.agent.executor_factory``) use :func:`get_permitted_tools` to resolve
which external tools an Anima is allowed to invoke, keeping the logic in a
single authoritative location.

Runtime gates are evaluated through :func:`check_tool_access` (the loader)
which wraps the pure :func:`evaluate_tool_access` decision engine and is
fail-closed: any configuration or profile-loading failure results in a
denied (:data:`ToolAccessDecision`) rather than silently passing.

Supports action-level gating: dangerous sub-actions (e.g. ``gmail_send``)
require explicit ``external_tools.allow`` entries even when ``allow_all`` is
true. Callers may separately supply a verified, thread-scoped Slack reply grant;
that exception does not alter the legacy allow-list behavior.
"""

import importlib.util
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from core.i18n import t

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolAccessDecision:
    """Result of an external tool access check.

    Attributes:
        allowed: Whether the tool/action may be executed.
        reason: Case-level reason — ``"ok"`` | ``"tool_denied"`` |
            ``"tool_not_permitted"`` | ``"action_gated"`` | ``"check_failed"``.
        message: User (Anima)-facing explanation, generated via ``core.i18n.t()``.
    """

    allowed: bool
    reason: str
    message: str = ""


# ── Public API ────────────────────────────────────────────


def _disabled_service_tools() -> set[str]:
    """Return tool module names whose backing service is disabled in config.json.

    Prevents e.g. ``slack_channel_post`` appearing in an anima's tool list
    when ``external_messaging.slack.enabled`` is false.  Only modules that
    are registered in ``TOOL_MODULES`` AND whose service is explicitly
    disabled are excluded; unconfigured services are left as-is.
    """
    disabled: set[str] = set()
    try:
        from core.config.models import load_config

        cfg = load_config()
        em = cfg.external_messaging
        if not em.slack.enabled:
            disabled.add("slack")
        if not em.chatwork.enabled:
            disabled.add("chatwork")
    except Exception:
        logger.debug("Config unavailable at import time — skip filtering", exc_info=True)
    return disabled


def _permitted_names(
    config: PermissionsConfig,
    all_core_tools: set[str],
    disabled: frozenset[str],
) -> set[str]:
    """Compute the permitted name set (tool modules + action keys) from config."""
    deny = set(config.external_tools.deny)
    if config.external_tools.allow_all:
        base = all_core_tools - disabled - deny
        action_permits = set(config.external_tools.allow) - all_core_tools - deny
        return base | action_permits
    if config.external_tools.allow:
        return set(config.external_tools.allow) - deny
    return (all_core_tools - disabled) - deny


def get_permitted_tools(config: PermissionsConfig) -> set[str]:
    """Get permitted tool names from structured permissions config."""
    from core.tooling.policy.registry import get_tool_modules

    all_tools = set(get_tool_modules()) - _disabled_service_tools()
    return _permitted_names(config, all_tools, frozenset(_disabled_service_tools()))


def _load_execution_profile(tool_name: str) -> dict[str, dict[str, object]] | None:
    """Load EXECUTION_PROFILE from the tool module.

    Args:
        tool_name: Tool module name (e.g. ``gmail``).

    Returns:
        The module's EXECUTION_PROFILE dict, or None if not found or load fails.
    """
    try:
        from core.tooling.policy.registry import get_tool_modules, load_tool_module

        tool_modules = get_tool_modules()
        if tool_name not in tool_modules:
            return None
        mod = load_tool_module(tool_name, tool_modules)
        return getattr(mod, "EXECUTION_PROFILE", None)
    except Exception:
        logger.debug("Failed to load EXECUTION_PROFILE for %s", tool_name, exc_info=True)
        return None


def _load_profile_from_file(tool_file: Path | None) -> dict[str, dict[str, object]] | None:
    """Load EXECUTION_PROFILE from a file-based (common/personal) tool module."""
    if tool_file is None:
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            f"animaworks_tool_profile_{tool_file.stem}",
            tool_file,
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return getattr(mod, "EXECUTION_PROFILE", None)
    except Exception:
        logger.debug("Failed to load EXECUTION_PROFILE from %s", tool_file, exc_info=True)
        return None


# ── Evaluation engine (pure function) ────────────────────


def evaluate_tool_access(
    tool_name: str,
    action: str | None,
    *,
    config: PermissionsConfig,
    origin: Literal["core", "common", "personal"],
    profile: Mapping[str, Mapping[str, object]] | None,
    disabled_services: frozenset[str] = frozenset(),
    reply_grant_ok: bool = False,
    core_tools: set[str] | None = None,
) -> ToolAccessDecision:
    """Evaluate whether a tool (and optional gated action) is permitted.

    Pure decision function — performs no I/O. Configuration, execution
    profile, disabled-service set, and optional runtime core-tool set are supplied as arguments.

    Decision order:
      1. ``tool_name`` in ``external_tools.deny`` → ``tool_denied``
      2. ``origin == "core"`` and ``tool_name`` not in the permitted core
         set (computed from config + ``disabled_services``) → ``tool_not_permitted``
      3. ``origin`` in (common, personal): ``allow_all`` is false and ``allow``
         is non-empty and ``tool_name`` not in ``allow`` → ``tool_not_permitted``
      4. ``action`` matches a gated entry in ``profile`` (with ``_`` → ``-``
         leniency): permitted only if ``f"{tool}_{gated_as or profile_action}"``
         is in ``allow`` and not in ``deny``, or a caller-verified reply grant
         applies to one of the Slack reply actions; otherwise → ``action_gated``.
         Explicit permission is required even when ``allow_all`` is true.
      5. Otherwise → ``ok``.

    ``core_tools`` defaults to the static host registry. Enclave-aware callers
    pass the registry for their current runtime so enclave-only tools are
    permitted only inside an enabled enclave.
    """
    from core.tooling.policy.registry import TOOL_MODULES

    deny = set(config.external_tools.deny)
    allow = set(config.external_tools.allow)

    # 1. Deny always wins.
    if tool_name in deny:
        return ToolAccessDecision(False, "tool_denied", t("tooling.tool_denied", tool=tool_name))

    # 2. Core tools must be in the permitted core set.
    if origin == "core":
        all_core_tools = set(TOOL_MODULES if core_tools is None else core_tools)
        permitted = _permitted_names(config, all_core_tools, disabled_services)
        if tool_name not in permitted:
            return ToolAccessDecision(
                False,
                "tool_not_permitted",
                t("tooling.tool_not_permitted", tool=tool_name),
            )

    # 3. Common / personal tools use an allow-list (unless allow_all).
    elif origin in {"common", "personal"}:
        if not config.external_tools.allow_all and config.external_tools.allow:
            if tool_name not in allow:
                return ToolAccessDecision(
                    False,
                    "tool_not_permitted",
                    t("tooling.tool_not_permitted", tool=tool_name),
                )

    # 4. Gated action check.
    if action is not None and isinstance(profile, dict):
        matches = _action_candidates(profile, action)
        if matches:
            profile_action = matches[0]
            info = profile.get(profile_action)
            if isinstance(info, dict) and info.get("gated") is True:
                action_key = f"{tool_name}_{info.get('gated_as', profile_action)}"
                if action_key in allow and action_key not in deny:
                    return ToolAccessDecision(True, "ok")
                if reply_grant_ok and action_key in {"slack_send", "slack_channel_post"} and action_key not in deny:
                    return ToolAccessDecision(True, "ok")
                return ToolAccessDecision(
                    False,
                    "action_gated",
                    t("tooling.gated_action_denied", tool=tool_name, action=action),
                )

    # 5. Default allow.
    return ToolAccessDecision(True, "ok")


def _action_candidates(
    profile: Mapping[str, Mapping[str, object]],
    action: str,
) -> tuple[str, ...]:
    """Return profile action keys an ``action`` resolves to (with ``_``↔``-``)."""
    if action in profile:
        return (action,)
    dashed = action.replace("_", "-")
    if dashed in profile:
        return (dashed,)
    return ()


# ── Loader ───────────────────────────────────────────────


def check_tool_access(
    anima_dir: Path | None,
    tool_name: str,
    action: str | None,
    *,
    origin: Literal["core", "common", "personal"],
    tool_file: Path | None = None,
    reply_grant_ok: bool = False,
) -> ToolAccessDecision:
    """Load configuration/execution-profile and evaluate tool access.

    Fail-closed: any exception during permission loading or profile import
    yields ``ToolAccessDecision(False, "check_failed", ...)`` rather than
    silently allowing the call.
    """
    try:
        from core.config.models import PermissionsConfig, load_permissions

        config = load_permissions(anima_dir) if anima_dir else PermissionsConfig()

        core_tools = _core_tool_names() if origin == "core" else None
        if origin == "core":
            profile = _load_execution_profile(tool_name) if tool_name in core_tools else None
        else:
            profile = _load_profile_from_file(tool_file)

        # ``external_messaging.<svc>.enabled`` controls the inbound integration
        # and only filters tool listings; it must not block explicit calls.
        return evaluate_tool_access(
            tool_name,
            action,
            config=config,
            origin=origin,
            profile=profile,
            reply_grant_ok=reply_grant_ok,
            core_tools=core_tools,
        )
    except Exception as e:
        logger.warning("Permission check failed for %s %s: %s", tool_name, action, e, exc_info=True)
        return ToolAccessDecision(
            False,
            "check_failed",
            t("tooling.permission_check_failed", tool=tool_name, error=type(e).__name__),
        )


def _core_tool_names() -> set[str]:
    from core.tooling.policy.registry import get_tool_modules

    return set(get_tool_modules().keys())


# ── Compatibility wrapper ────────────────────────────────


def is_action_gated(tool_name: str, action: str, permitted: set[str]) -> bool:
    """Check if a tool action is gated and not explicitly permitted.

    Thin wrapper over :func:`evaluate_tool_access` for legacy callers.
    When the tool's ``EXECUTION_PROFILE`` cannot be loaded the action is
    treated as gated (fail-closed).

    Args:
        tool_name: Tool module name (e.g. ``gmail``).
        action: Action/subcommand name (e.g. ``send``).
        permitted: Set of permitted names from :func:`get_permitted_tools`.

    Returns:
        True if the action is gated AND not in permitted (i.e. should be blocked).
        False if non-gated or explicitly permitted.
    """
    from core.config.models import ExternalToolsPermission, PermissionsConfig

    config = PermissionsConfig(
        external_tools=ExternalToolsPermission(
            allow_all=True,
            allow=list(permitted),
            deny=[],
        )
    )
    profile = _load_execution_profile(tool_name)
    if profile is None:
        # Cannot confirm the action is non-gated without a profile → fail-closed.
        return True
    decision = evaluate_tool_access(
        tool_name,
        action,
        config=config,
        origin="core",
        profile=profile,
        disabled_services=frozenset(),
    )
    return decision.reason == "action_gated"
