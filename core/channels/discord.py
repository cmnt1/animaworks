"""Central Discord REST API v10 client for channel messaging."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx

from core.exceptions import ToolConfigError

logger = logging.getLogger(__name__)

API_BASE = "https://discord.com/api/v10"
RATE_LIMIT_RETRY_MAX = 5
DISCORD_MESSAGE_LIMIT = 2000
_DEFAULT_TIMEOUT = 30.0

_CHANNEL_TYPE_TEXT = 0
_CHANNEL_TYPE_ANNOUNCEMENT = 5


class DiscordAPIError(Exception):
    """Raised when the Discord API returns a non-success HTTP status."""

    def __init__(self, status: int, message: str, code: int | None = None) -> None:
        self.status = status
        self.code = code
        super().__init__(f"Discord API error {status}: {message}")


class _DiscordRateLimitError(Exception):
    """Internal wrapper for 429 responses so the request can be retried."""

    def __init__(self, api_error: DiscordAPIError, retry_after: float) -> None:
        self.api_error = api_error
        self.retry_after = retry_after
        super().__init__(str(api_error))


async def post_webhook(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    params: dict[str, str] | None = None,
    request_timeout: float = _DEFAULT_TIMEOUT,
) -> Any:
    """Post a message to a Discord webhook URL without a bot auth header."""
    async with httpx.AsyncClient(timeout=request_timeout) as client:
        response = await client.post(webhook_url, json=payload, params=params)
        response.raise_for_status()
        return response.json()


def _retry_on_rate_limit(fn: Callable[[], Any], default_wait: float = 1.0) -> Any:
    """Retry a Discord request on 429, honoring the response retry delay."""
    for attempt in range(RATE_LIMIT_RETRY_MAX + 1):
        try:
            return fn()
        except _DiscordRateLimitError as exc:
            if attempt >= RATE_LIMIT_RETRY_MAX:
                raise
            wait = exc.retry_after if exc.retry_after is not None else default_wait
            logger.warning(
                "Rate limited – retry %d/%d after %.0fs: %s",
                attempt + 1,
                RATE_LIMIT_RETRY_MAX,
                wait,
                exc,
            )
            time.sleep(wait)
    raise RuntimeError("Rate limit retry exhausted")  # pragma: no cover


class DiscordClient:
    """Synchronous Discord REST API v10 client using ``httpx``."""

    def __init__(self, token: str) -> None:
        self._token = token
        self._http: httpx.Client | None = None
        self._channel_name_cache: dict[str, dict[str, str]] = {}

    def _ensure_http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(
                base_url=API_BASE,
                headers={"Authorization": f"Bot {self._token}"},
                timeout=_DEFAULT_TIMEOUT,
            )
        return self._http

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http is not None:
            self._http.close()
            self._http = None

    def _parse_error_response(self, response: httpx.Response) -> tuple[str, int | None]:
        """Extract message and optional numeric code from a Discord error body."""
        code: int | None = None
        message = response.text
        try:
            data = response.json()
            if isinstance(data, dict):
                message = str(data.get("message", message))
                raw_code = data.get("code")
                if isinstance(raw_code, int):
                    code = raw_code
        except (json.JSONDecodeError, TypeError):
            pass
        return message, code

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform an HTTP request with 429 rate-limit retry."""

        def _do() -> Any:
            client = self._ensure_http()
            try:
                response = client.request(method, path, **kwargs)
            except httpx.TimeoutException as exc:
                raise DiscordAPIError(0, f"Request timeout: {exc}") from exc
            except httpx.ConnectError as exc:
                raise DiscordAPIError(0, f"Connection failed: {exc}") from exc
            if response.status_code == 429:
                message, code = self._parse_error_response(response)
                retry_after = 1.0
                try:
                    data = response.json()
                    if isinstance(data, dict) and "retry_after" in data:
                        retry_after = float(data["retry_after"])
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
                api_err = DiscordAPIError(429, message, code=code)
                raise _DiscordRateLimitError(api_err, retry_after) from None
            if response.status_code < 200 or response.status_code >= 300:
                message, code = self._parse_error_response(response)
                raise DiscordAPIError(response.status_code, message, code=code)
            if not response.content:
                return {}
            try:
                return response.json()
            except json.JSONDecodeError:
                return {}

        try:
            return _retry_on_rate_limit(_do, default_wait=1.0)
        except _DiscordRateLimitError as exc:
            raise exc.api_error from None

    def guilds(self) -> list[dict]:
        """GET /users/@me/guilds — guilds the bot is in."""
        result = self._request("GET", "/users/@me/guilds")
        return result if isinstance(result, list) else []

    def channels(self, guild_id: str) -> list[dict]:
        """GET /guilds/{guild_id}/channels — text and announcement channels only."""
        result = self._request("GET", f"/guilds/{guild_id}/channels")
        if not isinstance(result, list):
            return []
        return [
            channel for channel in result if channel.get("type") in (_CHANNEL_TYPE_TEXT, _CHANNEL_TYPE_ANNOUNCEMENT)
        ]

    def channel_history(self, channel_id: str, limit: int = 50) -> list[dict]:
        """GET /channels/{channel_id}/messages with ``limit``."""
        result = self._request(
            "GET",
            f"/channels/{channel_id}/messages",
            params={"limit": min(limit, 100)},
        )
        return result if isinstance(result, list) else []

    def send_message(
        self,
        channel_id: str,
        content: str,
        *,
        reply_to: str | None = None,
        components: list[dict[str, Any]] | None = None,
    ) -> dict:
        """POST /channels/{channel_id}/messages with optional reply reference."""
        body: dict[str, Any] = {"content": content}
        if reply_to:
            body["message_reference"] = {
                "message_id": reply_to,
                "channel_id": channel_id,
            }
        if components:
            body["components"] = components
        result = self._request("POST", f"/channels/{channel_id}/messages", json=body)
        return result if isinstance(result, dict) else {}

    def edit_message(self, channel_id: str, message_id: str, content: str) -> dict:
        """PATCH /channels/{channel_id}/messages/{message_id}."""
        result = self._request(
            "PATCH",
            f"/channels/{channel_id}/messages/{message_id}",
            json={"content": content},
        )
        return result if isinstance(result, dict) else {}

    def add_reaction(self, channel_id: str, message_id: str, emoji: str) -> None:
        """PUT /channels/.../reactions/{emoji}/@me (emoji URL-encoded)."""
        encoded = quote(emoji, safe="")
        self._request(
            "PUT",
            f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me",
        )

    def get_message(self, channel_id: str, message_id: str) -> dict:
        """GET a single message."""
        result = self._request("GET", f"/channels/{channel_id}/messages/{message_id}")
        return result if isinstance(result, dict) else {}

    def resolve_channel(self, guild_id: str, name_or_id: str) -> str:
        """Resolve ``#name`` or numeric channel ID to a Discord channel ID."""
        raw = name_or_id.strip()
        if re.fullmatch(r"\d{17,22}", raw):
            return raw

        key = name_or_id.lstrip("#").strip()
        cache = self._channel_name_cache.get(guild_id)
        if cache is None:
            cache = {}
            for channel in self.channels(guild_id):
                channel_id = str(channel.get("id", ""))
                name = str(channel.get("name", ""))
                if channel_id:
                    cache[name.lower()] = channel_id
            self._channel_name_cache[guild_id] = cache

        if key.lower() in cache:
            return cache[key.lower()]

        partial = [(name, channel_id) for name, channel_id in cache.items() if key.lower() in name]
        if len(partial) == 1:
            return partial[0][1]
        if len(partial) > 1:
            names = ", ".join(f"#{name}" for name, _ in partial)
            raise ToolConfigError(f"Multiple Discord channels matched '{name_or_id}': {names}. Use the channel ID.")

        raise ToolConfigError(f"Discord channel '{name_or_id}' not found in guild {guild_id}")

    def list_webhooks(self, channel_id: str) -> list[dict]:
        """GET /channels/{channel_id}/webhooks — list channel webhooks."""
        result = self._request("GET", f"/channels/{channel_id}/webhooks")
        return result if isinstance(result, list) else []

    def create_webhook(self, channel_id: str, name: str = "AnimaWorks") -> dict:
        """POST /channels/{channel_id}/webhooks — create a webhook."""
        result = self._request(
            "POST",
            f"/channels/{channel_id}/webhooks",
            json={"name": name},
        )
        return result if isinstance(result, dict) else {}

    def execute_webhook(
        self,
        webhook_id: str,
        webhook_token: str,
        content: str | None = None,
        *,
        username: str | None = None,
        avatar_url: str | None = None,
        thread_id: str | None = None,
        components: list[dict[str, Any]] | None = None,
    ) -> dict:
        """POST /webhooks/{id}/{token} — execute a webhook."""
        body: dict[str, Any] = {}
        if content is not None:
            body["content"] = content[:DISCORD_MESSAGE_LIMIT]
        if username:
            body["username"] = username
        if avatar_url:
            body["avatar_url"] = avatar_url
        if components:
            body["components"] = components
        if "content" not in body and "components" not in body:
            body["content"] = ""
        params: dict[str, str] = {"wait": "true"}
        if thread_id:
            params["thread_id"] = thread_id

        client = self._ensure_http()
        try:
            response = client.request(
                "POST",
                f"/webhooks/{webhook_id}/{webhook_token}",
                json=body,
                params=params,
            )
            if response.status_code == 429:
                _message, code = self._parse_error_response(response)
                retry_after = 1.0
                try:
                    data = response.json()
                    if isinstance(data, dict) and "retry_after" in data:
                        retry_after = float(data["retry_after"])
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
                raise DiscordAPIError(429, f"Rate limited ({retry_after}s)", code=code)
            if response.status_code < 200 or response.status_code >= 300:
                message, code = self._parse_error_response(response)
                raise DiscordAPIError(response.status_code, message, code=code)
            if not response.content:
                return {}
            return response.json()
        except httpx.TimeoutException as exc:
            raise DiscordAPIError(0, f"Webhook timeout: {exc}") from exc

    def create_dm(self, user_id: str) -> dict:
        """POST /users/@me/channels — open a DM channel with a user."""
        result = self._request(
            "POST",
            "/users/@me/channels",
            json={"recipient_id": user_id},
        )
        return result if isinstance(result, dict) else {}

    _CHANNEL_TYPE_CATEGORY = 4

    def create_channel(
        self,
        guild_id: str,
        name: str,
        *,
        channel_type: int = 0,
        parent_id: str | None = None,
    ) -> dict:
        """POST /guilds/{guild_id}/channels — create a guild channel."""
        body: dict[str, Any] = {"name": name, "type": channel_type}
        if parent_id:
            body["parent_id"] = parent_id
        result = self._request("POST", f"/guilds/{guild_id}/channels", json=body)
        return result if isinstance(result, dict) else {}

    def get_guild_channels(self, guild_id: str) -> list[dict]:
        """GET /guilds/{guild_id}/channels — all channels (including categories)."""
        result = self._request("GET", f"/guilds/{guild_id}/channels")
        return result if isinstance(result, list) else []
