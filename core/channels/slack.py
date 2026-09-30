"""Central Slack Web API and incoming-webhook send client."""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Any

import httpx

SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
DEFAULT_TIMEOUT = 30.0


def post_sdk_message(
    api_call: Callable[..., dict],
    channel_id: str,
    text: str,
    thread_ts: str | None = None,
    *,
    username: str = "",
    icon_url: str = "",
) -> dict:
    """Send ``chat.postMessage`` through a configured Slack SDK call function."""
    payload: dict[str, Any] = {"channel": channel_id, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    if username:
        payload["username"] = username
    if icon_url:
        payload["icon_url"] = icon_url
    return api_call("chat_postMessage", **payload)


class SlackHTTPClient:
    """Async Slack send client shared by notifications and automatic replies."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout
        self._context: Any = None
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> SlackHTTPClient:
        self._context = httpx.AsyncClient(timeout=self._timeout)
        self._client = await self._context.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._context is not None:
            await self._context.__aexit__(exc_type, exc, traceback)
            self._context = None
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("SlackHTTPClient must be used as an async context manager")
        return self._client

    async def post_message(self, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Post a JSON payload to Slack's Bot Token API."""
        response = await self._get_client().post(
            SLACK_POST_MESSAGE_URL,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def post_webhook(self, webhook_url: str, payload: dict[str, Any]) -> None:
        """Post a JSON payload to a Slack Incoming Webhook URL."""
        response = await self._get_client().post(webhook_url, json=payload)
        response.raise_for_status()


async def post_message(
    token: str,
    payload: dict[str, Any],
    request_timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Open a short-lived client and post through Slack's Bot Token API."""
    async with SlackHTTPClient(timeout=request_timeout) as client:
        return await client.post_message(token, payload)


async def post_webhook(
    webhook_url: str,
    payload: dict[str, Any],
    request_timeout: float = DEFAULT_TIMEOUT,
) -> None:
    """Open a short-lived client and post through an Incoming Webhook URL."""
    async with SlackHTTPClient(timeout=request_timeout) as client:
        await client.post_webhook(webhook_url, payload)
