from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Project → Discord thread registry and routing.

Long-running project tasks (FIN-047 etc.) get a dedicated Discord thread.
This module keeps a registry mapping project task codes to their thread, so:

- Board posts mentioning a registered code are routed INTO the thread instead
  of scattering across the top level of #finance / #management
  (see ``BoardDiscordSync.sync_board_post``).
- Closing a meeting that carries a ``project_task_code`` auto-creates the
  thread in the department's mapped channel and posts a kickoff summary
  (see ``ensure_project_thread``).

Registry file: ``{shared}/system/project_threads.json``::

    {"FIN-047": {"channel_id": "...", "thread_id": "...",
                 "title": "...", "created_at": "..."}}
"""

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from core.paths import get_shared_dir
from core.time_utils import now_iso

logger = logging.getLogger("animaworks.project_threads")

_LOCK = threading.Lock()

# Project code prefix → board name (board_mapping resolves board → channel id).
_CODE_PREFIX_BOARDS = {
    "FIN": "finance",
    "PROP": "property",
    "AFF": "affiliate",
    "GEN": "general",
    "ADM": "administration",
    "OPS": "ops",
    "MGT": "management",
}

# Fallback: meeting の project_department 表記 → board name
_DEPARTMENT_BOARDS = {
    "投資": "finance",
    "finance": "finance",
    "不動産": "property",
    "property": "property",
    "アフィリエイト": "affiliate",
    "affiliate": "affiliate",
    "総務": "administration",
    "administration": "administration",
}

_TASK_CODE_RE = re.compile(r"^[A-Z]{2,5}-\d{1,4}$")


def _registry_path() -> Path:
    return get_shared_dir() / "system" / "project_threads.json"


def load_registry() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_registry_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_registry(registry: dict[str, dict[str, Any]]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def register_thread(code: str, *, channel_id: str, thread_id: str, title: str = "") -> None:
    """Register (or overwrite) a project thread mapping."""
    with _LOCK:
        registry = load_registry()
        registry[code] = {
            "channel_id": str(channel_id),
            "thread_id": str(thread_id),
            "title": title,
            "created_at": registry.get(code, {}).get("created_at") or now_iso(),
        }
        _save_registry(registry)
    logger.info("Project thread registered: %s -> thread %s", code, thread_id)


def resolve_thread_for_text(text: str) -> tuple[str, str, str] | None:
    """Return (code, channel_id, thread_id) when text mentions a registered project code."""
    if not text:
        return None
    registry = load_registry()
    for code, entry in registry.items():
        channel_id = entry.get("channel_id")
        thread_id = entry.get("thread_id")
        if not channel_id or not thread_id:
            continue
        if re.search(rf"(?i)(?<![A-Z0-9]){re.escape(code)}(?![0-9])", text):
            return code, str(channel_id), str(thread_id)
    return None


def resolve_thread_for_code(code: str) -> tuple[str, str] | None:
    """Return (channel_id, thread_id) for an exact registered code."""
    entry = load_registry().get(code)
    if entry and entry.get("channel_id") and entry.get("thread_id"):
        return str(entry["channel_id"]), str(entry["thread_id"])
    return None


def _resolve_board_channel(code: str, department: str) -> str | None:
    """Resolve the Discord channel id for a project code / department."""
    from core.config.models import load_config

    discord_cfg = load_config().external_messaging.discord
    prefix = code.split("-", 1)[0].upper() if code else ""
    board = _CODE_PREFIX_BOARDS.get(prefix)
    if board is None and department:
        dept = department.strip()
        board = _DEPARTMENT_BOARDS.get(dept) or _DEPARTMENT_BOARDS.get(dept.lower())
    if board is None:
        return None
    for ch_id, bname in discord_cfg.board_mapping.items():
        if bname == board:
            return str(ch_id)
    return None


def ensure_project_thread(
    code: str,
    *,
    title: str = "",
    department: str = "",
    kickoff_text: str = "",
) -> tuple[str, str] | None:
    """Return the project's (channel_id, thread_id), creating the thread if needed.

    Reuses a registered thread when present. Otherwise creates a public thread
    named ``[CODE] title`` in the department's mapped channel, posts
    ``kickoff_text`` into it, and records the mapping.  Fail-soft: returns
    None when Discord is disabled or the channel cannot be resolved.
    """
    if not code or not _TASK_CODE_RE.match(code.strip()):
        logger.info("ensure_project_thread: skipping invalid task code %r", code)
        return None
    code = code.strip()

    existing = resolve_thread_for_code(code)
    if existing:
        return existing

    from core.config.models import load_config

    if not load_config().external_messaging.discord.enabled:
        return None

    channel_id = _resolve_board_channel(code, department)
    if not channel_id:
        logger.warning("ensure_project_thread: no channel mapping for %s (dept=%s)", code, department)
        return None

    thread_name = f"[{code}]{title}" if title else f"[{code}]"
    try:
        from core.tools._discord_client import DiscordClient

        client = DiscordClient()
        try:
            thread = client.start_thread(channel_id, thread_name[:100])
        finally:
            client.close()
    except Exception:
        logger.exception("ensure_project_thread: failed to create thread for %s", code)
        return None

    thread_id = str(thread.get("id", ""))
    if not thread_id:
        logger.warning("ensure_project_thread: no thread id returned for %s", code)
        return None

    register_thread(code, channel_id=channel_id, thread_id=thread_id, title=title)

    if kickoff_text:
        try:
            from core.discord_webhooks import get_webhook_manager

            get_webhook_manager().send_as_anima(channel_id, "AnimaWorks 会議", kickoff_text, thread_id=thread_id)
        except Exception:
            logger.exception("ensure_project_thread: kickoff post failed for %s", code)

    return channel_id, thread_id
