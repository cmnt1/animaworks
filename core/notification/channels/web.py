from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Built-in Web UI notification channel.

Delivers ``call_human`` to the browser through the server's WebSocket
manager, so a fresh install can reach the user without any external
service. Works from any process (sandboxed MCP servers, anima runners,
the server itself) because it goes through the internal host API.
"""

import asyncio
import logging
from typing import Any

from core.notification.notifier import NotificationChannel, register_channel
from core.time_utils import now_iso

logger = logging.getLogger("animaworks.notification.web")

WEB_CHANNEL_TYPE = "web"


@register_channel(WEB_CHANNEL_TYPE)
class WebChannel(NotificationChannel):
    """Push the notification into the user's Web UI chat and toast."""

    @property
    def channel_type(self) -> str:
        return WEB_CHANNEL_TYPE

    async def send(
        self,
        subject: str,
        body: str,
        priority: str = "normal",
        *,
        anima_name: str = "",
        interaction: Any | None = None,
    ) -> str:
        payload = {
            "anima": anima_name,
            "subject": subject,
            "body": body,
            "priority": priority,
            "timestamp": now_iso(),
        }
        await asyncio.to_thread(_post_to_server, payload)
        return "web: OK"


def _post_to_server(payload: dict[str, Any]) -> None:
    import httpx

    from core.internal_api import host_api

    resp = host_api.post(
        "/api/internal/notify-web",
        json=payload,
        timeout=httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0),
    )
    resp.raise_for_status()
