# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from cli.tui.client import AnimaWorksClient, AnimaWorksClientError
from cli.tui.commands import get_command, is_command, iter_commands
from cli.tui.keybindings import app_keymap, load_keybindings
from cli.tui.session import SessionInfo, new_session, save_session
from cli.tui.sse import SseEvent
from cli.tui.state import AppState, PaletteItem, apply_ws_event, filter_palette
from cli.tui.widgets import (
    CallHumanOption,
    ChatInputContainer,
    ChatSubmitted,
    InteractionCard,
    Palette,
    Sidebar,
    StatusBar,
    ToolCard,
    Transcript,
)
from cli.tui.widgets.sidebar import AnimaChosen
from cli.tui.widgets.thinking import ThinkingBlock
from cli.tui.widgets.transcript import AssistantBlock, HumanTurn, strip_html_comments

# WS event types that are fed into the shared sidebar state.
_WS_STATE_TYPES = {
    "anima.status",
    "anima.tool_activity",
    "anima.heartbeat",
    "anima.cron",
    "anima.bootstrap",
    "anima.proactive_message",
    "anima.notification",
    "anima.interaction",
    "board.post",
}


class AnimaChatApp(App):
    """The interactive terminal chat UI for talking to an anima."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #body {
        height: 1fr;
        layout: horizontal;
    }
    Sidebar {
        width: 32;
    }
    #right {
        width: 1fr;
        height: 1fr;
        layout: vertical;
    }
    #transcript {
        height: 1fr;
        border: round $primary;
        background: $surface;
        padding: 0 1;
    }
    #palette {
        height: auto;
        max-height: 12;
        display: none;
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
        Binding("escape", "maybe_interrupt", "Interrupt", id="interrupt"),
        Binding("ctrl+c", "quit_or_confirm", "Quit"),
        Binding("ctrl+d", "quit_now", "Quit", id="quit", priority=True),
        Binding("ctrl+b", "toggle_sidebar", "Toggle sidebar", show=False, id="toggle_sidebar"),
        Binding("ctrl+t", "toggle_thinking", "Toggle thinking", show=False, id="toggle_thinking"),
        Binding("ctrl+l", "focus_input", "Focus input", show=False, id="focus_input"),
        Binding("pageup", "scroll_up", "Scroll up", show=False, id="scroll_up"),
        Binding("pagedown", "scroll_down", "Scroll down", show=False, id="scroll_down"),
    ]

    def __init__(
        self,
        client: AnimaWorksClient,
        anima_name: str,
        thread_id: str = "default",
        *,
        session: SessionInfo | None = None,
        session_dir: Path | None = None,
        no_reattach: bool = False,
        keymap: dict[str, str] | None = None,
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

        self.state = AppState()
        self.state.current = anima_name
        self._skills: list[dict] = []
        self._pending_cards: dict[str, dict] = {}
        self._suppress_palette = False
        self._sidebar_open = True

        # Phase 3: session + resume + keybindings.
        self.session_dir = session_dir
        if session is None:
            session = new_session(
                anima=anima_name,
                thread_id=thread_id,
                gateway_url=getattr(client, "base_url", "") or "http://localhost:18500",
                from_person=getattr(client, "from_person", "human") or "human",
            )
        self.session: SessionInfo = session
        self.no_reattach = no_reattach
        self._keymap, self._key_warnings = (keymap, []) if keymap is not None else load_keybindings()
        self._key_warnings = list(self._key_warnings)

        # History lazy-loading cursor state.
        self._history_cursor: str | None = None
        self._history_end = False
        self._history_loading = False

        # Stream reconnect state.
        self._last_event_id: str | None = None
        self._last_response_id: str | None = None

        # Session save throttling.
        self._session_save_pending = False

    # ── Lifecycle ──────────────────────────────────────────
    def compose(self) -> ComposeResult:
        with Horizontal(id="body"):
            yield Sidebar(id="sidebar")
            with Vertical(id="right"):
                yield Transcript(id="transcript")
                yield Palette(id="palette")
                yield ChatInputContainer(id="input-container")
        yield StatusBar(self.anima_name, self.thread_id, id="status")

    def on_mount(self) -> None:
        self.title = f"AnimaWorks — {self.anima_name}"
        try:
            self._bindings.apply_keymap(app_keymap(self._keymap))
        except Exception:
            pass

        self.body = self.query_one("#body", Horizontal)
        self.sidebar = self.query_one("#sidebar", Sidebar)
        self.transcript = self.query_one("#transcript", Transcript)
        self.input_container = self.query_one("#input-container", ChatInputContainer)
        self.status_bar = self.query_one("#status", StatusBar)
        self.palette = self.query_one("#palette", Palette)
        self.input_container.input.set_controller(self)

        # Default the sidebar closed on narrow terminals.
        width = getattr(self, "size", None)
        term_w = getattr(width, "width", None) if width else None
        if term_w is not None and term_w < 100:
            self._set_sidebar_open(False)

        self.call_after_refresh(self.focus_input)

        self.run_worker(self._bootstrap(), group="init", exit_on_error=False)

    def focus_input(self) -> None:
        if self.input_container.input.has_focus is not True:
            self.input_container.focus_input()

    def focus_sidebar(self) -> None:
        self.sidebar.animas.focus()

    async def _bootstrap(self) -> None:
        try:
            animas = await self.client.list_animas()
        except AnimaWorksClientError as exc:
            self.status_bar.set_state(status="error", right_hint=f"connection error: {exc}")
            self.show_transient(f"Connection error: {exc}")
            return
        self.state.set_animas(animas)
        self.sidebar.update_state(self.state)
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
        self.run_worker(self._load_history_then_reattach(), group="init", exit_on_error=False)
        self.run_worker(self._load_skills(), group="init", exit_on_error=False)
        self.run_worker(self._ws_loop(), group="ws", exit_on_error=False)

    async def _load_history_then_reattach(self) -> None:
        # History first so a resumed in-flight response is appended after it.
        await self._load_history()
        await self._check_reattach()

    # ── History ───────────────────────────────────────────
    async def _load_history(self) -> None:
        history = await self._get_history()
        if history is None:
            return
        self._history_cursor = history.get("next_before")
        if not history.get("has_more"):
            self._history_end = True
        await self.render_history(history)

    async def _get_history(self, *, before: str | None = None) -> dict | None:
        try:
            return await self.client.get_history(
                self.anima_name,
                thread_id=self.thread_id,
                limit=50,
                before=before,
            )
        except AnimaWorksClientError:
            self.status_bar.set_state(right_hint="history unavailable")
            return None

    def _clear_history_cursor(self) -> None:
        self._history_cursor = None
        self._history_end = False
        self._history_loading = False

    async def render_history(self, history: dict) -> None:
        for session in history.get("sessions", []):
            for msg in session.get("messages", []):
                await self._render_history_msg(msg, prepend=False)
        self.current = None

    async def _render_history_msg(self, msg: dict, *, prepend: bool) -> None:
        role = msg.get("role")
        content = msg.get("content")
        if not content:
            return
        if role == "human":
            turn = HumanTurn("You", str(content))
            await self.transcript.mount(turn, before=0 if prepend else None)
        elif role == "assistant":
            block = self.transcript.new_assistant(self.anima_name)
            block.set_final(str(content))
            await self.transcript.mount(block, before=0 if prepend else None)
        # any other role (e.g. system) is skipped as noise

    async def _show_beginning_marker(self) -> None:
        if any(
            isinstance(c, Static) and getattr(c, "classes", None) and "beginning" in c.classes
            for c in self.transcript.children
        ):
            return
        marker = Static("— beginning of history —", classes="beginning")
        await self.transcript.mount(marker, before=0)

    async def load_older_history(self) -> None:
        """Load and prepend older history; called when the user scrolls to the top."""
        if self._history_loading:
            return
        if self._history_end:
            await self._show_beginning_marker()
            return
        if not self._history_cursor:
            self._history_end = True
            await self._show_beginning_marker()
            return
        self._history_loading = True
        history = None
        try:
            history = await self._get_history(before=self._history_cursor)
        finally:
            self._history_loading = False
        if history is None:
            return
        self._history_cursor = history.get("next_before")
        if not history.get("has_more"):
            self._history_end = True
        await self.render_history_at_top(history)
        if self._history_end:
            await self._show_beginning_marker()

    async def render_history_at_top(self, history: dict) -> None:
        """Render older history above the current transcript, keeping scroll position."""
        prev_scroll = self.transcript.scroll_y
        old_first = self.transcript.children[0] if self.transcript.children else None
        added = 0
        for session in history.get("sessions", []):
            for msg in session.get("messages", []):
                role = msg.get("role")
                content = msg.get("content")
                if not content:
                    continue
                added += 1
                if role == "human":
                    turn = HumanTurn("You", str(content))
                    await self.transcript.mount(turn, before=old_first)
                elif role == "assistant":
                    block = self.transcript.new_assistant(self.anima_name)
                    block.set_final(str(content))
                    await self.transcript.mount(block, before=old_first)
        # Approximate the inserted height (a turn is ~2 rows) to keep the
        # current view stable after prepending older content.
        if added and prev_scroll > 0:
            try:
                self.transcript.scroll_y = prev_scroll + added * 2
            except Exception:
                pass

    def load_more_history(self) -> None:
        """Slash-command handler: load 50 more (older) messages."""
        self.run_worker(self.load_older_history(), group="history", exit_on_error=False)

    async def reload_history(self, limit: int = 50) -> None:
        self._clear_history_cursor()
        history = await self._get_history()
        if history is None:
            return
        self.transcript.clear_all()
        self.current = None
        self._history_cursor = history.get("next_before")
        if not history.get("has_more"):
            self._history_end = True
        await self.render_history(history)

    def on_transcript_scrolled_to_top(self, _message) -> None:
        self.run_worker(self.load_older_history(), group="history", exit_on_error=False)

    # ── Skills ───────────────────────────────────────────
    async def _load_skills(self) -> None:
        list_skills = getattr(self.client, "list_skills", None)
        if list_skills is None:
            self._skills = []
            self._update_skill_count()
            return
        try:
            resp = await list_skills(self.anima_name, self.thread_id)
        except Exception:
            self._skills = []
            self._update_skill_count()
            return
        self._skills = resp.get("skills") or []
        self._update_skill_count()

    def _update_skill_count(self) -> None:
        count = sum(1 for s in self._skills if s.get("active"))
        self.status_bar.set_state(skill_count=count)

    # ── WebSocket ─────────────────────────────────────────
    async def _ws_loop(self) -> None:
        async for msg in self.client.ws_events():
            self.handle_ws(msg)

    def handle_ws(self, msg: dict) -> None:
        event_type = msg.get("type")
        data = msg.get("data") or {}
        if event_type == "_ws_status":
            self.status_bar.set_state(connected=bool(data.get("connected")))
            return

        if event_type in _WS_STATE_TYPES:
            eff = apply_ws_event(self.state, msg)
            self._apply_ws_effect(eff, data)
            self.sidebar.update_state(self.state)

        # Per-anima (self) status bar handling stays unchanged.
        if event_type == "anima.status" and data.get("name") == self.anima_name:
            status = data.get("status") or "idle"
            self.status_bar.set_state(status=status)
        elif event_type == "anima.tool_activity" and data.get("name") == self.anima_name:
            evt = data.get("event")
            kind = data.get("kind")
            tool_name = data.get("tool_name") or data.get("tool")
            if (evt == "tool_start" or kind == "tool_use") and self.busy:
                # Only while a response is in flight: a late tool_start after
                # ``done`` must not leave a stale tool name in the status bar.
                self.status_bar.set_state(active_tool=tool_name)
            elif evt == "tool_end" or kind == "tool_result":
                self.status_bar.set_state(active_tool=None)

    def _apply_ws_effect(self, eff, data: dict) -> None:
        for _title, _body in eff.toasts:
            self.notify(_body or _title, timeout=6)
        for pmsg in eff.proactive:
            name = pmsg.get("anima") or pmsg.get("name")
            if name == self.anima_name:
                self._thread_proactive(pmsg)
        for card_data in eff.cards:
            self._thread_interaction_card(card_data)

    def _thread_proactive(self, data: dict) -> None:
        subject = data.get("subject") or ""
        body = strip_html_comments(data.get("body") or "")
        text = (f"**{subject}**\n{body}" if subject else body).replace("**", "")
        block = self.transcript.new_assistant(self.anima_name)
        block.set_final(text)
        self.run_worker(self.transcript.mount_assistant(block), group="ui", exit_on_error=False)

    def _thread_interaction_card(self, data: dict) -> None:
        name = data.get("anima") or data.get("name") or self.anima_name
        card = InteractionCard(name, data)
        self._pending_cards[card.callback_id] = {"anima": name, "options": card.options}
        self.run_worker(self.transcript.mount(card), group="ui", exit_on_error=False)

    # ── Input / palette (called by ChatInput) ────────────
    def palette_is_open(self) -> bool:
        return self.palette.is_open

    def on_input_text_changed(self, text: str) -> None:
        if self._suppress_palette:
            self._suppress_palette = False
            return
        if text.startswith("/") and not self.busy:
            items = filter_palette(self._palette_items(), text)
            if items:
                self.palette.set_items(items)
            else:
                self.palette.close()
        else:
            self.palette.close()

    def _clear_input(self) -> None:
        self._suppress_palette = True
        self.input_container.input.text = ""
        self.palette.close()

    def palette_move(self, direction: str) -> None:
        if self.palette.is_open:
            self.palette.move(direction)

    def palette_close(self) -> None:
        self.palette.close()

    def palette_complete(self) -> None:
        """Tab: complete with the selected candidate only (never execute)."""
        if not self.palette.is_open:
            return
        item = self.palette.selected()
        self.palette.close()
        if item is None:
            return
        self._suppress_palette = True
        self.input_container.input.text = item.value
        self.focus_input()

    def palette_confirm(self) -> None:
        """Enter: run a fully-typed command, otherwise complete (running where
        the candidate needs no further input).

        Mirrors Claude Code: an input that is exactly a registered command
        name runs immediately; a partial input completes with the selected
        candidate (running it if it takes no arguments, otherwise keeping the
        user in the input to continue).
        """
        if not self.palette.is_open:
            return
        raw = self.input_container.input.text
        if self._matches_exact_command(raw):
            self._clear_input()
            self.run_worker(
                self._handle_message(raw.strip()),
                group="submit",
                exit_on_error=False,
            )
            return
        item = self.palette.selected()
        self.palette.close()
        if item is None:
            return
        if item.on_confirm is not None:
            self._clear_input()
            item.on_confirm(self)
            return
        self._suppress_palette = True
        self.input_container.input.text = item.value
        self.palette.close()
        if not item.takes_args:
            self._clear_input()
            self.run_worker(
                self._handle_message(item.value.strip()),
                group="submit",
                exit_on_error=False,
            )
        else:
            self.focus_input()

    def _matches_exact_command(self, text: str) -> bool:
        """True when ``text`` is exactly ``/name`` (no extra whitespace or
        arguments) and ``name`` is a registered command."""
        stripped = text.strip()
        if not stripped.startswith("/"):
            return False
        name = stripped[1:].strip()
        if not name or " " in name:
            return False
        return get_command(name) is not None

    def _palette_items(self) -> list[PaletteItem]:
        items: list[PaletteItem] = []
        for cmd in iter_commands():
            if cmd.takes_args:
                items.append(
                    PaletteItem(
                        value=f"/{cmd.name} ",
                        label=Text.assemble(
                            Text(f"/{cmd.name}", style="bold"), Text(f"  {cmd.description}", style="dim")
                        ),
                        takes_args=True,
                        search=f"/{cmd.name}",
                    )
                )
            else:
                items.append(
                    PaletteItem(
                        value=f"/{cmd.name}",
                        label=Text.assemble(
                            Text(f"/{cmd.name}", style="bold"), Text(f"  {cmd.description}", style="dim")
                        ),
                        takes_args=False,
                        search=f"/{cmd.name}",
                        on_confirm=_make_runner(cmd.handler),
                    )
                )
        for skill in self._skills:
            name = skill.get("name") or ""
            if not name:
                continue
            desc = (skill.get("description") or "")[:60]
            marks = []
            if skill.get("active"):
                marks.append("● ")
            if skill.get("is_common"):
                marks.append("(common) ")
            if skill.get("is_procedure"):
                marks.append("(procedure) ")
            label = Text.assemble(
                Text(f"/skill {name}", style="bold"),
                Text(f"  {''.join(marks)}{desc}", style="dim"),
            )
            low = name.lower()
            items.append(
                PaletteItem(
                    value=f"/skill {name}",
                    label=label,
                    takes_args=True,
                    search=f"/skill {low} /{low} {low}",
                )
            )
        return items

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
        self._last_response_id = None
        self._last_event_id = None
        self.session.in_flight = True
        self.session.last_response_id = None
        self.session.last_event_id = None
        self.run_worker(
            self._chat_worker(text),
            group="chat",
            exclusive=True,
            exit_on_error=False,
        )

    def _handle_stream_event_state(self, sse: SseEvent) -> bool:
        """Track resume state from an event.

        Returns True when an ``error`` event with ``STREAM_NOT_FOUND`` is
        seen (the caller should stop reconnecting).
        """
        if sse.event == "stream_start":
            rid = sse.data.get("response_id")
            if rid:
                self._last_response_id = rid
                self.session.last_response_id = rid
                self.session.in_flight = True
                self._schedule_session_save(force=True)
        if sse.id:
            self._last_event_id = sse.id
            self.session.last_event_id = sse.id
            self._schedule_session_save()
        return sse.event == "error" and sse.data.get("code") == "STREAM_NOT_FOUND"

    async def _chat_worker(
        self,
        text: str,
        *,
        resume: str | None = None,
        last_event_id: str | None = None,
    ) -> None:
        delay = 1.0
        attempts = 0
        while True:
            try:
                async for sse in self.client.chat_stream(
                    self.anima_name,
                    text,
                    thread_id=self.thread_id,
                    resume=resume,
                    last_event_id=last_event_id,
                ):
                    self._handle_stream_event_state(sse)
                    await self.handle_sse(sse)
                break
            except AnimaWorksClientError as exc:
                if self._last_response_id is None:
                    await self._show_error(str(exc))
                    break
                if attempts >= 3:
                    self.show_transient("stream lost")
                    break
                attempts += 1
                await asyncio.sleep(delay)
                delay = min(delay * 2, 4.0)
                resume = self._last_response_id
                last_event_id = self._last_event_id
        self.busy = False
        self.session.in_flight = False
        self._schedule_session_save(force=True)
        self.status_bar.set_state(active_tool=None)
        self.call_after_refresh(self.focus_input)

    def _schedule_session_save(self, *, force: bool = False) -> None:
        if force:
            self._write_session()
            self._session_save_pending = False
            return
        if not self._session_save_pending:
            self._session_save_pending = True
            self.set_timer(1.0, self._flush_session_save)

    def _flush_session_save(self) -> None:
        if not self._session_save_pending:
            return
        self._session_save_pending = False
        self._write_session()

    def _write_session(self) -> None:
        try:
            save_session(self.session, base_dir=self.session_dir)
        except Exception:
            pass

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
            self.session.in_flight = False
            self._schedule_session_save(force=True)
            self.status_bar.set_state(status="idle", active_tool=None, right_hint="Esc: interrupt")
        elif name == "error":
            await self._show_error(data.get("message", "Stream error"))
            self.busy = False
            self.session.in_flight = False
            self._schedule_session_save(force=True)
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
        self.session.show_thinking = self.show_thinking
        self._write_session()
        for block in self.query(ThinkingBlock):
            block.set_visible(self.show_thinking)
        self.show_transient(f"Thinking display: {'on' if self.show_thinking else 'off'}")

    def request_interrupt(self) -> None:
        self.action_maybe_interrupt()

    # ── Anima switching / sidebar ───────────────────────
    def switch_anima(self, name: str) -> None:
        self.run_worker(
            self._switch_anima_worker(name),
            group="switch",
            exclusive=True,
            exit_on_error=False,
        )

    async def _switch_anima_worker(self, name: str) -> None:
        if name == self.anima_name:
            return
        if self.busy:
            self.show_transient("Finish or Esc-interrupt the current response before switching.")
            return
        if name not in self.state.animas:
            self.show_transient(f"Unknown anima: {name}")
            return
        self.anima_name = name
        self.state.current = name
        self.state.clear_unread(name)
        self.title = f"AnimaWorks — {name}"
        self.status_bar.set_anima(name, self.thread_id)
        self.busy = False
        self.clear_transcript()
        self.sidebar.update_state(self.state)
        await self.reload_history(limit=50)
        self.show_transient(f"-- switched to {name} --")
        if len(self.transcript.children) == 0:
            self.show_transient("no conversation history yet")
        await self._load_skills()
        if name not in self.session.recent_animas:
            self.session.recent_animas.append(name)
        self.session.anima = name
        self._write_session()

    def _set_sidebar_open(self, open_state: bool) -> None:
        self._sidebar_open = open_state
        self.sidebar.display = "block" if open_state else "none"

    def toggle_sidebar(self) -> None:
        self._set_sidebar_open(not self._sidebar_open)
        self.session.sidebar_open = self._sidebar_open
        self._write_session()

    def on_anima_chosen(self, message: AnimaChosen) -> None:
        self.switch_anima(message.name)

    def action_toggle_sidebar(self) -> None:
        self.toggle_sidebar()

    # ── Reattach (Phase 3) ──────────────────────────────
    async def _check_reattach(self) -> None:
        if self.no_reattach:
            return
        active = None
        try:
            active = await self.client.get_active_stream(
                self.anima_name,
                thread_id=self.thread_id,
            )
        except AnimaWorksClientError:
            return
        action = decide_reattach(active, self.session.in_flight)
        if action == "reattach":
            await self._render_reattach(active)
        elif action == "render_final":
            await self._render_final(active)
            self.session.in_flight = False
            self._write_session()
        elif action == "lost":
            self.show_transient("The previous response could not be resumed. Use /history to review the conversation.")

    async def _render_reattach(self, active: dict) -> None:
        if self.current is not None and self.current._body:
            # Already rendering part of this response; only resume the tail.
            pass
        else:
            self.current = self.transcript.new_assistant(self.anima_name)
            full = active.get("full_text") or ""
            self.current.set_final(full)
            await self.transcript.mount_assistant(self.current)
            for tool in active.get("tool_history") or []:
                try:
                    card = ToolCard(tool.get("tool_name", "tool"), tool.get("tool_id", ""))
                    if tool.get("input_summary"):
                        card.add_detail(str(tool.get("input_summary")))
                    if tool.get("result_summary"):
                        card.finish(
                            result_summary=tool.get("result_summary"),
                            is_error=bool(tool.get("is_error")),
                        )
                    self.tool_cards[tool.get("tool_id", "")] = card
                    await self.current.add_tool(card)
                except Exception:
                    continue
        self.busy = True
        self.session.in_flight = True
        self.status_bar.set_state(status="streaming", right_hint="resuming stream…")
        self.run_worker(
            self._chat_worker(
                "",
                resume=active.get("response_id"),
                last_event_id=active.get("last_event_id"),
            ),
            group="chat",
            exclusive=True,
            exit_on_error=False,
        )

    async def _render_final(self, active: dict) -> None:
        self.current = self.transcript.new_assistant(self.anima_name)
        self.current.set_final(active.get("full_text") or "")
        await self.transcript.mount_assistant(self.current)

    # ── Command implementations (called by commands.py) ─
    def show_sessions(self) -> None:
        from cli.tui.session import list_sessions

        infos = list_sessions(base_dir=self.session_dir)
        if not infos:
            self.show_transient("No saved sessions.")
            return
        lines = [f"Sessions ({self.session_dir or 'default'}):"]
        for s in infos:
            ts = (s.updated_at or "")[:16].replace("T", " ")
            in_flight = " *" if s.in_flight else ""
            lines.append(f"  {s.session_id}  {ts}  {s.anima}/{s.thread_id}{in_flight}")
        self.show_transient("\n".join(lines))

    def show_keys(self) -> None:
        lines = ["Key bindings:"]
        for key, value in self._keymap.items():
            lines.append(f"  {key:<16} {value}")
        if self._key_warnings:
            for w in self._key_warnings:
                lines.append(f"  (warn) {w}")
        self.show_transient("\n".join(lines))

    def show_animas(self) -> None:
        lines = ["Animas:"]
        for name, row in sorted(self.state.animas.items()):
            mark = "●" if row.busy or row.status in ("busy", "thinking", "streaming") else "○"
            tool = f"  {row.active_tool}" if row.active_tool else ""
            unread = f"  ({row.unread})" if row.unread else ""
            lines.append(f"{mark} {name}  {row.status}{tool}{unread}")
        self.show_transient("\n".join(lines))

    def show_skills(self) -> None:
        self.run_worker(self._show_skills_worker(), group="skills", exit_on_error=False)

    async def _show_skills_worker(self) -> None:
        await self.reload_skills_catalog()
        lines = [f"Skills for {self.anima_name} (thread {self.thread_id}):"]
        for skill in self._skills:
            name = skill.get("name") or skill.get("ref") or "?"
            active = "●" if skill.get("active") else "○"
            marks = []
            if skill.get("is_common"):
                marks.append("common")
            if skill.get("is_procedure"):
                marks.append("procedure")
            mark_s = f" ({', '.join(marks)})" if marks else ""
            desc = (skill.get("description") or "")[:60]
            lines.append(f"{active} {name}{mark_s}: {desc}")
        if not self._skills:
            lines.append("(no skills listed)")
        self.show_transient("\n".join(lines))

    async def reload_skills_catalog(self) -> None:
        """Re-fetch the current anima's skill catalog from the server."""
        list_skills = getattr(self.client, "list_skills", None)
        if list_skills is None:
            return
        try:
            resp = await list_skills(self.anima_name, self.thread_id)
        except Exception:
            return
        self._skills = resp.get("skills") or []
        self._update_skill_count()

    def activate_skill(self, args: list[str]) -> None:
        self.run_worker(
            self._activate_skill_worker(args),
            group="skill",
            exit_on_error=False,
        )

    async def _activate_skill_worker(self, args: list[str]) -> None:
        confirm = "--confirm" in args
        off = "--off" in args
        wanted = next((a for a in args if not a.startswith("--")), "")
        if not wanted:
            self.show_transient("usage: /skill <name> [--confirm] [--off]")
            return
        ref = self._find_skill_ref(wanted)
        if ref is None:
            self.show_transient(f"Unknown skill: {wanted}")
            return
        try:
            active = await self.client.get_active_skills(self.anima_name, thread_id=self.thread_id)
            current_refs = [item.get("ref") for item in active.get("accepted", [])]
        except (AnimaWorksClientError, AttributeError) as exc:
            self.show_transient(f"Could not read active skills: {exc}")
            return
        new_refs = list(current_refs)
        if off:
            if ref in new_refs:
                new_refs.remove(ref)
            else:
                self.show_transient(f"Skill not active: {wanted}")
                return
        else:
            if ref in new_refs:
                self.show_transient(f"Skill already active: {wanted}")
                return
            new_refs.append(ref)
        try:
            result = await self.client.set_active_skills(self.anima_name, self.thread_id, new_refs, confirm)
        except (AnimaWorksClientError, AttributeError) as exc:
            self.show_transient(f"Activation failed: {exc}")
            return
        self._render_skill_result(result, off)
        await self._load_skills()

    def _find_skill_ref(self, name: str) -> str | None:
        for skill in self._skills:
            if skill.get("name") == name or skill.get("ref") == name:
                return skill.get("ref")
        return None

    def _render_skill_result(self, result: dict, off: bool) -> None:
        accepted = result.get("accepted") or []
        rejections = result.get("rejections") or []
        warnings = result.get("warnings") or []
        lines: list[str] = []
        if accepted:
            names = ", ".join(i.get("name") or i.get("ref") or "?" for i in accepted)
            lines.append(f"Accepted: {names}")
        for rej in rejections:
            reason = rej.get("reason") or ""
            hint = " (add --confirm to override)" if "confirm" in reason.lower() else ""
            lines.append(f"Rejected: {rej.get('ref')}: {reason}{hint}")
        for warn in warnings:
            lines.append(f"Warning: {warn.get('name')}: {warn.get('reason')}")
        if not lines:
            lines = ["Skill request processed (no changes)."]
        self.show_transient("\n".join(lines))

    def show_board(self, args: list[str]) -> None:
        self.run_worker(self._board_worker(args), group="board", exit_on_error=False)

    async def _board_worker(self, args: list[str]) -> None:
        if not args:
            try:
                channels = await self.client.list_channels()
            except (AnimaWorksClientError, AttributeError) as exc:
                self.show_transient(f"Could not list channels: {exc}")
                return
            if not channels:
                self.show_transient("No channels.")
                return
            lines = ["Channels:"]
            for ch in channels:
                lines.append(f"  #{ch.get('name')}  ({ch.get('message_count', 0)} messages)")
            self.show_transient("\n".join(lines))
            return
        channel = args[0]
        limit = 20
        if len(args) > 1:
            try:
                limit = int(args[1])
            except ValueError:
                limit = 20
        try:
            resp = await self.client.read_channel(channel, limit=limit)
        except (AnimaWorksClientError, AttributeError) as exc:
            self.show_transient(f"Could not read #{channel}: {exc}")
            return
        messages = resp.get("messages") or []
        if not messages:
            self.show_transient(f"#{channel}: no messages.")
            return
        lines = [f"#{channel} (last {len(messages)}):"]
        for msg in reversed(messages):
            frm = msg.get("from") or "?"
            ts = (msg.get("ts") or "")[11:16]
            text = (msg.get("text") or "")[:120]
            lines.append(f"  {ts} {frm}: {text}")
        self.show_transient("\n".join(lines))

    def post_to_channel(self, args: list[str]) -> None:
        if len(args) < 2:
            self.show_transient("usage: /post <channel> <text>")
            return
        channel = args[0]
        text = " ".join(args[1:])
        self.run_worker(self._post_worker(channel, text), group="post", exit_on_error=False)

    async def _post_worker(self, channel: str, text: str) -> None:
        try:
            await self.client.post_channel(channel, text)
        except (AnimaWorksClientError, AttributeError) as exc:
            self.show_transient(f"Post failed: {exc}")
            return
        self.show_transient(f"Posted to #{channel}.")

    def show_tasks(self, args: list[str]) -> None:
        assignee = args[0] if args else self.anima_name
        self.run_worker(self._tasks_worker(assignee), group="tasks", exit_on_error=False)

    async def _tasks_worker(self, assignee: str) -> None:
        try:
            resp = await self.client.list_tasks(assignee=assignee)
        except (AnimaWorksClientError, AttributeError) as exc:
            self.show_transient(f"Could not load tasks: {exc}")
            return
        tasks = resp.get("tasks") or []
        if not tasks:
            self.show_transient(f"No tasks for {assignee}.")
            return
        lines = [f"Tasks ({assignee}):"]
        for task in tasks:
            title = task.get("title") or task.get("summary") or "?"
            status = task.get("status") or task.get("column") or "?"
            lines.append(f"  [{status}] {title}")
        self.show_transient("\n".join(lines))

    def resolve_interaction(self, args: list[str]) -> None:
        if not args:
            self.show_transient("usage: /approve <callback_id> [option]")
            return
        callback_id = args[0]
        option = args[1] if len(args) > 1 else None
        meta = self._pending_cards.get(callback_id)
        if option is None:
            options = (meta or {}).get("options") or []
            if "approve" in options:
                option = "approve"
            elif options:
                option = options[0]
            else:
                option = "approve"
        anima = meta.get("anima", self.anima_name) if meta else self.anima_name
        self.run_worker(
            self._resolve_worker(anima, callback_id, option),
            group="interact",
            exit_on_error=False,
        )

    async def _resolve_worker(self, anima: str, callback_id: str, option: str) -> None:
        try:
            await self.client.resolve_interaction(anima, callback_id, option)
        except AnimaWorksClientError as exc:
            if "resolved" in str(exc).lower():
                self.show_transient("Already resolved or expired.")
            else:
                self.show_transient(f"Resolve failed: {exc}")
            return
        self._pending_cards.pop(callback_id, None)
        self.show_transient(f"Resolved {callback_id} → {option}.")

    def on_call_human_option(self, message: CallHumanOption) -> None:
        self.resolve_interaction([message.callback_id, message.option])

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
        self.session.in_flight = False
        self._write_session()
        self.status_bar.set_state(
            status="idle",
            active_tool=None,
            right_hint="Esc: interrupt",
        )
        self.show_transient("Interrupted.")

    def _save_on_exit(self) -> None:
        self.session.updated_at = ""
        self._write_session()

    def action_quit_or_confirm(self) -> None:
        now = time.monotonic()
        if now - self._last_ctrlc < 2.0:
            self._save_on_exit()
            self.exit()
        else:
            self._last_ctrlc = now
            self.status_bar.set_state(right_hint="Press Ctrl+C again to quit")

    def action_quit_now(self) -> None:
        self._save_on_exit()
        self.exit()

    def action_scroll_up(self) -> None:
        self.transcript.scroll_up()

    def action_scroll_down(self) -> None:
        self.transcript.scroll_down()


def decide_reattach(active: dict | None, session_in_flight: bool) -> str:
    """Decide how to handle a possibly in-flight stream (pure function).

    ``active`` is the ``/stream/active`` response (``None`` or
    ``{"active": false}`` when there is nothing). Returns one of:

    - ``reattach``      there is an actively streaming response → resume the tail
    - ``render_final``  the stream is complete but we never saw it finish → render once
    - ``lost``          the session says in-flight but the server has nothing
    - ``nothing``       nothing to do
    """
    if not active or not active.get("active"):
        return "lost" if session_in_flight else "nothing"
    status = active.get("status")
    if status == "streaming":
        return "reattach"
    # complete / finished etc.
    return "render_final" if session_in_flight else "nothing"


def _make_runner(handler):
    def run(app) -> None:
        handler([], app)

    return run
