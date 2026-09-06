# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical
from textual.widgets import Static


class ThinkingBlock(Vertical):
    """A block showing ``thinking`` deltas in dim style.

    The body always buffers whatever is streamed. Whether it is shown is
    controlled via :meth:`set_visible`, which just toggles the block's
    ``display`` (show/hide) — content is never discarded.
    """

    DEFAULT_CSS = """
    ThinkingBlock {
        height: auto;
        width: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._body = ""
        self.header = Static("", classes="thinking-header")
        self.body = Static("", classes="thinking-body")

    def compose(self):
        yield self.header
        yield self.body

    def _refresh(self) -> None:
        self.header.update(Text("▸ thinking ", style="dim bold"))
        self.body.update(Text(self._body, style="dim"))

    def add_delta(self, text: str) -> None:
        self._body += text
        self._refresh()

    def set_visible(self, visible: bool) -> None:
        self.display = visible
        self._refresh()
