# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import websockets

from cli.tui.sse import SseEvent, aiter_sse

logger = logging.getLogger(__name__)

_MAX_RECONNECT_DELAY = 30.0
_INITIAL_RECONNECT_DELAY = 1.0


class AnimaWorksClientError(Exception):
    """Raised when a client request fails (connection, HTTP, parse error)."""


def _ws_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.startswith("https"):
        return "wss://" + normalized[len("https://") :] + "/ws"
    if normalized.startswith("http"):
        return "ws://" + normalized[len("http://") :] + "/ws"
    return normalized + "/ws"


def parse_ws_message(message: Any) -> tuple[str, dict[str, Any], bool]:
    """Parse a raw websocket message into ``(type, payload, should_pong)``.

    Pure function (no I/O) so it can be unit tested directly.

    - Handles ``str`` / ``bytes`` / already-parsed ``dict`` inputs.
    - Normalises the ``type`` / ``event`` keys into a single ``type``.
    - Returns ``should_pong=True`` for ``ping`` messages.
    """
    if isinstance(message, (str, bytes, bytearray)):
        try:
            if isinstance(message, (bytes, bytearray)):
                raw = message.decode("utf-8")
            else:
                raw = message
            parsed: Any = json.loads(raw)
        except Exception:
            return "_ws_status", {"handled": False}, False
    else:
        parsed = message

    if not isinstance(parsed, dict):
        return "_ws_status", {"handled": False}, False

    event_type = parsed.get("type") or parsed.get("event")
    if not event_type:
        return "_ws_status", {"handled": False}, False

    if event_type == "ping":
        payload = {k: v for k, v in parsed.items() if k not in ("type", "event")}
        return "ping", payload, True

    payload = parsed.get("data")
    if not isinstance(payload, dict):
        payload = {k: v for k, v in parsed.items() if k not in ("type", "event")}
    return event_type, payload, False


class AnimaWorksClient:
    """Thin HTTP / SSE / WebSocket client for the AnimaWorks gateway.

    Does not depend on Textual so it can be unit tested in isolation.
    """

    def __init__(
        self,
        base_url: str,
        *,
        from_person: str = "human",
        timeout: float | None = None,
        transport: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.from_person = from_person
        self.timeout = timeout
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def list_animas(self) -> list[dict]:
        resp = await self._get(f"{self.base_url}/api/animas")
        return resp

    async def get_history(
        self,
        anima: str,
        *,
        thread_id: str = "default",
        limit: int = 50,
    ) -> dict:
        resp = await self._get(
            f"{self.base_url}/api/animas/{anima}/conversation/history",
            params={"limit": limit, "thread_id": thread_id},
        )
        return resp

    async def chat_stream(
        self,
        anima: str,
        message: str,
        *,
        thread_id: str = "default",
        resume: str | None = None,
        last_event_id: str | None = None,
    ) -> AsyncIterator[SseEvent]:
        payload = {
            "message": message,
            "from_person": self.from_person,
            "intent": "",
            "images": [],
            "thread_id": thread_id,
            "model": None,
            "resume": resume,
            "last_event_id": last_event_id,
        }
        try:
            async with self._http.stream(
                "POST",
                f"{self.base_url}/api/animas/{anima}/chat/stream",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for event in aiter_sse(resp):
                    yield event
        except httpx.HTTPError as exc:
            raise AnimaWorksClientError(str(exc)) from exc

    async def interrupt(self, anima: str, *, thread_id: str) -> dict:
        resp = await self._http.post(
            f"{self.base_url}/api/animas/{anima}/interrupt",
            params={"thread_id": thread_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def ws_events(self) -> AsyncIterator[dict]:
        """Yield normalized websocket events, reconnecting with backoff.

        Each yielded dict is ``{"type": <str>, "data": <dict>}``.
        Connection state changes are yielded as ``_ws_status`` events.
        ``ping`` messages are answered with ``pong`` automatically.
        """
        url = _ws_url(self.base_url)
        delay = _INITIAL_RECONNECT_DELAY
        while True:
            try:
                async with websockets.connect(url) as ws:
                    delay = _INITIAL_RECONNECT_DELAY
                    yield {"type": "_ws_status", "data": {"connected": True}}
                    async for raw in ws:
                        event_type, payload, should_pong = parse_ws_message(raw)
                        if should_pong:
                            try:
                                await ws.send(json.dumps({"type": "pong"}))
                            except Exception:
                                logger.debug("Failed to send pong", exc_info=True)
                        yield {"type": event_type, "data": payload}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("WebSocket disconnected (%s); reconnecting in %.1fs", exc, delay)
                yield {"type": "_ws_status", "data": {"connected": False}}
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_RECONNECT_DELAY)

    async def _get(self, url: str, params: dict | None = None) -> Any:
        try:
            resp = await self._http.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise AnimaWorksClientError(str(exc)) from exc
