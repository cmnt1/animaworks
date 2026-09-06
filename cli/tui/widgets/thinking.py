# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static


class ThinkingBlock(Vertical):
    """A collapsible block showing ``thinking`` deltas in dim style.

    Collapsed by default. The body accumulates ``thinking_delta`` text
    and can be toggled via :meth:`toggle` or :meth:`set_visible`.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._body = ""
        self.expanded = False
        self.header = Static("", classes="thinking-header")
        self.body = Static("", classes="thinking-body")

    def compose(self):
        yield self.header
        yield self.body

    def _render(self) -> None:
        marker = "▾" if self.expanded else "▸"
        self.header.update(Text(f"{marker} thinking ", style="dim bold"))
        self.body.update(Text(self._body, style="dim"))

    def add_delta(self, text: str) -> None:
        self._body += text
        self._render()

    def set_visible(self, visible: bool) -> None:
        self.expanded = visible
        self.body.display = visible
        self._render()

    def toggle(self) -> None:
        self.set_visible(not self.expanded)
