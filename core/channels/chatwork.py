"""Central Chatwork message send client."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

CHATWORK_API_BASE = "https://api.chatwork.com/v2"
CHATWORK_MESSAGE_URL = f"{CHATWORK_API_BASE}/rooms/{{room_id}}/messages"
DEFAULT_TIMEOUT = 30.0
MAX_MESSAGE_LENGTH = 10_000


def post_message_sync(post: Callable[..., Any], room_id: str, body: str) -> Any:
    """Send a Chatwork message using an existing synchronous API client."""
    if len(body) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Message exceeds 10,000 characters ({len(body)} chars)")
    return post(f"/rooms/{room_id}/messages", data={"body": body})


async def post_message(token: str, room_id: str, body: str) -> httpx.Response:
    """Post a Chatwork message asynchronously using the channel's shared wire contract."""
    url = CHATWORK_MESSAGE_URL.format(room_id=room_id)
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.post(
            url,
            headers={"X-ChatWorkToken": token},
            data={"body": body},
        )
        response.raise_for_status()
        return response
