# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time

from core.i18n import t

logger = logging.getLogger("animaworks")


def _is_human_alias(name: str) -> bool:
    """Return True when *name* is a configured human alias."""
    try:
        from core.config.models import load_config

        return name in load_config().external_messaging.user_aliases
    except Exception:
        logger.debug("Could not resolve human aliases for board CLI", exc_info=True)
        return False


# ── Board Read ────────────────────────────────────────────


def cmd_board_read(args: argparse.Namespace) -> None:
    """Read recent messages from a shared channel."""
    from core.init import ensure_runtime_dir
    from core.messenger import Messenger
    from core.paths import get_shared_dir

    ensure_runtime_dir()
    messenger = Messenger(get_shared_dir(), "cli")
    messages = messenger.read_channel(
        args.channel,
        limit=args.limit,
        human_only=args.human_only,
        source="human",
    )
    if not messages:
        print(f"No messages in #{args.channel}")
        return
    print(json.dumps(messages, ensure_ascii=False, indent=2))


# ── Board Post ────────────────────────────────────────────


def cmd_board_post(args: argparse.Namespace) -> None:
    """Post a message to a shared channel."""
    from core.exceptions import ChannelAccessDeniedError, ChannelNotFoundError
    from core.init import ensure_runtime_dir
    from core.messenger import Messenger
    from core.paths import get_shared_dir

    ensure_runtime_dir()
    messenger = Messenger(get_shared_dir(), args.from_anima)
    post_kwargs = {}
    if _is_human_alias(args.from_anima):
        post_kwargs = {"source": "human", "from_name": args.from_anima}
    try:
        posted = messenger.post_channel(args.channel, args.text, **post_kwargs)
    except ChannelNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except ChannelAccessDeniedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if posted is False:
        print(f"Post denied or failed for #{args.channel}")
        return
    print(f"Posted to #{args.channel}")

    # Mention fanout
    _fanout_board_mentions(messenger, args.from_anima, args.channel, args.text)

    # Notify running server (silent failure)
    _notify_server_board_posted(
        args.from_anima,
        args.channel,
        args.text,
        source=post_kwargs.get("source", "anima"),
    )


# ── Board DM History ──────────────────────────────────────


def cmd_board_dm_history(args: argparse.Namespace) -> None:
    """Read DM history with a specific peer."""
    from core.init import ensure_runtime_dir
    from core.messenger import Messenger
    from core.paths import get_shared_dir

    ensure_runtime_dir()
    messenger = Messenger(get_shared_dir(), args.from_anima)
    messages = messenger.read_dm_history(args.peer, limit=args.limit)
    if not messages:
        print(f"No DM history with {args.peer}")
        return
    print(json.dumps(messages, ensure_ascii=False, indent=2))


# ── Mention Fanout ────────────────────────────────────────


def _fanout_board_mentions(
    messenger: Messenger,  # noqa: F821
    from_anima: str,
    channel: str,
    text: str,
) -> None:
    """Send DM notifications to mentioned Animas.

    Replicates the fanout logic from core/tooling/handler.py
    so that CLI board posts trigger the same @mention notifications
    as tool_use-based posts.
    """
    mentions = re.findall(r"@(\w+)", text)
    if not mentions:
        return

    is_all = "all" in mentions

    # Determine running Animas via socket files
    from core.paths import get_data_dir

    sockets_dir = get_data_dir() / "run" / "sockets"
    if sockets_dir.exists():
        running = {p.stem for p in sockets_dir.glob("*.sock")}
    else:
        running = set()

    if is_all:
        targets = running - {from_anima}
    else:
        named = {m for m in mentions if m != "all"}
        targets = (named & running) - {from_anima}

    if not targets:
        return

    fanout_content = f"[board_reply:channel={channel},from={from_anima}]\n" + t(
        "handler.board_mention_content", from_name=from_anima, channel=channel, text=text
    )

    for target in sorted(targets):
        try:
            messenger.send(
                to=target,
                content=fanout_content,
                msg_type="board_mention",
            )
            logger.info(
                "board_mention fanout: %s -> %s (channel=%s)",
                from_anima,
                target,
                channel,
            )
        except Exception:
            logger.warning(
                "Failed to fanout board_mention to %s",
                target,
                exc_info=True,
            )


# ── Server Notification ───────────────────────────────────


def _notify_server_board_posted(
    from_anima: str,
    channel: str,
    text: str,
    *,
    source: str = "anima",
) -> None:
    """Notify the running server about a CLI board post.

    Fails silently if the server is not running.
    """
    from cli.commands.server import _is_process_alive, _read_pid

    pid = _read_pid()
    if pid is None or not _is_process_alive(pid):
        return

    server_url = os.environ.get("ANIMAWORKS_SERVER_URL", "http://localhost:18500")
    import httpx

    payload = {
        "from_person": from_anima,
        "to_person": f"#channel:{channel}",
        "content": text[:200],
        "source": source,
    }
    for attempt in range(5):
        try:
            resp = httpx.post(
                f"{server_url}/api/internal/message-sent",
                json=payload,
                timeout=5.0,
            )
            if resp.status_code == 200:
                logger.debug("Server notified of CLI board post: %s -> #%s", from_anima, channel)
                return
            logger.debug("Server notification failed: %s", resp.status_code)
        except Exception:
            logger.debug("Could not notify server of CLI board post", exc_info=True)
        if attempt < 4:
            time.sleep(1.0)
