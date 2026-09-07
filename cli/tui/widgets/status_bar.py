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
        self.skill_count = 0
        self.model: str | None = None
        self.context_usage_ratio: float | None = None
        self.context_input_tokens: int | None = None
        self.context_window: int | None = None

    def set_anima(self, anima_name: str, thread_id: str | None = None) -> None:
        self.anima_name = anima_name
        if thread_id is not None:
            self.thread_id = thread_id
        self.refresh()

    def set_state(
        self,
        *,
        status: str | None = None,
        active_tool: str | None = None,
        connected: bool | None = None,
        right_hint: str | None = None,
        skill_count: int | None = None,
    ) -> None:
        if status is not None:
            self.status = status
        if active_tool is not None:
            self.active_tool = active_tool or None
        if connected is not None:
            self.connected = connected
        if right_hint is not None:
            self.right_hint = right_hint
        if skill_count is not None:
            self.skill_count = skill_count
        self.refresh()

    def set_model(self, model: str | None) -> None:
        """Set the model to show (``None`` leaves it untouched, "" clears it)."""
        self.model = model or None
        self.refresh()

    def set_context_usage(
        self,
        ratio: float | int | str | None,
        *,
        input_tokens: int | str | None = None,
        context_window: int | str | None = None,
    ) -> None:
        """Persist the current conversation's context position."""
        self.context_usage_ratio = None if ratio is None else min(max(float(ratio), 0.0), 1.0)
        self.context_input_tokens = int(input_tokens) if input_tokens else None
        self.context_window = int(context_window) if context_window else None
        self.refresh()

    def render(self) -> Text:
        parts = [
            Text(self.anima_name),
            Text(" "),
            # The status word follows the dot, so no colour is needed.
            Text("●", style="bold"),
            Text(f" {self.status}"),
        ]

        if self.active_tool:
            parts.append(Text(f" | {self.active_tool}", style="bold"))

        if self.skill_count:
            parts.append(Text(f" | skills:{self.skill_count}", style="dim"))

        if self.context_usage_ratio is not None:
            percent = round(self.context_usage_ratio * 100)
            parts.append(Text(f" | ctx:{percent}%", style="dim"))

        parts.append(
            Text(
                f" | ws: {'connected' if self.connected else 'disconnected'}",
                style="dim",
            )
        )
        parts.append(Text(f" | thread:{self.thread_id}", style="dim"))

        if self.model:
            shown = self.model if len(self.model) <= 40 else self.model[:39] + "…"
            parts.append(Text(f" | model:{shown}", style="dim"))

        line = Text.assemble(*parts)
        if self.right_hint:
            line.append_text(Text(f"  {self.right_hint}", style="dim"))
        return line
