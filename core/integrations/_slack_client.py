# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Slack Web API client with rate-limit retry and pagination."""

from __future__ import annotations

import re
from datetime import timedelta, timezone
from typing import Any

from core.integrations._async_compat import run_sync
from core.integrations._base import ToolConfigError, get_credential
from core.integrations._retry import retry_on_rate_limit

# ── Constants ──────────────────────────────────────────────

JST = timezone(timedelta(hours=9))
RATE_LIMIT_RETRY_MAX = 5
RATE_LIMIT_WAIT_DEFAULT = 30

WebClient: Any = None
SlackApiError: Any = None


def _require_slack_sdk():
    global WebClient, SlackApiError
    if WebClient is None:
        try:
            from slack_sdk import WebClient as _WC
            from slack_sdk.errors import SlackApiError as _SAE

            WebClient = _WC
            SlackApiError = _SAE
        except ImportError:
            raise ImportError(
                "slack tool requires 'slack-sdk'. Install with: pip install animaworks[communication]"
            ) from None
    return WebClient


# ── SlackClient ─────────────────────────────────────────────


class SlackClient:
    """Slack Web API wrapper with rate-limit retry and cursor pagination."""

    def __init__(self, token: str | None = None):
        _require_slack_sdk()
        if token is None:
            token = get_credential("slack", "slack", env_var="SLACK_BOT_TOKEN")
        self.client = WebClient(token=token)
        self.my_user_id: str | None = None
        self.my_name: str | None = None
        self._channel_cache: dict[str, dict] = {}  # channel_id -> {id, name, ...}
        self._user_cache: dict[str, str] = {}  # user_id -> display_name

    def _call(self, method_name: str, **kwargs):
        """Call a WebClient method with 429 rate-limit retry."""
        method = getattr(self.client, method_name)

        class _SlackRateLimitError(Exception):
            """Wrapper to distinguish rate-limit errors for retry."""

            def __init__(self, original: Exception, retry_after: int) -> None:
                self.original = original
                self.retry_after = retry_after
                super().__init__(str(original))

        def _do_call():
            try:
                return method(**kwargs)
            except SlackApiError as e:
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get("Retry-After", RATE_LIMIT_WAIT_DEFAULT))
                    raise _SlackRateLimitError(e, retry_after) from e
                raise

        def _get_retry_after(exc: Exception) -> float | None:
            if isinstance(exc, _SlackRateLimitError):
                return float(exc.retry_after)
            return None

        try:
            return retry_on_rate_limit(
                _do_call,
                max_retries=RATE_LIMIT_RETRY_MAX,
                default_wait=RATE_LIMIT_WAIT_DEFAULT,
                get_retry_after=_get_retry_after,
                retry_on=(_SlackRateLimitError,),
            )
        except _SlackRateLimitError as exc:
            raise exc.original from None

    async def _acall(self, method_name: str, **kwargs):
        """Async wrapper around :meth:`_call` using a thread-pool executor."""
        return await run_sync(self._call, method_name, **kwargs)

    def _paginate(self, method_name: str, response_key: str, **kwargs) -> list:
        """Cursor-based pagination. Returns all items."""
        all_items = []
        cursor = None
        while True:
            call_kwargs = dict(kwargs)
            if cursor:
                call_kwargs["cursor"] = cursor
            response = self._call(method_name, **call_kwargs)
            items = response.get(response_key, [])
            all_items.extend(items)
            # Check for next page
            metadata = response.get("response_metadata", {})
            next_cursor = metadata.get("next_cursor", "")
            if not next_cursor:
                break
            cursor = next_cursor
        return all_items

    def auth_test(self):
        """Get the bot's own info, setting my_user_id / my_name."""
        response = self._call("auth_test")
        self.my_user_id = response.get("user_id", "")
        self.my_name = response.get("user", "")
        return response

    def channels(self, exclude_archived: bool = True) -> list[dict]:
        """List joined channels (tries all types, skips on missing_scope)."""
        all_channels = []
        type_groups = [
            "public_channel",
            "private_channel",
            "im",
            "mpim",
        ]
        for ch_type in type_groups:
            try:
                chs = self._paginate(
                    "conversations_list",
                    "channels",
                    types=ch_type,
                    exclude_archived=exclude_archived,
                    limit=200,
                )
                all_channels.extend(chs)
            except SlackApiError as e:
                if "missing_scope" in str(e):
                    pass  # Scope not available, skip this type
                else:
                    raise
        # Cache channel info
        for ch in all_channels:
            self._channel_cache[ch["id"]] = ch
        return all_channels

    def channel_history(self, channel_id: str, limit: int = 100) -> list[dict]:
        """Get messages via conversations.history with pagination."""
        all_messages = []
        cursor = None
        remaining = limit
        while remaining > 0:
            fetch_count = min(remaining, 200)
            call_kwargs = {"channel": channel_id, "limit": fetch_count}
            if cursor:
                call_kwargs["cursor"] = cursor
            response = self._call("conversations_history", **call_kwargs)
            messages = response.get("messages", [])
            all_messages.extend(messages)
            remaining -= len(messages)
            if not messages:
                break
            metadata = response.get("response_metadata", {})
            next_cursor = metadata.get("next_cursor", "")
            if not next_cursor:
                break
            cursor = next_cursor
        return all_messages

    def thread_replies(self, channel_id: str, ts: str) -> list[dict]:
        """Get thread replies via conversations.replies."""
        all_replies = self._paginate(
            "conversations_replies",
            "messages",
            channel=channel_id,
            ts=ts,
            limit=200,
        )
        return all_replies

    def post_message(
        self,
        channel_id: str,
        text: str,
        thread_ts: str | None = None,
        *,
        username: str = "",
        icon_url: str = "",
    ) -> dict:
        """Send a message via chat.postMessage."""
        kwargs = {"channel": channel_id, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        if username:
            kwargs["username"] = username
        if icon_url:
            kwargs["icon_url"] = icon_url
        response = self._call("chat_postMessage", **kwargs)
        return response

    def update_message(self, channel_id: str, ts: str, text: str) -> dict:
        """Update an existing message via chat.update (silent, no notification)."""
        return self._call("chat_update", channel=channel_id, ts=ts, text=text)

    def pins_add(self, channel_id: str, ts: str) -> dict:
        """Pin a message in a channel via pins.add."""
        return self._call("pins_add", channel=channel_id, timestamp=ts)

    def add_reaction(self, channel_id: str, emoji: str, ts: str) -> dict:
        """Add an emoji reaction to a message via reactions.add."""
        return self._call(
            "reactions_add",
            channel=channel_id,
            name=emoji,
            timestamp=ts,
        )

    def users_list(self) -> list[dict]:
        """Get all workspace users."""
        all_users = self._paginate("users_list", "members", limit=200)
        # Cache display names
        for u in all_users:
            display = u.get("profile", {}).get("display_name", "") or u.get("real_name", "") or u.get("name", "")
            self._user_cache[u["id"]] = display
        return all_users

    def resolve_channel(self, name_or_id: str) -> str:
        """Resolve a channel name or ID to a channel_id.

        - C/D/G + alphanumeric is treated as an ID
        - Otherwise, search by name (exact match first, then partial)
        """
        # Looks like an ID
        if re.match(r"^[CDG][A-Z0-9]{8,}$", name_or_id):
            return name_or_id

        # Strip leading #
        name_or_id = name_or_id.lstrip("#")

        # Populate cache if empty
        if not self._channel_cache:
            self.channels()

        # Exact match first
        for ch_id, ch in self._channel_cache.items():
            ch_name = ch.get("name", "")
            if ch_name == name_or_id:
                return ch_id

        # Partial match
        matches = []
        for ch_id, ch in self._channel_cache.items():
            ch_name = ch.get("name", "")
            if name_or_id.lower() in ch_name.lower():
                matches.append((ch_id, ch))

        if len(matches) == 1:
            return matches[0][0]

        if len(matches) > 1:
            names = ", ".join(f"{cid} #{c.get('name', '?')}" for cid, c in matches)
            raise ToolConfigError(
                f"Multiple channels matched '{name_or_id}': {names}. Specify the channel ID directly."
            )

        raise ToolConfigError(f"Channel '{name_or_id}' not found")

    def resolve_user_name(self, user_id: str) -> str:
        """Resolve user_id to a display name. Fetches from API if not cached."""
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        # Fetch user info from API
        try:
            response = self._call("users_info", user=user_id)
            user = response.get("user", {})
            display = (
                user.get("profile", {}).get("display_name", "") or user.get("real_name", "") or user.get("name", "")
            )
            self._user_cache[user_id] = display
            return display
        except SlackApiError:
            self._user_cache[user_id] = user_id
            return user_id

    def get_channel_name(self, channel_id: str) -> str:
        """Get channel name from channel_id."""
        if channel_id in self._channel_cache:
            ch = self._channel_cache[channel_id]
            name = ch.get("name", "")
            if name:
                return name
            # DM: return other user's name
            if ch.get("is_im"):
                other_user = ch.get("user", "")
                if other_user:
                    return f"DM:{self.resolve_user_name(other_user)}"
            return channel_id

        # Not cached: fetch via conversations.info
        try:
            response = self._call("conversations_info", channel=channel_id)
            ch = response.get("channel", {})
            self._channel_cache[channel_id] = ch
            name = ch.get("name", "")
            if name:
                return name
            if ch.get("is_im"):
                other_user = ch.get("user", "")
                if other_user:
                    return f"DM:{self.resolve_user_name(other_user)}"
            return channel_id
        except SlackApiError:
            return channel_id
