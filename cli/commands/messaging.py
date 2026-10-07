# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import sys

from cli._anima_tool import current_anima_dir, run_and_print
from core.tooling.standalone import notify_server_message_sent

# ── Send ───────────────────────────────────────────────────


def cmd_send(args: argparse.Namespace) -> None:
    """Send a message through ToolHandler for Animas or Messenger for operators."""
    anima_dir = current_anima_dir()
    if anima_dir is not None:
        if args.from_person != anima_dir.name:
            print(
                f"Error: anima '{anima_dir.name}' cannot send as '{args.from_person}'",
                file=sys.stderr,
            )
            raise SystemExit(1)

        run_and_print(
            "send_message",
            {
                "to": args.to_person,
                "content": args.message,
                "intent": getattr(args, "intent", "") or "",
                "thread_id": args.thread_id or "",
                "reply_to": args.reply_to or "",
            },
        )
        return

    # Human/operator use remains a small Messenger path; only anima tool calls
    # are required to pass through ToolHandler.
    from core.infra.runtime_init import ensure_runtime_dir
    from core.messaging.messenger import Messenger
    from core.messaging.sender import resolve_sender_source
    from core.paths import get_shared_dir

    ensure_runtime_dir()
    source = resolve_sender_source(args.from_person)
    messenger = Messenger(get_shared_dir(), args.from_person)
    msg = messenger.send(
        to=args.to_person,
        content=args.message,
        thread_id=args.thread_id or "",
        reply_to=args.reply_to or "",
        intent=getattr(args, "intent", "") or "",
        source=source,
    )
    sender_label = msg.from_person if source == "anima" else f"{msg.from_person} (human)"
    print(f"Sent: {sender_label} -> {msg.to_person} (id: {msg.id}, thread: {msg.thread_id})")
    _notify_server_message_sent(args.from_person, args.to_person, args.message, msg.id)


def _notify_server_message_sent(
    from_anima: str,
    to_anima: str,
    content: str,
    message_id: str = "",
) -> None:
    """Keep operator sends' server notification on the shared core path."""
    notify_server_message_sent(from_anima, to_anima, content, message_id)


# ── Status ─────────────────────────────────────────────────


def cmd_status(args: argparse.Namespace) -> None:
    """Show system status."""
    from cli._gateway import gateway_request

    data = gateway_request(args, "GET", "/api/system/status", timeout=10.0)
    if isinstance(data, dict):
        print(f"Animas: {data.get('animas', 0)}")
        print(f"Scheduler: {'running' if data.get('scheduler_running') else 'stopped'}")
        for j in data.get("jobs", []):
            print(f"  [{j['id']}] {j['name']} -> next: {j['next_run']}")
    else:
        print(data)
