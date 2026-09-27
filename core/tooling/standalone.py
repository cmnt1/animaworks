from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Build a standalone ``ToolHandler`` for non-Web processes.

Shared by the MCP subprocess (``core.mcp.server``) and the
``animaworks-tool supervisor`` CLI, which both need a fully assembled
``ToolHandler`` from an ``anima_dir`` without a running ``AgentCore``.
"""

import json as _json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _load_permitted_categories(anima_dir: Path) -> set[str]:
    """Load permitted external tool categories from permissions.json."""
    from core.config.models import load_permissions
    from core.tooling.permissions import get_permitted_tools

    config = load_permissions(anima_dir)
    return get_permitted_tools(config)


def _build_background_manager(anima_dir: Path) -> Any:
    """Build a BackgroundTaskManager for a standalone ToolHandler process.

    Mirrors ``AgentCore._build_background_manager()`` but operates
    without the full AgentCore.  Returns None when disabled in config.
    """
    try:
        from core.config.models import load_config

        config = load_config()
        if not config.background_task.enabled:
            return None

        from core.integrations import TOOL_MODULES
        from core.integrations._base import load_execution_profiles
        from core.tasks.background import BackgroundTaskManager

        profiles = load_execution_profiles(TOOL_MODULES)
        config_eligible = {name: tc.threshold_s for name, tc in config.background_task.eligible_tools.items()}

        mgr = BackgroundTaskManager.from_profiles(
            anima_dir=anima_dir,
            anima_name=anima_dir.name,
            profiles=profiles,
            config_eligible=config_eligible or None,
        )

        mgr.on_complete = _make_on_complete_callback(anima_dir)
        logger.info("BackgroundTaskManager initialised for standalone (anima=%s)", anima_dir.name)
        return mgr

    except Exception:
        logger.debug("BackgroundTaskManager init skipped in standalone", exc_info=True)
        return None


def _make_on_complete_callback(anima_dir: Path) -> Any:
    """Create an on_complete callback that writes notification files.

    Without access to WebSocket or HumanNotifier, we only write a
    notification file under ``state/background_notifications/`` for the
    next heartbeat to pick up.
    """
    from core.i18n import t as _t

    async def _on_complete(task: Any) -> None:
        try:
            subject = _t("anima.bg_task_done", tool=task.tool_name)
            if task.status.value == "failed":
                subject = _t("anima.bg_task_failed", tool=task.tool_name)

            notif_dir = anima_dir / "state" / "background_notifications"
            notif_dir.mkdir(parents=True, exist_ok=True)
            notif_path = notif_dir / f"{task.task_id}.md"
            notif_content = (
                f"# {subject}\n\n"
                f"- task_id: {task.task_id}\n"
                f"- tool: {task.tool_name}\n"
                f"- status: {task.status.value}\n"
                f"- result: {task.summary()}\n"
            )
            notif_path.write_text(notif_content, encoding="utf-8")
            logger.info(
                "Standalone bg task notification written: %s (tool=%s, status=%s)",
                task.task_id,
                task.tool_name,
                task.status.value,
            )
        except Exception:
            logger.exception("Failed to write standalone bg task notification for %s", task.task_id)

    return _on_complete


def build_standalone_tool_handler(anima_dir: Path, *, for_mcp: bool) -> Any:
    """Assemble a fully configured ``ToolHandler`` from *anima_dir*.

    Used by the MCP subprocess (``for_mcp=True``) and the
    ``animaworks-tool supervisor`` CLI (``for_mcp=False``).  The
    ``for_mcp`` flag only controls the ``debug_superuser`` gate that
    skips the ``status.json`` check for short-lived MCP tool subprocesses.
    """
    anima_dir = Path(anima_dir).resolve()

    # ── MemoryManager ──
    from core.memory import MemoryManager

    memory = MemoryManager(anima_dir)

    # ── Messenger ──
    from core.messaging.messenger import Messenger
    from core.paths import get_shared_dir

    messenger = Messenger(shared_dir=get_shared_dir(), anima_name=anima_dir.name)

    # ── HumanNotifier (optional) ──
    human_notifier = None
    try:
        from core.config.models import load_config
        from core.notification.notifier import HumanNotifier

        config = load_config()
        human_notifier = HumanNotifier.from_config(config.human_notification)
        if human_notifier.channel_count == 0:
            human_notifier = None
    except Exception:
        logger.debug("HumanNotifier init skipped", exc_info=True)

    # ── Tool registry and personal tools (filesystem discovery) ──
    tool_registry: list[str] = []
    personal_tools: dict[str, str] = {}
    try:
        from core.integrations import discover_common_tools, discover_personal_tools

        permitted = _load_permitted_categories(anima_dir)
        tool_registry = sorted(permitted)
        common = discover_common_tools()
        personal = discover_personal_tools(anima_dir)
        personal_tools = {**common, **personal}
    except Exception:
        logger.debug("Tool discovery failed", exc_info=True)

    # ── ToolHandler ──
    from core.tooling.handler import ToolHandler

    # Check debug_superuser flag from status.json
    _superuser = False
    _status_path = anima_dir / "status.json"
    if not (for_mcp and "ANIMAWORKS_MCP_TOOLS" in os.environ) and _status_path.is_file():
        try:
            _su_data = _json.loads(_status_path.read_text(encoding="utf-8"))
            _superuser = bool(_su_data.get("debug_superuser"))
        except (ValueError, OSError):
            pass

    # ── BackgroundTaskManager ──
    bg_manager = _build_background_manager(anima_dir)

    handler = ToolHandler(
        anima_dir=anima_dir,
        memory=memory,
        messenger=messenger,
        tool_registry=tool_registry,
        personal_tools=personal_tools,
        on_message_sent=None,
        on_schedule_changed=None,
        human_notifier=human_notifier,
        background_manager=bg_manager,
        superuser=_superuser,
    )

    logger.info("ToolHandler initialised for anima '%s' (%s)", anima_dir.name, anima_dir)
    return handler
