# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Discord integration for AnimaWorks.

Provides:
- DiscordClient: Discord REST API v10 wrapper with rate-limit retry
- MessageCache: SQLite cache for offline search
- get_tool_schemas(): Anthropic tool_use schemas
- cli_main(): standalone CLI entry point
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.integrations._base import dispatch_by_table, logger

# Re-exports (also used by :func:`dispatch`)
from core.integrations._discord_cache import MessageCache
from core.integrations._discord_cli import cli_main, get_cli_guide  # noqa: F401
from core.integrations._discord_client import DiscordClient
from core.integrations._discord_markdown import (  # noqa: F401
    clean_discord_markup,
    md_to_discord,
    truncate,
)

# ── Execution Profile ─────────────────────────────────────

EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "guilds": {"expected_seconds": 10, "background_eligible": False},
    "channels": {"expected_seconds": 10, "background_eligible": False},
    "messages": {"expected_seconds": 30, "background_eligible": False},
    # gated: requires explicit "discord_send" in permissions allow list.
    "send": {"expected_seconds": 10, "background_eligible": False, "gated": True},
    "search": {"expected_seconds": 30, "background_eligible": False},
    # gated: requires explicit "discord_channel_post" in permissions allow list.
    "channel_post": {"expected_seconds": 10, "background_eligible": False, "gated": True},
    "unreplied": {"expected_seconds": 10, "background_eligible": False},
}


# ── Token Resolution ───────────────────────────────────────


def _resolve_discord_token(args: dict[str, Any]) -> str | None:
    """Resolve per-Anima Discord bot token from tool dispatch args."""
    from core.channels.tokens import resolve_per_anima_token
    from core.credentials import _lookup_shared_credentials, _lookup_vault_credential

    return resolve_per_anima_token(
        "discord",
        args.get("anima_dir"),
        credential_lookup=lambda key: _lookup_vault_credential(key) or _lookup_shared_credentials(key),
        log=True,
    )


def _resolve_discord_identity(args: dict[str, Any]) -> tuple[str, str]:
    """Resolve Anima display name and icon URL for Discord-related context.

    See :func:`core.integrations._anima_icon_url.resolve_anima_icon_identity`.
    """
    from core.integrations._anima_icon_url import resolve_anima_icon_identity

    anima_dir = args.get("anima_dir")
    if not anima_dir:
        return ("", "")
    return resolve_anima_icon_identity(Path(anima_dir).name, channel_config=None)


# ── Tool Schemas ───────────────────────────────────────────


def get_tool_schemas() -> list[dict]:
    """Return Anthropic tool_use schemas for Discord tools.

    ``discord_channel_post`` is a gated action: it requires
    ``discord_channel_post: yes`` in permissions.md.
    """
    return [
        {
            "name": "discord_channel_post",
            "description": (
                "Post a message to a Discord text channel. "
                "The message appears with your Anima identity (name + avatar). "
                "Returns the message ID for future reference."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": (
                            "Discord parent channel ID. When replying into a thread, "
                            "this MUST be the parent text channel ID (not the thread ID) — "
                            "Discord webhooks are attached to the parent channel and "
                            "target the thread via the separate thread_id parameter."
                        ),
                    },
                    "text": {
                        "type": "string",
                        "description": "Message text (Markdown supported, max 2000 chars)",
                    },
                    "thread_id": {
                        "type": "string",
                        "description": (
                            "Thread channel ID to post into. REQUIRED when replying to "
                            "a message that arrived from within a thread — otherwise the "
                            "post lands in the parent channel. Use the value shown in the "
                            "[reply_instruction: ...] annotation of the incoming message."
                        ),
                    },
                },
                "required": ["channel_id", "text"],
            },
        },
        {
            "name": "discord_unreplied",
            "description": (
                "Find Discord messages that mention your name but have not been replied to. "
                "Useful during heartbeat to check for pending requests."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Discord channel ID to search (optional — searches all cached channels if omitted)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                    },
                },
                "required": [],
            },
        },
    ]


# ── Dispatch ───────────────────────────────────────────────


def _dispatch_discord_send(args: dict[str, Any]) -> Any:
    anima_dir = args.get("anima_dir")
    if anima_dir:
        anima_name = Path(anima_dir).name
        discord_text = md_to_discord(args["message"])
        try:
            from core.messaging.discord_webhooks import get_webhook_manager

            msg_id = get_webhook_manager().send_as_anima(
                args["channel_id"],
                anima_name,
                discord_text,
                thread_id=args.get("thread_id") or None,
            )
            if msg_id:
                return {
                    "status": "ok",
                    "channel_id": args["channel_id"],
                    "thread_id": args.get("thread_id") or "",
                    "message_id": msg_id,
                }
            logger.warning("Webhook send returned no message id for discord_send; falling back to bot token")
        except Exception:
            logger.warning("Webhook send failed for discord_send; falling back to bot token", exc_info=True)
        fallback_channel_id = args.get("thread_id") or args["channel_id"]
        client = DiscordClient(token=_resolve_discord_token(args))
        try:
            response = client.send_message(
                fallback_channel_id,
                discord_text,
                reply_to=args.get("reply_to"),
            )
            return {
                "status": "ok",
                "channel_id": response.get("channel_id", fallback_channel_id)
                if isinstance(response, dict)
                else fallback_channel_id,
                "thread_id": args.get("thread_id") or "",
                "message_id": response.get("id", "") if isinstance(response, dict) else "",
                "fallback": "bot_token",
            }
        finally:
            client.close()
    client = DiscordClient(token=_resolve_discord_token(args))
    try:
        return client.send_message(
            args["channel_id"],
            args["message"],
            reply_to=args.get("reply_to"),
        )
    finally:
        client.close()


