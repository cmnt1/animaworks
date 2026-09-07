# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re

from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.geometry import Size
from textual.message import Message
from textual.widgets import Static

from cli.tui.markdown import render_markdown
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
        self.label_widget.update(Text(f"{self._label}:", style="bold"))
        # Wrapped in Text so console markup a person happens to type
        # (`[red]…`) is shown, not interpreted.
        self.message.update(Text(self._text))


class SystemNote(Vertical):
    """A system-role entry: heartbeats, cron triggers, notifications.

    These are the anima's background traffic rather than the
    conversation, so they are drawn faintly — the same treatment the web
    UI gives them. Dropping them altogether made threads whose recent
    history is all background look empty.
    """

    DEFAULT_CSS = """
    SystemNote {
        height: auto;
        width: 100%;
    }
    """

    def __init__(self, label: str, text: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._text = text
        self.label_widget = Static("", classes="system-label")
        self.message = Static("", classes="system-message")

    def compose(self):
        yield self.label_widget
        yield self.message

    def on_mount(self) -> None:
        self.label_widget.update(Text(self._label, style="dim bold"))
        self.message.update(render_markdown(strip_html_comments(self._text).rstrip(), muted=True))


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
        # The speaker gets its own row, like `You:` does. Inlining it as a
        # prefix left the name buried in the first paragraph, so a reader
        # scanning the transcript could not tell who was talking.
        self.label_widget = Static("", classes="assistant-label")
        self.text = Static("", classes="assistant-text")
        self.thinking: ThinkingBlock | None = None
        self.tools = Vertical(classes="tools")

    def compose(self):
        yield self.label_widget
        yield self.text
        if self.thinking is not None:
            yield self.thinking
        yield self.tools

    def on_mount(self) -> None:
        self.label_widget.update(Text(f"{self._label}:", style="bold"))
        # Render whatever body was set before mounting (e.g. history entries).
        self._refresh_text()

    def _refresh_text(self) -> None:
        self.text.update(render_markdown(self._display_body()))

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

    async def add_error(self, message: str) -> None:
        """Show a stream error under the body.

        Kept out of the body text: that is rendered as markdown now, so
        console markup poked into it would be shown literally.
        """
        widget = Static(Text(f"Error: {message}", style="bold red"), classes="assistant-error")
        await self.mount(widget, before=self.tools)

    async def add_tool(self, tool: ToolCard) -> None:
        await self.tools.mount(tool)


class TranscriptScrolledToTop(Message):
    """Posted when the user scrolls the transcript to its very top.

    Used to lazy-load older history.
    """


class Transcript(VerticalScroll):
    """The vertical scroll of all chat turns."""

    # Following the tail is a mode, the way a pager behaves: scrolling up
    # turns it off, coming back to the bottom turns it on again. Mounting
    # a turn used to scroll to the end once, but the reply kept growing
    # afterwards and the view stayed where it was, so every message had
    # to be scrolled down by hand.
    _follow_tail = True

    def watch_scroll_y(self, old: float, new: float) -> None:
        # The base implementation moves the scrollbar thumb, keeps the
        # bottom anchor and — crucially — repaints. Skipping it made the
        # transcript scroll internally without ever redrawing, which is
        # what "the UI froze when I scrolled" actually was.
        super().watch_scroll_y(old, new)
        self._follow_tail = new >= self.max_scroll_y
        if new <= 0 and self.max_scroll_y > 0:
            self.post_message(TranscriptScrolledToTop())

    def watch_virtual_size(self, old: Size, new: Size) -> None:
        # Every growth of the transcript lands here: streamed text, tool
        # cards, thinking blocks. Deferred inside `scroll_end`, so the new
        # `max_scroll_y` is the one that gets used.
        if old != new and self._follow_tail:
            self.scroll_end(animate=False)

    def jump_to_end(self) -> None:
        """Scroll to the newest turn and resume following it."""
        self._follow_tail = True
        self.scroll_end(animate=False)

    async def add_human(self, label: str, text: str) -> None:
        turn = HumanTurn(label, text)
        await self.mount(turn)
        self.jump_to_end()

    def new_assistant(self, label: str) -> AssistantBlock:
        return AssistantBlock(label)

    async def mount_assistant(self, block: AssistantBlock) -> None:
        await self.mount(block)
        self.jump_to_end()

    def clear_all(self) -> None:
        self.remove_children(selector="*")
