"""Backward-compatible Discord client import path.

The transport and REST client now live in :mod:`core.channels.discord` so
message sends and webhook calls share the channel client. This adapter keeps
the historical optional-token behavior for integrations and tools.
"""

from __future__ import annotations

import httpx  # Kept for compatibility with callers/tests patching this module's HTTP client.

from core.channels.discord import (
    _CHANNEL_TYPE_ANNOUNCEMENT,
    _CHANNEL_TYPE_TEXT,
    _DEFAULT_TIMEOUT,
    API_BASE,
    DISCORD_MESSAGE_LIMIT,
    RATE_LIMIT_RETRY_MAX,
    DiscordAPIError,
    _DiscordRateLimitError,
)
from core.channels.discord import (
    DiscordClient as _DiscordClient,
)
from core.integrations._base import get_credential

__all__ = [
    "API_BASE",
    "DISCORD_MESSAGE_LIMIT",
    "RATE_LIMIT_RETRY_MAX",
    "DiscordAPIError",
    "DiscordClient",
    "httpx",
    "_CHANNEL_TYPE_ANNOUNCEMENT",
    "_CHANNEL_TYPE_TEXT",
    "_DEFAULT_TIMEOUT",
    "_DiscordRateLimitError",
]


class DiscordClient(_DiscordClient):
    """Compatibility adapter resolving the shared token when omitted."""

    def __init__(self, token: str | None = None) -> None:
        if token is None:
            token = get_credential("discord", "discord", env_var="DISCORD_BOT_TOKEN")
        super().__init__(token)
