# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Debate threads: Discord threads where several Animas discuss one record.

An external job (Finance "Market Now") runs a scripted debate in a Discord
thread, writes the full record under ``common_knowledge/`` and registers the
thread in ``shared/discord_debate_threads.json``::

    {"<thread_id>": {"participants": ["airi", "rika", "momoka", "sakura"],
                     "record": "common_knowledge/market_now/20261009-141134.md",
                     "title": "Market Now 10/09 14:11", "expires_at": "<iso>"}}

Inside a registered thread the gateway routes differently:

* A human message reaches every participant. The Animas the human addressed
  (reply target / named, else the normal fallback) must answer; the others
  answer only if their role gives them something to add, otherwise they
  output ``[[PASS]]`` (suppressed by the auto-responder).
* An Anima's post that names another participant reaches that participant,
  up to ``MAX_ANIMA_TURNS`` Anima posts per human message.
* Every post is appended to the record, so it stays the full transcript.

Inbox delivery truncates bodies to ~2000 characters, so each delivery carries
a compact digest of the latest messages plus the record path to read first.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REGISTRY_NAME = "discord_debate_threads.json"
PASS_TOKEN = "[[PASS]]"
MAX_ANIMA_TURNS = 4
HISTORY_MESSAGES = 6
HISTORY_LINE_CHARS = 180
BODY_CHARS = 700
MAX_DELIVERY_CHARS = 1800  # inbox keeps ~2000 chars of a message body

_turns: dict[str, int] = {}
_turns_lock = threading.Lock()
_record_lock = threading.Lock()


def _shared_dir() -> Path:
    from core.paths import get_shared_dir

    return get_shared_dir()


def _common_knowledge_dir() -> Path:
    from core.paths import get_common_knowledge_dir

    return get_common_knowledge_dir()


def load_entry(thread_id: str, *, now: datetime | None = None, shared_dir: Path | None = None) -> dict | None:
    """The live registry entry for *thread_id*, or None (absent / expired / unreadable)."""
    path = (shared_dir or _shared_dir()) / REGISTRY_NAME
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        logger.warning("Debate thread registry unreadable: %s", path, exc_info=True)
        return None
    entry = registry.get(str(thread_id)) if isinstance(registry, dict) else None
    if not isinstance(entry, dict) or not entry.get("participants"):
        return None
    try:
        expires = datetime.fromisoformat(str(entry.get("expires_at")))
    except ValueError:
        return None
    if expires <= (now or datetime.now(UTC)):
        return None
    return entry


def record_path(entry: dict, *, ck_dir: Path | None = None) -> Path | None:
    rel = str(entry.get("record") or "")
    if not rel.startswith("common_knowledge/"):
        return None
    base = ck_dir or _common_knowledge_dir()
    path = (base / rel[len("common_knowledge/") :]).resolve()
    return path if path.is_relative_to(base.resolve()) else None


def append_to_record(entry: dict, author: str, text: str, *, ck_dir: Path | None = None) -> None:
    path = record_path(entry, ck_dir=ck_dir)
    if path is None or not path.exists():
        return
    stamp = datetime.now().astimezone().strftime("%m/%d %H:%M")
    with _record_lock, path.open("a", encoding="utf-8") as f:
        f.write(f"\n### {author}（Discord {stamp}）\n{text.strip()}\n")


def start_human_turn(thread_id: str) -> None:
    with _turns_lock:
        _turns[str(thread_id)] = 0


def take_anima_turn(thread_id: str) -> bool:
    """Count one Anima post; False once the per-human-message budget is spent."""
    with _turns_lock:
        used = _turns.get(str(thread_id), 0)
        if used >= MAX_ANIMA_TURNS:
            return False
        _turns[str(thread_id)] = used + 1
        return True


def build_delivery(
    entry: dict,
    *,
    target: str,
    required: bool,
    author: str,
    text: str,
    history: list[tuple[str, str]],
) -> str:
    """Inbox body for one participant (kept under the ~2000 char inbox budget)."""
    lines = [
        f"[discord:議論スレッド「{entry.get('title') or ''}」]",
        f"【議論の記録】{entry.get('record')} を最初に read_memory_file で読むこと。"
        "分析・取得値・イベント・これまでの議論の全文がある（新しい発言は末尾に追記される）。",
    ]
    if required:
        lines.append(f"【あなた（{target}）の立場】宛先なので、記録を踏まえて必ず答える。")
    else:
        lines.append(
            f"【あなた（{target}）の立場】名指しされていない。あなたの役割から新しい論点・訂正・補足が"
            f"あるときだけ答える。なければ何も書かずに {PASS_TOKEN} とだけ出力する。"
        )
    lines.append("他の参加者に問いたいときは、本文でその名前を呼べば相手に届く。")
    tail = [f"【今回の発言（{author}）】", " ".join(text.split())[:BODY_CHARS]]
    # Newest history lines first, as many as fit; the record has the rest.
    room = MAX_DELIVERY_CHARS - len("\n".join([*lines, *tail])) - len("【直近の流れ（古い順）】") - 1
    picked: list[str] = []
    for name, body in reversed(history[-HISTORY_MESSAGES:]):
        line = f"- {name}: {' '.join(body.split())[:HISTORY_LINE_CHARS]}"
        if len(line) + 1 > room:
            break
        picked.insert(0, line)
        room -= len(line) + 1
    if picked:
        lines += ["【直近の流れ（古い順）】", *picked]
    return "\n".join([*lines, *tail])


def plan_human_deliveries(entry: dict, addressed: list[str]) -> list[tuple[str, bool]]:
    """(participant, required) for a human message; addressed ones first."""
    participants = [str(p) for p in entry.get("participants") or []]
    required = [a for a in addressed if a in participants]
    return [(p, True) for p in required] + [(p, False) for p in participants if p not in required]


def plan_anima_deliveries(entry: dict, author: str, named: list[str]) -> list[tuple[str, bool]]:
    """Participants named by an Anima's post (never the author itself)."""
    participants = [str(p) for p in entry.get("participants") or []]
    seen: list[str] = []
    for name in named:
        if name in participants and name != author and name not in seen:
            seen.append(name)
    return [(name, True) for name in seen]


async def recent_history(channel: Any, *, before_id: int | None = None) -> list[tuple[str, str]]:
    """Last few thread messages as (author, text), oldest first. Never raises."""
    items: list[tuple[str, str]] = []
    try:
        kwargs: dict[str, Any] = {"limit": HISTORY_MESSAGES}
        if before_id is not None:
            import discord  # type: ignore

            kwargs["before"] = discord.Object(id=before_id)
        async for msg in channel.history(**kwargs):
            name = msg.author.display_name or msg.author.name
            items.append((name, msg.content or ""))
    except Exception:
        logger.debug("Debate thread history fetch failed", exc_info=True)
    return list(reversed(items))
