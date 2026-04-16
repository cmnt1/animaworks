from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Automatic outbound routing for external platform messages.

When an Anima processes an inbox message that originated from Slack,
this module posts the LLM response back to the originating
channel/thread automatically — without relying on the LLM to
explicitly call ``slack_channel_post``.
"""

import logging
import os
from typing import Any

import httpx

from core.messenger import InboxItem
from core.tools._base import _lookup_shared_credentials, _lookup_vault_credential

logger = logging.getLogger("animaworks.outbound_auto")

_SLACK_POST_URL = "https://slack.com/api/chat.postMessage"
_SLACK_TIMEOUT = 30.0
_MAX_SLACK_TEXT = 40000


def _resolve_avatar_url(anima_name: str) -> str:
    """Resolve avatar URL for Slack icon_url.

    Delegates to :func:`core.tools._anima_icon_url.resolve_anima_icon_url`
    which applies the 3-tier resolution (per-Anima / env / config / channel / asset).
    """
    try:
        from core.tools._anima_icon_url import resolve_anima_icon_url

        return resolve_anima_icon_url(anima_name, channel_config=None)
    except Exception:
        return ""


def _resolve_bot_token(anima_name: str) -> str | None:
    """Resolve the per-Anima or shared Slack bot token."""
    per_anima_key = f"SLACK_BOT_TOKEN__{anima_name}"
    token = _lookup_vault_credential(per_anima_key)
    if token:
        return token
    token = _lookup_shared_credentials(per_anima_key)
    if token:
        return token
    token = os.environ.get(per_anima_key)
    if token:
        return token
    # Fallback to shared token
    token = _lookup_vault_credential("SLACK_BOT_TOKEN")
    if token:
        return token
    token = _lookup_shared_credentials("SLACK_BOT_TOKEN")
    if token:
        return token
    return os.environ.get("SLACK_BOT_TOKEN") or None


class SlackAutoResponder:
    """Post-cycle hook: auto-send LLM responses back to originating Slack channels."""

    async def on_inbox_response(
        self,
        anima_name: str,
        response_text: str,
        inbox_items: list[InboxItem],
        *,
        already_posted: set[str] | None = None,
    ) -> list[str]:
        """Post *response_text* to each Slack-sourced message's channel/thread.

        Args:
            anima_name: Name of the Anima that generated the response.
            response_text: The LLM's accumulated response text.
            inbox_items: The inbox items that were processed in this cycle.
            already_posted: Set of ``"channel_id:thread_ts"`` keys where the
                LLM already posted via tool calls (double-post prevention).

        Returns:
            List of Slack message ``ts`` values for successfully posted messages.
        """
        if not response_text or not response_text.strip():
            return []

        posted_keys = already_posted or set()
        slack_targets = self._collect_slack_targets(inbox_items, posted_keys)
        if not slack_targets:
            return []

        token = _resolve_bot_token(anima_name)
        if not token:
            logger.warning(
                "SlackAutoResponder: no bot token for anima '%s'; skipping",
                anima_name,
            )
            return []

        from core.tools._slack_markdown import md_to_slack_mrkdwn

        slack_text = md_to_slack_mrkdwn(response_text)[:_MAX_SLACK_TEXT]

        # Resolve icon URL from AVATAR_URL__{name} env/credentials
        icon_url = _resolve_avatar_url(anima_name)

        posted_ts: list[str] = []
        async with httpx.AsyncClient(timeout=_SLACK_TIMEOUT) as client:
            for target in slack_targets:
                ts = await self._post_one(
                    client,
                    token=token,
                    channel_id=target["channel_id"],
                    thread_ts=target["thread_ts"],
                    text=slack_text,
                    mention_prefix=target.get("mention_prefix", ""),
                    username=anima_name,
                    icon_url=icon_url,
                )
                if ts:
                    posted_ts.append(ts)

        if posted_ts:
            logger.info(
                "SlackAutoResponder: posted %d auto-response(s) for '%s'",
                len(posted_ts),
                anima_name,
            )
        return posted_ts

    @staticmethod
    def _collect_slack_targets(
        inbox_items: list[InboxItem],
        already_posted: set[str],
    ) -> list[dict[str, str]]:
        """Extract unique Slack targets, skipping already-posted ones."""
        seen: set[str] = set()
        targets: list[dict[str, str]] = []
        for item in inbox_items:
            msg = item.msg
            if getattr(msg, "source", "") != "slack":
                continue
            channel_id = getattr(msg, "external_channel_id", "")
            if not channel_id:
                continue
            thread_ts = getattr(msg, "external_thread_ts", "") or getattr(msg, "source_message_id", "")
            dedup_key = f"{channel_id}:{thread_ts}"
            if dedup_key in seen or dedup_key in already_posted:
                continue
            seen.add(dedup_key)

            mention = ""
            ext_uid = getattr(msg, "external_user_id", "")
            if ext_uid:
                mention = f"<@{ext_uid}> "

            targets.append(
                {
                    "channel_id": channel_id,
                    "thread_ts": thread_ts,
                    "mention_prefix": mention,
                }
            )
        return targets

    @staticmethod
    async def _post_one(
        client: httpx.AsyncClient,
        *,
        token: str,
        channel_id: str,
        thread_ts: str,
        text: str,
        mention_prefix: str = "",
        username: str = "",
        icon_url: str = "",
    ) -> str:
        """Post a single message. Return the ts or empty string on failure."""
        payload: dict[str, Any] = {
            "channel": channel_id,
            "text": f"{mention_prefix}{text}" if mention_prefix else text,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts
        if username:
            payload["username"] = username
        if icon_url:
            payload["icon_url"] = icon_url
        try:
            resp = await client.post(
                _SLACK_POST_URL,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                logger.error(
                    "SlackAutoResponder: chat.postMessage failed for %s: %s",
                    channel_id,
                    data.get("error", "unknown"),
                )
                return ""
            return data.get("ts", "")
        except Exception:
            logger.exception("SlackAutoResponder: failed to post to %s", channel_id)
            return ""


class DiscordAutoResponder:
    """Post-cycle hook: auto-send LLM responses back to originating Discord channels."""

    async def on_inbox_response(
        self,
        anima_name: str,
        response_text: str,
        inbox_items: list[InboxItem],
        *,
        already_posted: set[str] | None = None,
    ) -> list[str]:
        """Post *response_text* to each Discord-sourced message's channel via webhook.

        Returns list of Discord message IDs for successfully posted messages.
        """
        if not response_text or not response_text.strip():
            return []

        posted_keys = already_posted or set()
        targets = self._collect_discord_targets(inbox_items, posted_keys)
        if not targets:
            return []

        try:
            from core.discord_webhooks import get_webhook_manager

            wm = get_webhook_manager()
        except Exception:
            logger.warning("DiscordAutoResponder: webhook manager not available")
            return []

        from core.tools._discord_markdown import md_to_discord

        discord_text = md_to_discord(response_text)

        posted_ids: list[str] = []
        for target in targets:
            try:
                mention = target.get("mention_prefix", "")
                text = f"{mention}{discord_text}" if mention else discord_text
                thread_id = target.get("thread_id") or None
                logger.info(
                    "DiscordAutoResponder: posting for '%s' channel=%s thread=%s",
                    anima_name,
                    target["channel_id"],
                    thread_id or "(none)",
                )
                msg_id = wm.send_as_anima(
                    target["channel_id"],
                    anima_name,
                    text,
                    thread_id=thread_id,
                )
                if msg_id:
                    posted_ids.append(msg_id)
                    # Mirror to AnimaWorks board so thread conversations
                    # appear in the shared channel JSONL alongside the
                    # human messages routed by the gateway.
                    self._mirror_to_board(
                        target["channel_id"],
                        response_text,
                        anima_name,
                    )
            except Exception:
                logger.exception(
                    "DiscordAutoResponder: failed to post to %s",
                    target["channel_id"],
                )

        if posted_ids:
            logger.info(
                "DiscordAutoResponder: posted %d auto-response(s) for '%s'",
                len(posted_ids),
                anima_name,
            )
        return posted_ids

    @staticmethod
    def _mirror_to_board(
        channel_id: str,
        text: str,
        anima_name: str,
    ) -> None:
        """Write the auto-response to the AnimaWorks board mapped to *channel_id*.

        This ensures that Anima replies sent via Discord webhook also appear
        in the shared channel JSONL, matching how the gateway records
        inbound human messages.
        """
        try:
            from core.config.models import load_config
            from core.messenger import Messenger
            from core.paths import get_shared_dir

            board_mapping = load_config().external_messaging.discord.board_mapping
            board_name = board_mapping.get(channel_id)
            if not board_name:
                return
            # DM boards are per-Anima; skip to avoid noise
            if board_name.startswith("dm-"):
                return
            messenger = Messenger(get_shared_dir(), anima_name)
            messenger.post_channel(
                board_name,
                text,
                source="anima",
                from_name=anima_name,
            )
        except Exception:
            logger.debug(
                "DiscordAutoResponder: board mirror failed for channel %s",
                channel_id,
                exc_info=True,
            )

    @staticmethod
    def _collect_discord_targets(
        inbox_items: list[InboxItem],
        already_posted: set[str],
    ) -> list[dict[str, str]]:
        """Extract unique Discord targets from inbox items.

        ``external_channel_id`` = parent channel (webhook target).
        ``external_thread_ts``  = thread channel ID if threaded, else "".

        **DM channels** (``#dm-*``) are skipped when the inbox batch
        also contains non-Discord messages (internal Anima DMs, task
        results, etc.).  In a mixed batch the ``accumulated_text``
        contains responses to *all* messages, so posting it to a DM
        channel would leak Anima-to-Anima content into the human
        communication channel.  Pure-Discord batches are fine.
        """
        # Detect mixed batch: has non-discord items?
        _has_non_discord = any(getattr(item.msg, "source", "") != "discord" for item in inbox_items)

        # Load board_mapping once to identify DM channels
        _dm_channel_ids: set[str] = set()
        if _has_non_discord:
            try:
                from core.config.models import load_config

                for ch_id, board in load_config().external_messaging.discord.board_mapping.items():
                    if board.startswith("dm-"):
                        _dm_channel_ids.add(ch_id)
            except Exception:
                pass

        seen: set[str] = set()
        targets: list[dict[str, str]] = []
        for item in inbox_items:
            msg = item.msg
            if getattr(msg, "source", "") != "discord":
                continue
            channel_id = getattr(msg, "external_channel_id", "")
            if not channel_id:
                logger.warning(
                    "DiscordAutoResponder: inbox item from discord has no external_channel_id, from=%s",
                    getattr(msg, "from_name", "?"),
                )
                continue

            # Skip DM channels in mixed batches to prevent cross-talk
            if channel_id in _dm_channel_ids:
                logger.info(
                    "DiscordAutoResponder: skipping DM channel %s in mixed batch",
                    channel_id,
                )
                continue

            thread_id = getattr(msg, "external_thread_ts", "")
            dedup_key = f"{channel_id}:{thread_id}" if thread_id else channel_id
            logger.info(
                "DiscordAutoResponder: target channel_id=%s thread_id=%s from=%s dedup=%s",
                channel_id,
                thread_id or "(none)",
                getattr(msg, "from_name", "?"),
                dedup_key,
            )
            if dedup_key in seen or dedup_key in already_posted:
                continue
            seen.add(dedup_key)

            mention = ""
            ext_uid = getattr(msg, "external_user_id", "")
            if ext_uid:
                mention = f"<@{ext_uid}> "

            targets.append(
                {
                    "channel_id": channel_id,
                    "thread_id": thread_id,
                    "mention_prefix": mention,
                }
            )
        return targets


class BoardDiscordSync:
    """Sync AnimaWorks board posts back to mapped Discord channels."""

    def sync_board_post(
        self,
        board_name: str,
        text: str,
        from_person: str,
        *,
        source: str = "",
    ) -> str | None:
        """Post a board message to the mapped Discord channel.

        Returns the Discord message ID on success, or None.
        Skips messages that originated from Discord (echo prevention).
        """
        if source == "discord":
            return None

        # DM boards (dm-*) are handled by AutoResponder directly;
        # forwarding them here would create an infinite loop.
        if board_name.startswith("dm-"):
            return None

        from core.config.models import load_config

        cfg = load_config()
        discord_cfg = cfg.external_messaging.discord
        if not discord_cfg.enabled:
            return None

        # Reverse lookup: board_name -> discord_channel_id
        channel_id = None
        for ch_id, bname in discord_cfg.board_mapping.items():
            if bname == board_name:
                channel_id = ch_id
                break
        if not channel_id:
            return None

        try:
            from core.discord_webhooks import get_webhook_manager
            from core.tools._discord_markdown import md_to_discord

            wm = get_webhook_manager()
            discord_text = md_to_discord(text)
            msg_id = wm.send_as_anima(channel_id, from_person, discord_text)
            if msg_id:
                logger.info("BoardDiscordSync: synced '%s' -> %s", board_name, channel_id)
                return msg_id
            return None
        except Exception:
            logger.exception("BoardDiscordSync: failed to sync '%s'", board_name)
            return None


class BoardSlackSync:
    """Sync AnimaWorks board posts back to mapped Slack channels."""

    async def sync_board_post(
        self,
        board_name: str,
        text: str,
        from_person: str,
        *,
        source: str = "",
    ) -> str | None:
        """Post a board message to the mapped Slack channel.

        Returns the Slack message ts on success, or None.
        Skips messages that originated from Slack (echo prevention).
        """
        if source == "slack":
            return None

        from core.config.models import load_config

        cfg = load_config()
        slack_cfg = cfg.external_messaging.slack
        if not slack_cfg.enabled:
            return None

        # Reverse lookup: board_name -> slack_channel_id
        channel_id = None
        for ch_id, bname in slack_cfg.board_mapping.items():
            if bname == board_name:
                channel_id = ch_id
                break
        if not channel_id:
            return None

        token = _resolve_bot_token(from_person)
        if not token:
            logger.warning("BoardSlackSync: no token for board '%s' sync", board_name)
            return None

        from core.tools._slack_markdown import md_to_slack_mrkdwn

        slack_text = md_to_slack_mrkdwn(text)[:_MAX_SLACK_TEXT]
        icon_url = _resolve_avatar_url(from_person)
        payload: dict[str, Any] = {
            "channel": channel_id,
            "text": slack_text,
            "username": from_person,
        }
        if icon_url:
            payload["icon_url"] = icon_url

        try:
            async with httpx.AsyncClient(timeout=_SLACK_TIMEOUT) as client:
                resp = await client.post(
                    _SLACK_POST_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    logger.error(
                        "BoardSlackSync: failed for '%s' -> %s: %s",
                        board_name,
                        channel_id,
                        data.get("error", "unknown"),
                    )
                    return None
                logger.info("BoardSlackSync: synced '%s' -> %s", board_name, channel_id)
                return data.get("ts")
        except Exception:
            logger.exception("BoardSlackSync: failed to sync '%s'", board_name)
            return None
