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

from core.integrations._base import dispatch_by_table

# Re-exports for backward compatibility
from core.integrations._slack_cache import MessageCache  # noqa: F401
from core.integrations._slack_cli import cli_main, get_cli_guide  # noqa: F401
from core.integrations._slack_client import SlackClient  # noqa: F401
from core.integrations._slack_markdown import (  # noqa: F401
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
    # gated: requires explicit "slack_send" / "slack_channel_post" in permissions.
    "send": {"expected_seconds": 10, "background_eligible": False, "gated": True},
    "search": {"expected_seconds": 30, "background_eligible": False},
    "unreplied": {"expected_seconds": 30, "background_eligible": False},
    "channel_post": {"expected_seconds": 10, "background_eligible": False, "gated": True},
    "channel_update": {"expected_seconds": 10, "background_eligible": False, "gated": True},
}


# ── Token Resolution ───────────────────────────────────────


def _resolve_slack_token(args: dict[str, Any]) -> str | None:
    """Resolve per-Anima Slack bot token from tool dispatch args."""
    from core.channels.tokens import resolve_per_anima_token
    from core.integrations._base import resolve_env_style_credential

    return resolve_per_anima_token(
        "slack",
        args.get("anima_dir"),
        credential_lookup=resolve_env_style_credential,
        log=True,
    )


def _resolve_slack_identity(args: dict[str, Any]) -> tuple[str, str]:
    """Resolve Anima display name and icon URL for Slack messages.

    See :func:`core.integrations._anima_icon_url.resolve_anima_icon_identity`.
    """
    from core.integrations._anima_icon_url import resolve_anima_icon_identity

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
                    "thread_ts": {
                        "type": "string",
                        "description": "Optional parent message ts to reply in-thread",
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


def _dispatch_slack_send(args: dict[str, Any]) -> Any:
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


def _dispatch_slack_messages(args: dict[str, Any]) -> Any:
    from core.integrations._slack_cache import MessageCache  # noqa: F811

    client = SlackClient(token=_resolve_slack_token(args))
    channel_id = client.resolve_channel(args["channel"])
    cache = MessageCache()
    try:
        limit = args.get("limit", 20)
        messages = client.channel_history(channel_id, limit=limit)
        if messages:
            for message in messages:
                user_id = message.get("user", message.get("bot_id", ""))
                if user_id:
                    message["user_name"] = client.resolve_user_name(user_id)
            cache.upsert_messages(channel_id, messages)
            cache.update_sync_state(channel_id)
        return cache.get_recent(channel_id, limit=limit)
    finally:
        cache.close()


def _dispatch_slack_search(args: dict[str, Any]) -> Any:
    from core.integrations._slack_cache import MessageCache  # noqa: F811

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


def _dispatch_slack_unreplied(args: dict[str, Any]) -> Any:
    from core.integrations._slack_cache import MessageCache  # noqa: F811

    client = SlackClient(token=_resolve_slack_token(args))
    cache = MessageCache()
    try:
        client.auth_test()
        return cache.find_unreplied(client.my_user_id or "")
    finally:
        cache.close()


def _dispatch_slack_channels(args: dict[str, Any]) -> Any:
    client = SlackClient(token=_resolve_slack_token(args))
    return client.channels()


def _dispatch_slack_react(args: dict[str, Any]) -> Any:
    client = SlackClient(token=_resolve_slack_token(args))
    channel_id = client.resolve_channel(args["channel"])
    return client.add_reaction(
        channel_id,
        args["emoji"],
        args["message_ts"],
    )


def _dispatch_slack_channel_post(args: dict[str, Any]) -> Any:
    client = SlackClient(token=_resolve_slack_token(args))
    slack_text = md_to_slack_mrkdwn(args["text"])
    username, icon_url = _resolve_slack_identity(args)
    response = client.post_message(
        args["channel_id"],
        slack_text,
        thread_ts=args.get("thread_ts"),
        username=username,
        icon_url=icon_url,
    )
    timestamp = response.get("ts", "") if response is not None else ""
    return {"status": "ok", "channel": args["channel_id"], "ts": timestamp}


def _dispatch_slack_channel_update(args: dict[str, Any]) -> Any:
    client = SlackClient(token=_resolve_slack_token(args))
    slack_text = md_to_slack_mrkdwn(args["text"])
    client.update_message(args["channel_id"], args["ts"], slack_text)
    return {"status": "ok", "channel": args["channel_id"], "ts": args["ts"]}


_DISPATCH_HANDLERS = {
    "slack_send": _dispatch_slack_send,
    "slack_messages": _dispatch_slack_messages,
    "slack_search": _dispatch_slack_search,
    "slack_unreplied": _dispatch_slack_unreplied,
    "slack_channels": _dispatch_slack_channels,
    "slack_react": _dispatch_slack_react,
    "slack_channel_post": _dispatch_slack_channel_post,
    "slack_channel_update": _dispatch_slack_channel_update,
}


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call by schema name."""
    return dispatch_by_table(_DISPATCH_HANDLERS, name, args)


if __name__ == "__main__":
    cli_main()
