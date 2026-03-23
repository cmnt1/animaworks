# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Slack integration for AnimaWorks.

Provides:
- SlackClient: Slack Web API wrapper with rate-limit retry and pagination
- MessageCache: SQLite cache for offline search and unreplied detection
- get_tool_schemas(): Anthropic tool_use schemas
- cli_main(): standalone CLI entry point
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.tools._base import logger

# Re-exports for backward compatibility
from core.tools._slack_cache import MessageCache  # noqa: F401
from core.tools._slack_cli import cli_main, get_cli_guide  # noqa: F401
from core.tools._slack_client import SlackClient  # noqa: F401
from core.tools._slack_markdown import (  # noqa: F401
    clean_slack_markup,
    format_slack_ts,
    md_to_slack_mrkdwn,
    taskboard_md_to_slack,
    truncate,
)

# ── Execution Profile ─────────────────────────────────────

EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "channels": {"expected_seconds": 10, "background_eligible": False},
    "messages": {"expected_seconds": 30, "background_eligible": False},
    "send": {"expected_seconds": 10, "background_eligible": False},
    "search": {"expected_seconds": 30, "background_eligible": False},
    "unreplied": {"expected_seconds": 30, "background_eligible": False},
    # gated: requires explicit "slack_channel_post: yes" in permissions.md.
    "channel_post": {"expected_seconds": 10, "background_eligible": False, "gated": True},
    "channel_update": {"expected_seconds": 10, "background_eligible": False, "gated": True},
}


# ── Token Resolution ───────────────────────────────────────


def _resolve_per_anima_token(anima_dir: str | Path | None) -> str | None:
    """Resolve per-Anima Slack bot token from anima_dir path.

    Uses ``SLACK_BOT_TOKEN__<anima_name>`` from vault.json / shared/credentials.json.
    Returns None to fall back to the shared token.
    """
    if not anima_dir:
        return None
    from core.tools._base import _lookup_shared_credentials, _lookup_vault_credential

    anima_name = Path(anima_dir).name
    per_anima_key = f"SLACK_BOT_TOKEN__{anima_name}"
    token = _lookup_vault_credential(per_anima_key)
    if token:
        logger.debug("Using per-Anima Slack token for '%s'", anima_name)
        return token
    token = _lookup_shared_credentials(per_anima_key)
    if token:
        logger.debug("Using per-Anima Slack token for '%s'", anima_name)
        return token
    return None


def _resolve_slack_token(args: dict[str, Any]) -> str | None:
    """Resolve per-Anima Slack bot token from tool dispatch args."""
    return _resolve_per_anima_token(args.get("anima_dir"))


def _resolve_slack_identity(args: dict[str, Any]) -> tuple[str, str]:
    """Resolve Anima display name and icon URL for Slack messages.

    See :func:`core.tools._anima_icon_url.resolve_anima_icon_identity`.
    """
    from core.tools._anima_icon_url import resolve_anima_icon_identity

    anima_dir = args.get("anima_dir")
    if not anima_dir:
        return ("", "")
    return resolve_anima_icon_identity(Path(anima_dir).name, channel_config=None)


# ── Tool Schemas ───────────────────────────────────────────


def get_tool_schemas() -> list[dict]:
    """Return Anthropic tool_use schemas for Slack tools.

    ``slack_channel_post`` / ``slack_channel_update`` are gated actions:
    they require ``slack_channel_post: yes`` / ``slack_channel_update: yes``
    in permissions.md.
    """
    return [
        {
            "name": "slack_channel_post",
            "description": (
                "Post a message to an actual Slack channel via Bot Token API. "
                "Returns the message ts for future updates via slack_channel_update. "
                "Use this for external Slack channels (not internal Board)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Slack channel ID (e.g. C0AJ4J5KK46)",
                    },
                    "text": {
                        "type": "string",
                        "description": "Message text (Markdown will be converted to Slack mrkdwn)",
                    },
                },
                "required": ["channel_id", "text"],
            },
        },
        {
            "name": "slack_channel_update",
            "description": (
                "Update an existing Slack message by ts. "
                "The message is silently replaced (no notification). "
                "Use this for live dashboards like task-board."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "channel_id": {"type": "string", "description": "Slack channel ID"},
                    "ts": {
                        "type": "string",
                        "description": "Message timestamp to update (from slack_channel_post result)",
                    },
                    "text": {"type": "string", "description": "New message text"},
                },
                "required": ["channel_id", "ts", "text"],
            },
        },
    ]


# ── Dispatch ───────────────────────────────────────────────


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call by schema name."""
    if name == "slack_send":
        client = SlackClient(token=_resolve_slack_token(args))
        channel_id = client.resolve_channel(args["channel"])
        username, icon_url = _resolve_slack_identity(args)
        return client.post_message(
            channel_id,
            md_to_slack_mrkdwn(args["message"]),
            thread_ts=args.get("thread_ts"),
            username=username,
            icon_url=icon_url,
        )
    if name == "slack_messages":
        from core.tools._slack_cache import MessageCache

        client = SlackClient(token=_resolve_slack_token(args))
        channel_id = client.resolve_channel(args["channel"])
        cache = MessageCache()
        try:
            limit = args.get("limit", 20)
            msgs = client.channel_history(channel_id, limit=limit)
            if msgs:
                for m in msgs:
                    uid = m.get("user", m.get("bot_id", ""))
                    if uid:
                        m["user_name"] = client.resolve_user_name(uid)
                cache.upsert_messages(channel_id, msgs)
                cache.update_sync_state(channel_id)
            return cache.get_recent(channel_id, limit=limit)
        finally:
            cache.close()
    if name == "slack_search":
        from core.tools._slack_cache import MessageCache

        client = SlackClient(token=_resolve_slack_token(args))
        cache = MessageCache()
        try:
            channel_id = None
            if args.get("channel"):
                channel_id = client.resolve_channel(args["channel"])
            return cache.search(
                args["keyword"],
                channel_id=channel_id,
                limit=args.get("limit", 50),
            )
        finally:
            cache.close()
    if name == "slack_unreplied":
        from core.tools._slack_cache import MessageCache

        client = SlackClient(token=_resolve_slack_token(args))
        cache = MessageCache()
        try:
            client.auth_test()
            return cache.find_unreplied(client.my_user_id or "")
        finally:
            cache.close()
    if name == "slack_channels":
        client = SlackClient(token=_resolve_slack_token(args))
        return client.channels()
    if name == "slack_react":
        client = SlackClient(token=_resolve_slack_token(args))
        channel_id = client.resolve_channel(args["channel"])
        return client.add_reaction(
            channel_id,
            args["emoji"],
            args["message_ts"],
        )
    if name == "slack_channel_post":
        client = SlackClient(token=_resolve_slack_token(args))
        slack_text = md_to_slack_mrkdwn(args["text"])
        username, icon_url = _resolve_slack_identity(args)
        resp = client.post_message(
            args["channel_id"],
            slack_text,
            username=username,
            icon_url=icon_url,
        )
        ts = resp.get("ts", "") if resp is not None else ""
        return {"status": "ok", "channel": args["channel_id"], "ts": ts}
    if name == "slack_channel_update":
        client = SlackClient(token=_resolve_slack_token(args))
        slack_text = md_to_slack_mrkdwn(args["text"])
        client.update_message(args["channel_id"], args["ts"], slack_text)
        return {"status": "ok", "channel": args["channel_id"], "ts": args["ts"]}
    raise ValueError(f"Unknown tool: {name}")


if __name__ == "__main__":
    cli_main()
