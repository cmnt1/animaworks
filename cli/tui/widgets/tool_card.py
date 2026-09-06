# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static


class ToolCard(Vertical):
    """A one-line tool card, expandable to show detail.

    Shows ``▸ Name … ✓`` on success or ``✗ error`` on failure. Details
    streamed via ``tool_detail`` can be expanded by toggling.
    """

    DEFAULT_CSS = """
    ToolCard {
        height: auto;
        width: 100%;
    }
    """

    def __init__(self, tool_name: str, tool_id: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.tool_id = tool_id
        self._detail = ""
        self._result_summary: str | None = None
        self._is_error = False
        self._finished = False
        self.expanded = False
        self.header = Static("", classes="tool-header")
        self.detail = Static("", classes="tool-detail")

    def compose(self):
        yield self.header
        yield self.detail

    def add_detail(self, text: str) -> None:
        if not self.expanded:
            return
        self._detail += text
        self.detail.update(Text(self._detail, style="dim"))

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self.detail.display = self.expanded
        if self.expanded:
            self.detail.update(Text(self._detail, style="dim"))
        self._refresh()

    def finish(self, result_summary: str | None = None, is_error: bool = False) -> None:
        self._finished = True
        self._is_error = self._is_error or is_error
        self._result_summary = result_summary or self._result_summary
        self._refresh()

    def _refresh(self) -> None:
        if self._is_error:
            marker = Text("✗", style="red bold")
            tail = " error"
        elif self._finished:
            marker = Text("✓", style="green bold")
            tail = f"  {self._result_summary}" if self._result_summary else ""
        else:
            marker = Text("…", style="yellow bold")
            tail = ""

        line = Text.assemble(
            Text("▸ "),
            Text(self.tool_name, style="bold"),
            Text("  "),
            marker,
            Text(tail, style="dim"),
        )
        self.header.update(line)
