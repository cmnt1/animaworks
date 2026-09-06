# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from cli.tui.widgets.thinking import ThinkingBlock
from cli.tui.widgets.tool_card import ToolCard


class HumanTurn(Vertical):
    """A single user message in the transcript."""

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
        self.text.update(Text(f"{self._label}: ", style="bold"))

    def ensure_thinking(self) -> ThinkingBlock:
        if self.thinking is None:
            self.thinking = ThinkingBlock()
            self.mount(self.thinking, before=self.tools)
        return self.thinking

    def append_text(self, text: str) -> None:
        self._body += text
        self.text.update(Text.assemble(Text(f"{self._label}: ", style="bold"), self._body))

    def set_final(self, summary: str) -> None:
        self._body = summary
        self.text.update(Text.assemble(Text(f"{self._label}: ", style="bold"), summary))

    async def add_tool(self, tool: ToolCard) -> None:
        await self.tools.mount(tool)


class Transcript(VerticalScroll):
    """The vertical scroll of all chat turns."""

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