def _dispatch_discord_messages(args: dict[str, Any]) -> Any:
    client = DiscordClient(token=_resolve_discord_token(args))
    cache = MessageCache()
    try:
        channel_id = args["channel_id"]
        limit = int(args.get("limit", 20))
        messages = client.channel_history(channel_id, limit=limit)
        if messages:
            for message in messages:
                author = message.get("author")
                if isinstance(author, dict):
                    user_id = author.get("id", "")
                    if user_id and not message.get("user_id"):
                        message["user_id"] = user_id
                    username = author.get("global_name") or author.get("username", "")
                    if username and not message.get("user_name"):
                        message["user_name"] = username
            cache.upsert_messages(channel_id, messages)
            cache.update_sync_state(channel_id)
        return cache.get_recent(channel_id, limit=limit)
    finally:
        client.close()
        cache.close()


def _dispatch_discord_search(args: dict[str, Any]) -> Any:
    cache = MessageCache()
    try:
        return cache.search(
            args["keyword"],
            channel_id=args.get("channel_id"),
            limit=int(args.get("limit", 50)),
        )
    finally:
        cache.close()


def _dispatch_discord_guilds(args: dict[str, Any]) -> Any:
    client = DiscordClient(token=_resolve_discord_token(args))
    try:
        return client.guilds()
    finally:
        client.close()


def _dispatch_discord_channels(args: dict[str, Any]) -> Any:
    client = DiscordClient(token=_resolve_discord_token(args))
    try:
        return client.channels(args["guild_id"])
    finally:
        client.close()


def _dispatch_discord_react(args: dict[str, Any]) -> Any:
    client = DiscordClient(token=_resolve_discord_token(args))
    try:
        return client.add_reaction(
            args["channel_id"],
            args["message_id"],
            args["emoji"],
        )
    finally:
        client.close()


def _dispatch_discord_channel_post(args: dict[str, Any]) -> Any:
    _trigger = args.get("_trigger", "")
    if _trigger.startswith("inbox"):
        return {
            "status": "blocked",
            "message": "discord_channel_post is unnecessary during inbox processing. "
            "Your final text response is AUTOMATICALLY posted to Discord by the framework. "
            "Do NOT attempt to send via TaskExec or any other workaround. "
            "Just write your response as plain text — it will be delivered.",
        }

    discord_text = md_to_discord(args["text"])
    anima_name = ""
    anima_dir = args.get("anima_dir")
    if anima_dir:
        anima_name = Path(anima_dir).name

    thread_id = args.get("thread_id") or None

    # Use webhook manager for Anima identity if available
    if anima_name:
        try:
            from core.messaging.discord_webhooks import get_webhook_manager

            wm = get_webhook_manager()
            msg_id = wm.send_as_anima(
                args["channel_id"],
                anima_name,
                discord_text,
                thread_id=thread_id,
            )
            if msg_id:
                return {
                    "status": "ok",
                    "channel_id": args["channel_id"],
                    "thread_id": thread_id or "",
                    "message_id": msg_id,
                }
            logger.warning("Webhook send returned no message id; falling back to bot token")
        except Exception:
            logger.warning("Webhook send failed; falling back to bot token", exc_info=True)

    fallback_channel_id = thread_id or args["channel_id"]
    client = DiscordClient(token=_resolve_discord_token(args))
    try:
        response = client.send_message(fallback_channel_id, discord_text)
        return {
            "status": "ok",
            "channel_id": response.get("channel_id", fallback_channel_id)
            if isinstance(response, dict)
            else fallback_channel_id,
            "thread_id": thread_id or "",
            "message_id": response.get("id", "") if isinstance(response, dict) else "",
            "fallback": "bot_token",
        }
    finally:
        client.close()


def _dispatch_discord_unreplied(args: dict[str, Any]) -> Any:
    cache = MessageCache()
    try:
        anima_name = ""
        anima_dir = args.get("anima_dir")
        if anima_dir:
            anima_name = Path(anima_dir).name
        if not anima_name:
            return {"status": "error", "message": "Cannot determine Anima name"}

        return cache.find_unreplied(
            anima_name,
            channel_id=args.get("channel_id"),
            limit=int(args.get("limit", 10)),
        )
    finally:
        cache.close()


_DISPATCH_HANDLERS = {
    "discord_send": _dispatch_discord_send,
    "discord_messages": _dispatch_discord_messages,
    "discord_search": _dispatch_discord_search,
    "discord_guilds": _dispatch_discord_guilds,
    "discord_channels": _dispatch_discord_channels,
    "discord_react": _dispatch_discord_react,
    "discord_channel_post": _dispatch_discord_channel_post,
    "discord_unreplied": _dispatch_discord_unreplied,
}


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call by schema name."""
    return dispatch_by_table(_DISPATCH_HANDLERS, name, args)


if __name__ == "__main__":
    cli_main()
