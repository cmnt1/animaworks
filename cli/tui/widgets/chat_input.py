# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from textual import events
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Label, TextArea


class ChatSubmitted(Message):
    """Posted when the user submits the chat input via Enter."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class ChatInputChanged(Message):
    """Posted whenever the input buffer changes (used to drive the palette)."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class ChatInput(TextArea):
    """A multi-line chat input.

    ``Enter`` submits the current **entire** buffer, ``Shift+Enter``
    inserts a newline. Submissions are posted as a :class:`ChatSubmitted`
    message. Grows up to ``max_lines`` rows as content is added and
    returns to a single row after submission.

    A ``controller`` (the running app) may be attached so that arrow /
    tab keys can drive the open slash-command :class:`~cli.tui.widgets.palette.Palette`
    while the input keeps focus.
    """

    max_lines = 6

    def __init__(self, placeholder: str = "Say something…", *, controller=None, **kwargs) -> None:
        super().__init__(placeholder=placeholder, **kwargs)
        self._controller = controller

    def set_controller(self, controller) -> None:
        self._controller = controller

    def _palette_open(self) -> bool:
        return bool(self._controller is not None and self._controller.palette_is_open())

    def on_mount(self) -> None:
        self._update_height()

    def on_text_area_changed(self, _event) -> None:
        self._update_height()
        if self._controller is not None:
            self._controller.on_input_text_changed(self.text)

    def _update_height(self) -> None:
        lines = max(self.document.line_count, 1)
        self.styles.height = min(lines, self.max_lines)

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            if self._palette_open():
                event.stop()
                event.prevent_default()
                self._controller.palette_confirm()
                return
            event.stop()
            event.prevent_default()
            text = self.text
            if text.strip():
                self.post_message(ChatSubmitted(text))
            self.clear()
            self._update_height()
            return
        if event.key == "tab" and self._palette_open():
            event.stop()
            event.prevent_default()
            self._controller.palette_complete()
            return
        if event.key == "escape" and self._palette_open():
            event.stop()
            event.prevent_default()
            self._controller.palette_close()
            return
        if event.key in ("up", "down", "pageup", "pagedown", "home", "end") and self._palette_open():
            event.stop()
            event.prevent_default()
            self._controller.palette_move(event.key)
            return
        if event.key == "shift+enter":
            event.stop()
            event.prevent_default()
            self.insert("\n")
            self._update_height()
            return
        await super()._on_key(event)


class ChatInputContainer(Horizontal):
    """Prompt label + :class:`ChatInput`, auto-sizing up to 6 rows."""

    def __init__(self, placeholder: str = "Say something…", **kwargs) -> None:
        super().__init__(**kwargs)
        self._placeholder = placeholder
        self.input = ChatInput(placeholder=placeholder)

    def compose(self):
        yield Label(">", classes="input-prompt")
        yield self.input

    def focus_input(self) -> None:
        self.input.focus()
