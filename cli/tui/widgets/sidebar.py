# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Sidebar widget: list of animas + activity feed.

The widget is a thin view over :class:`cli.tui.state.AppState`. It has
no knowledge of the server; it just re-renders whatever state it is
given via :meth:`Sidebar.refresh`.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from cli.tui.state import AppState

_STATUS_COLORS = {
    "idle": "green",
    "running": "green",
    "busy": "yellow",
    "thinking": "yellow",
    "streaming": "yellow",
    "starting": "yellow",
    "bootstrapping": "yellow",
    "error": "red",
    "disconnected": "red",
}


class AnimaChosen(Message):
    """Posted when the user picks an anima from the sidebar."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class _AnimaRow(Static, can_focus=True):
    """A single, focusable row for one anima in the sidebar."""

    def __init__(self, name: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.anima_name = name

    def on_click(self) -> None:
        self.post_message(AnimaChosen(self.anima_name))

    def on_enter(self) -> None:
        self.post_message(AnimaChosen(self.anima_name))


class AnimaList(VerticalScroll):
    """The upper portion of the sidebar: one row per anima."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: dict[str, _AnimaRow] = {}
        self._current: str | None = None

    def refresh_animas(self, state: AppState) -> None:
        names = list(state.animas)
        rows_here = set(self._rows)
        for name in set(rows_here) - set(names):
            self._rows[name].remove()
            del self._rows[name]
        for name in names:
            row = self._rows.get(name)
            if row is None:
                row = _AnimaRow(name)
                self._rows[name] = row
                self.mount(row)
            self._update_row(row, state)

    def set_current(self, name: str | None) -> None:
        self._current = name
        for row_name, row in self._rows.items():
            row.set_class(row_name == name, "current")

    def _update_row(self, row: _AnimaRow, state: AppState) -> None:
        info = state.animas.get(row.anima_name)
        if info is None:
            return
        color = _STATUS_COLORS.get(info.status, "default")
        parts: list = []
        if info.busy or info.status in ("busy", "thinking", "streaming"):
            parts.append(Text("● ", style=color))
        else:
            parts.append(Text("○ ", style="dim"))
        parts.append(Text(row.anima_name, style="bold"))
        if info.unread:
            parts.append(Text(f" ({info.unread})", style="red bold"))
        if info.active_tool:
            parts.append(Text(f"  {info.active_tool}", style="dim"))
        row.update(Text.assemble(*parts))


class ActivityFeed(VerticalScroll):
    """The lower portion of the sidebar: rolling activity feed."""

    def update_state(self, state: AppState) -> None:
        self.remove_children()
        for entry in state.activity[-60:]:
            now = datetime.now().strftime("%H:%M")
            label = entry.anima or "?"
            text_parts: list = []
            if entry.kind == "board":
                text_parts.append(Text(f"{now} ", style="dim"))
                text_parts.append(Text(entry.text, style="bold"))
            elif entry.kind == "interaction":
                text_parts.append(Text(f"{now} ", style="dim"))
                text_parts.append(Text(entry.text, style="italic"))
            else:
                text_parts.append(Text(f"{now} {label} ", style="dim"))
                text_parts.append(Text(entry.kind, style="cyan"))
                if entry.text:
                    text_parts.append(Text(f" {entry.text}", style="dim"))
            line = Static(Text.assemble(*text_parts))
            line.styles.height = "auto"
            line.styles.width = "100%"
            self.mount(line)


class Sidebar(Vertical):
    """The full sidebar: anima list on top, activity feed below."""

    BINDINGS = [
        Binding("enter", "choose", "Choose selected anima", show=False),
    ]

    DEFAULT_CSS = """
    Sidebar {
        width: 32;
        height: 1fr;
        background: $panel;
        border-right: round $primary;
        padding: 0 1;
    }
    Sidebar > .sidebar-header {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    AnimaList {
        height: 1fr;
        width: 100%;
    }
    ActivityFeed {
        height: 1fr;
        width: 100%;
        border-top: round $primary;
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.animas = AnimaList()
        self.feed = ActivityFeed()

    def compose(self):
        yield Static("ANIMAS", classes="sidebar-header")
        yield self.animas
        yield Static("ACTIVITY", classes="sidebar-header")
        yield self.feed

    def update_state(self, state: AppState) -> None:
        self.animas.refresh_animas(state)
        self.animas.set_current(state.current)
        self.feed.update_state(state)

    def action_choose(self) -> None:
        focused = self.focused
        if isinstance(focused, _AnimaRow):
            self.post_message(AnimaChosen(focused.anima_name))
