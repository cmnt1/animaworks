# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import time

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from cli.tui.client import AnimaWorksClient, AnimaWorksClientError
from cli.tui.commands import get_command, is_command
from cli.tui.sse import SseEvent
from cli.tui.widgets import (
    ChatInputContainer,
    ChatSubmitted,
    StatusBar,
    ToolCard,
    Transcript,
)
from cli.tui.widgets.thinking import ThinkingBlock
from cli.tui.widgets.transcript import AssistantBlock


class AnimaChatApp(App):
    """The interactive terminal chat UI for talking to an anima."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #transcript {
        height: 1fr;
        border: round $primary;
        background: $surface;
        padding: 0 1;
    }
    #input-container {
        height: auto;
        background: $panel;
    }
    #input-container .input-prompt {
        padding: 1 0 0 1;
        text-style: bold;
    }
    #input {
        height: auto;
        border: none;
        padding: 0 1;
    }
    #status {
        height: 1;
        dock: bottom;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    #transcript .human-label {
        margin-top: 1;
    }
    #transcript .assistant-text, #transcript .human-message {
        width: 100%;
        padding: 0 2;
    }
    #transcript .transient {
        height: auto;
        width: 100%;
        padding: 0 2;
    }
    """

    BINDINGS = [
        Binding("escape", "maybe_interrupt", "Interrupt"),
        Binding("ctrl+c", "quit_or_confirm", "Quit"),
        Binding("ctrl+d", "quit_now", "Quit"),
    ]

    def __init__(
        self,
        client: AnimaWorksClient,
        anima_name: str,
        thread_id: str = "default",
    ) -> None:
        super().__init__()
        self.client = client
        self.anima_name = anima_name
        self.thread_id = thread_id

        self.busy = False
        self.current: AssistantBlock | None = None
        self.tool_cards: dict[str, ToolCard] = {}
        self.show_thinking = False
        self._last_ctrlc = 0.0

    # ── Lifecycle ──────────────────────────────────────────
    def compose(self) -> ComposeResult:
        yield Transcript(id="transcript")
        yield ChatInputContainer(id="input-container")
        yield StatusBar(self.anima_name, self.thread_id, id="status")

    def on_mount(self) -> None:
        self.title = f"AnimaWorks — {self.anima_name}"

        self.transcript = self.query_one("#transcript", Transcript)
        self.input_container = self.query_one("#input-container", ChatInputContainer)
        self.status_bar = self.query_one("#status", StatusBar)

        self.call_after_refresh(self.focus_input)

        self.run_worker(self._bootstrap(), group="init", exit_on_error=False)

    def focus_input(self) -> None:
        if self.input_container.input.has_focus is not True:
            self.input_container.focus_input()

    async def _bootstrap(self) -> None:
        try:
            animas = await self.client.list_animas()
        except AnimaWorksClientError as exc:
            self.status_bar.set_state(status="error", right_hint=f"connection error: {exc}")
            self.show_transient(f"Connection error: {exc}")
            return
        names = {a.get("name") for a in animas}
        if self.anima_name not in names:
            self.status_bar.set_state(
                status="error",
                right_hint=f"Anima '{self.anima_name}' not found",
            )
            self.show_transient(f"Anima '{self.anima_name}' not found.")
            self.set_timer(0.5, lambda: self.exit(return_code=1))
            return
        entry = next(
            (a for a in animas if a.get("name") == self.anima_name),
            None,
        )
        busy = (entry or {}).get("busy")
        if isinstance(busy, dict) and busy.get("is_busy"):
            status = "busy"
        else:
            status = "idle"
        self.status_bar.set_state(status=status)
        self.run_worker(self._load_history(), group="init", exit_on_error=False)
        self.run_worker(self._ws_loop(), group="ws", exit_on_error=False)

    # ── History ───────────────────────────────────────────
    async def _load_history(self) -> None:
        try:
            history = await self.client.get_history(
                self.anima_name,
                thread_id=self.thread_id,
                limit=50,
            )
        except AnimaWorksClientError:
            self.status_bar.set_state(right_hint="history unavailable")
            return
        await self.render_history(history)

    async def render_history(self, history: dict) -> None:
        for session in history.get("sessions", []):
            for msg in session.get("messages", []):
                role = msg.get("role")
                content = msg.get("content")
                if not content:
                    continue
                if role == "human":
                    await self.transcript.add_human("You", str(content))
                elif role == "assistant":
                    block = self.transcript.new_assistant(self.anima_name)
                    block.set_final(str(content))
                    await self.transcript.mount_assistant(block)
                # any other role (e.g. system) is skipped as noise
        self.current = None

    async def reload_history(self, limit: int = 20) -> None:
        try:
            history = await self.client.get_history(
                self.anima_name,
                thread_id=self.thread_id,
                limit=limit,
            )
        except AnimaWorksClientError as exc:
            self.show_transient(f"Failed to reload history: {exc}")
            return
        self.transcript.clear_all()
        self.current = None
        await self.render_history(history)

    # ── WebSocket ─────────────────────────────────────────
    async def _ws_loop(self) -> None:
        async for msg in self.client.ws_events():
            self.handle_ws(msg)

    def handle_ws(self, msg: dict) -> None:
        event_type = msg.get("type")
        data = msg.get("data") or {}
        if event_type == "_ws_status":
            self.status_bar.set_state(connected=bool(data.get("connected")))
        elif event_type == "anima.status":
            if data.get("name") == self.anima_name:
                # Anima-level process/lane status. Do not touch ``busy``:
                # it would race with our own streaming lane.
                status = data.get("status") or "idle"
                self.status_bar.set_state(status=status)
        elif event_type == "anima.tool_activity":
            if data.get("name") == self.anima_name:
                evt = data.get("event")
                tool_name = data.get("tool_name")
                if evt == "tool_start":
                    self.status_bar.set_state(active_tool=tool_name)
                elif evt == "tool_end":
                    self.status_bar.set_state(active_tool=None)

    # ── Input ────────────────────────────────────────────
    def on_chat_submitted(self, message: ChatSubmitted) -> None:
        self.run_worker(
            self._handle_message(message.text.strip()),
            group="submit",
            exit_on_error=False,
        )

    async def _handle_message(self, text: str) -> None:
        if not text:
            return
        if is_command(text):
            await self.handle_command(text)
        elif self.busy:
            self.status_bar.set_state(right_hint="Busy — wait for the response to finish")
        else:
            await self.send_message(text)

    # ── Sending / streaming ──────────────────────────────
    async def send_message(self, text: str) -> None:
        self.busy = True
        self.status_bar.set_state(status="thinking", right_hint="responding…")
        await self.transcript.add_human("You", text)
        self.current = self.transcript.new_assistant(self.anima_name)
        await self.transcript.mount_assistant(self.current)
        self.tool_cards = {}
        self.run_worker(
            self._chat_worker(text),
            group="chat",
            exclusive=True,
            exit_on_error=False,
        )

    async def _chat_worker(self, text: str) -> None:
        try:
            async for sse in self.client.chat_stream(
                self.anima_name,
                text,
                thread_id=self.thread_id,
            ):
                await self.handle_sse(sse)
        except AnimaWorksClientError as exc:
            await self._show_error(str(exc))
        finally:
            self.busy = False
            self.status_bar.set_state(active_tool=None)
            self.call_after_refresh(self.focus_input)

    async def handle_sse(self, sse: SseEvent) -> None:
        name = sse.event
        data = sse.data
        if name == "stream_start":
            self.status_bar.set_state(status="thinking")
        elif name == "text_delta":
            if self.current is not None:
                self.current.append_text(data.get("text", ""))
        elif name == "thinking_start":
            if self.current is not None:
                self.current.ensure_thinking().set_visible(self.show_thinking)
        elif name == "thinking_delta":
            if self.current is not None:
                block = self.current.ensure_thinking()
                block.set_visible(self.show_thinking)
                block.add_delta(data.get("text", ""))
        elif name == "thinking_end":
            pass
        elif name == "tool_start":
            tool_id = data.get("tool_id", "")
            card = ToolCard(data.get("tool_name", "tool"), tool_id)
            if data.get("input_summary"):
                card.add_detail(str(data.get("input_summary")))
            self.tool_cards[tool_id] = card
            if self.current is not None:
                await self.current.add_tool(card)
        elif name == "tool_detail":
            card = self.tool_cards.get(data.get("tool_id", ""))
            if card is not None:
                card.add_detail(str(data.get("detail", "")))
        elif name == "tool_end":
            card = self.tool_cards.get(data.get("tool_id", ""))
            if card is not None:
                card.finish(
                    result_summary=data.get("result_summary"),
                    is_error=bool(data.get("is_error")),
                )
            if data.get("tool_name") == self.status_bar.active_tool:
                self.status_bar.set_state(active_tool=None)
        elif name == "chain_start":
            pass
        elif name == "done":
            summary = data.get("summary") or ""
            if self.current is not None:
                self.current.set_final(summary)
            self.busy = False
            self.status_bar.set_state(status="idle", right_hint="Esc: interrupt")
        elif name == "error":
            await self._show_error(data.get("message", "Stream error"))
            self.busy = False
            self.status_bar.set_state(status="error", right_hint="Esc: interrupt")
        elif name == "bootstrap":
            self.show_transient(f"bootstrap: {data.get('status')} {data.get('message') or ''}")
        elif name == "context_update":
            ratio = data.get("context_usage_ratio")
            if ratio is not None:
                self.status_bar.set_state(right_hint=f"context: {int(float(ratio) * 100)}% | Esc: interrupt")
        elif name == "heartbeat_relay":
            pass

    async def _show_error(self, message: str) -> None:
        if self.current is not None:
            self.current.append_text(f"\n[red]Error: {message}[/red]\n")

    # ── Slash commands ───────────────────────────────────
    async def handle_command(self, text: str) -> None:
        parts = text.split()
        name = parts[0][1:]
        args = parts[1:]
        cmd = get_command(name)
        if cmd is None:
            self.show_transient(f"Unknown command: /{name}   (try /help)")
            return
        cmd.handler(args, self)
        self.call_after_refresh(self.focus_input)

    def show_transient(self, text: str) -> None:
        self.run_worker(self._show_transient_async(text), group="ui", exit_on_error=False)

    async def _show_transient_async(self, text: str) -> None:
        widget = Static(Text(str(text), style="italic dim"), classes="transient")
        await self.transcript.mount(widget)
        self.transcript.scroll_end(animate=False)

    def clear_transcript(self) -> None:
        self.transcript.clear_all()
        self.current = None
        self.tool_cards = {}

    def toggle_thinking(self) -> None:
        self.show_thinking = not self.show_thinking
        for block in self.query(ThinkingBlock):
            block.set_visible(self.show_thinking)
        self.show_transient(f"Thinking display: {'on' if self.show_thinking else 'off'}")

    def request_interrupt(self) -> None:
        self.action_maybe_interrupt()

    # ── Actions ──────────────────────────────────────────
    def action_maybe_interrupt(self) -> None:
        if self.busy:
            self.run_worker(self._do_interrupt(), group="interrupt", exit_on_error=False)

    async def _do_interrupt(self) -> None:
        try:
            await self.client.interrupt(self.anima_name, thread_id=self.thread_id)
        except AnimaWorksClientError as exc:
            self.show_transient(f"Interrupt failed: {exc}")
            return
        self.busy = False
        self.status_bar.set_state(
            status="idle",
            active_tool=None,
            right_hint="Esc: interrupt",
        )
        self.show_transient("Interrupted.")

    def action_quit_or_confirm(self) -> None:
        now = time.monotonic()
        if now - self._last_ctrlc < 2.0:
            self.exit()
        else:
            self._last_ctrlc = now
            self.status_bar.set_state(right_hint="Press Ctrl+C again to quit")

    def action_quit_now(self) -> None:
        self.exit()
