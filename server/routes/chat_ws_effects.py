from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from typing import Any

from server.events import emit_direct, emit_notification_direct


async def _emit_ws_side_effects(
    chunk: dict[str, Any],
    ws_manager: Any,
    anima_name: str,
    thread_id: str = "default",
) -> None:
    """Fire WebSocket side effects for an IPC chunk (no request dependency).

    Handles bootstrap status broadcasts and notification forwarding
    that need to work even when the SSE client is disconnected.
    """
    event_type = chunk.get("type")
    if event_type == "bootstrap_start" and ws_manager:
        await emit_direct(
            ws_manager,
            "anima.bootstrap",
            {"name": anima_name, "status": "started"},
        )
    elif event_type == "bootstrap_complete" and ws_manager:
        await emit_direct(
            ws_manager,
            "anima.bootstrap",
            {"name": anima_name, "status": "completed"},
        )
    elif event_type == "notification_sent" and ws_manager:
        await emit_notification_direct(
            ws_manager,
            chunk.get("data", {}),
        )
    elif event_type in ("tool_start", "tool_end", "tool_detail") and ws_manager:
        ws_payload: dict[str, Any] = {
            "name": anima_name,
            "event": event_type,
            "tool_name": chunk.get("tool_name", ""),
            "tool_id": chunk.get("tool_id", ""),
            "thread_id": thread_id,
        }
        if event_type == "tool_detail":
            ws_payload["detail"] = chunk.get("detail", "")
        elif event_type == "tool_end":
            record = chunk.get("record")
            if isinstance(record, dict):
                if record.get("is_error"):
                    ws_payload["is_error"] = True
        await emit_direct(ws_manager, "anima.tool_activity", ws_payload)
