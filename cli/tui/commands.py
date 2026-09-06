# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Handler signature: called with ``(args, app)`` where ``app`` is the
# running ``AnimaChatApp`` instance (duck-typed, so no import needed).
CommandHandler = Callable[[list[str], Any], None]


@dataclass
class SlashCommand:
    """A single slash command registered for the chat input.

    ``name`` is the command without the leading ``/`` (e.g. ``"help"``).
    ``handler`` receives the list of arguments and the running app.
    Commands can be added later by appending to :func:`register`.
    """

    name: str
    description: str
    handler: CommandHandler

    @property
    def signature(self) -> str:
        return f"/{self.name}"


def _cmd_help(_args: list[str], app: Any) -> None:
    lines = ["Available commands:"]
    for cmd in list_commands():
        lines.append(f"  {cmd.signature:<12} {cmd.description}")
    lines.append("  Esc            interrupt the current response")
    lines.append("  Ctrl+C (x2)    quit")
    app.show_transient("\n".join(lines))


def _cmd_quit(_args: list[str], app: Any) -> None:
    app.exit()


def _cmd_clear(_args: list[str], app: Any) -> None:
    app.clear_transcript()


def _cmd_thinking(_args: list[str], app: Any) -> None:
    app.toggle_thinking()


def _cmd_interrupt(_args: list[str], app: Any) -> None:
    app.request_interrupt()


def _cmd_history(args: list[str], app: Any) -> None:
    try:
        limit = int(args[0]) if args else 20
    except ValueError:
        limit = 20
    app.reload_history(limit=limit)


_registry: dict[str, SlashCommand] = {}


def register_default_commands() -> None:
    """Register the Phase 1 built-in slash commands (idempotent)."""
    if _registry:
        return
    for cmd in (
        SlashCommand("help", "Show available commands", _cmd_help),
        SlashCommand("quit", "Quit the TUI", _cmd_quit),
        SlashCommand("clear", "Clear the transcript", _cmd_clear),
        SlashCommand("thinking", "Toggle thinking display", _cmd_thinking),
        SlashCommand("interrupt", "Stop the current response", _cmd_interrupt),
        SlashCommand("history", "Reload conversation history [n]", _cmd_history),
    ):
        _registry[cmd.name] = cmd


def get_command(name: str) -> SlashCommand | None:
    register_default_commands()
    return _registry.get(name)


def list_commands() -> list[SlashCommand]:
    register_default_commands()
    return list(_registry.values())


def is_command(text: str) -> bool:
    """Return True if the trimmed input looks like a slash command."""
    return text.startswith("/")
