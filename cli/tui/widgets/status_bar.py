# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from rich.text import Text
from textual.widget import Widget


class StatusBar(Widget):
    """A single status line showing anima, state, tool, connection, thread."""

    def __init__(
        self,
        anima_name: str,
        thread_id: str,
        *,
        initial_status: str = "starting",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.anima_name = anima_name
        self.thread_id = thread_id
        self.status = initial_status
        self.active_tool: str | None = None
        self.connected = False
        self.right_hint = "Esc: interrupt"

    def set_state(
        self,
        *,
        status: str | None = None,
        active_tool: str | None = None,
        connected: bool | None = None,
        right_hint: str | None = None,
    ) -> None:
        if status is not None:
            self.status = status
        if active_tool is not None:
            self.active_tool = active_tool or None
        if connected is not None:
            self.connected = connected
        if right_hint is not None:
            self.right_hint = right_hint
        self.refresh()

    def render(self) -> Text:
        status_color = {
            "idle": "green",
            "starting": "yellow",
            "thinking": "yellow",
            "streaming": "yellow",
            "error": "red",
            "disconnected": "red",
        }.get(self.status, "default")

        parts = [
            Text(self.anima_name),
            Text(" "),
            Text("●", style=status_color),
            Text(f" {self.status}"),
        ]

        if self.active_tool:
            parts.append(Text(f" | {self.active_tool}", style="bold"))

        parts.append(
            Text(
                f" | ws: {'connected' if self.connected else 'disconnected'}",
                style="dim",
            )
        )
        parts.append(Text(f" | thread:{self.thread_id}", style="dim"))

        line = Text.assemble(*parts)
        if self.right_hint:
            line.append_text(Text(f"  {self.right_hint}", style="dim"))
        return line
