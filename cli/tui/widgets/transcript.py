# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re

from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static

from cli.tui.widgets.thinking import ThinkingBlock
from cli.tui.widgets.tool_card import ToolCard

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->")


def _strip_html_comments(text: str) -> str:
    """Remove complete HTML comments and any trailing unclosed one."""
    text = _HTML_COMMENT_RE.sub("", text)
    # Remove a trailing unclosed comment opener (e.g. `<!-- emotion: {...}`)
    idx = text.find("<!--")
    if idx != -1:
        text = text[:idx]
    return text


def strip_html_comments(text: str) -> str:
    """Public helper to strip HTML comments from display text."""
    return _strip_html_comments(text)


class HumanTurn(Vertical):
    """A single user message in the transcript."""

    DEFAULT_CSS = """
    HumanTurn {
        height: auto;
        width: 100%;
    }
    """

    def __init__(self, label: str, text: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._text = text
        self.label_widget = Static("", classes="human-label")
        self.message = Static("", classes="human-message")

    def compose(self):
        yield self.label_widget
        yield self.message

    def on_mount(self) -> None:
        self.label_widget.update(Text(f"{self._label}:", style="bold cyan"))
        self.message.update(self._text)


class AssistantBlock(Vertical):
    """Container for a single assistant response.

    Holds an accumulating text body plus optional thinking block and tool
    cards.
    """

    DEFAULT_CSS = """
    AssistantBlock {
        height: auto;
        width: 100%;
    }
    AssistantBlock > .tools {
        height: auto;
        width: 100%;
    }
    """

    def __init__(self, label: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._body = ""
        self.text = Static("", classes="assistant-text")
        self.thinking: ThinkingBlock | None = None
        self.tools = Vertical(classes="tools")

    def compose(self):
        yield self.text
        if self.thinking is not None:
            yield self.thinking
        yield self.tools

    def on_mount(self) -> None:
        # Render whatever body was set before mounting (e.g. history entries).
        self._refresh_text()

    def _refresh_text(self) -> None:
        self.text.update(Text.assemble(Text(f"{self._label}: ", style="bold"), self._display_body()))

    def ensure_thinking(self) -> ThinkingBlock:
        if self.thinking is None:
            self.thinking = ThinkingBlock()
            self.mount(self.thinking, before=self.tools)
        return self.thinking

    def _display_body(self) -> str:
        # Strip emotion comments first, then trailing blank lines they leave behind.
        return _strip_html_comments(self._body).rstrip()

    def append_text(self, text: str) -> None:
        self._body += text
        self._refresh_text()

    def set_final(self, summary: str) -> None:
        self._body = summary.rstrip()
        self._refresh_text()

    async def add_tool(self, tool: ToolCard) -> None:
        await self.tools.mount(tool)


class TranscriptScrolledToTop(Message):
    """Posted when the user scrolls the transcript to its very top.

    Used to lazy-load older history.
    """


class Transcript(VerticalScroll):
    """The vertical scroll of all chat turns."""

    def watch_scroll_y(self, old: float, new: float) -> None:
        # The base implementation moves the scrollbar thumb, keeps the
        # bottom anchor and — crucially — repaints. Skipping it made the
        # transcript scroll internally without ever redrawing, which is
        # what "the UI froze when I scrolled" actually was.
        super().watch_scroll_y(old, new)
        if new <= 0 and self.max_scroll_y > 0:
            self.post_message(TranscriptScrolledToTop())

    async def add_human(self, label: str, text: str) -> None:
        turn = HumanTurn(label, text)
        await self.mount(turn)
        self.scroll_end(animate=False)

    def new_assistant(self, label: str) -> AssistantBlock:
        return AssistantBlock(label)

    async def mount_assistant(self, block: AssistantBlock) -> None:
        await self.mount(block)
        self.scroll_end(animate=False)

    def clear_all(self) -> None:
        self.remove_children(selector="*")
