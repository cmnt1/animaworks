# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""SQLite message cache for Chatwork offline search and unreplied detection."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from core.exceptions import ToolConfigError
from core.integrations._cache import BaseMessageCache, CacheTable
from core.integrations._chatwork_client import JST, ChatworkClient
from core.platform.atomic_io import atomic_write_json

logger = logging.getLogger("animaworks.tools.chatwork.cache")

# ── Constants ──────────────────────────────────────────────

# Cache directory for Chatwork message cache.
# Can be overridden via ANIMAWORKS_CHATWORK_CACHE_DIR environment variable.
# This allows TaskExec/Codex sandbox environments to redirect cache writes
# to a writable location (e.g. /tmp/animaworks-cache/chatwork).
_DEFAULT_CACHE_DIR = Path.home() / ".animaworks" / "cache" / "chatwork"
DEFAULT_CACHE_DIR = Path(os.environ.get("ANIMAWORKS_CHATWORK_CACHE_DIR", str(_DEFAULT_CACHE_DIR)))

_CHATWORK_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS rooms (
    room_id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT,
    room_id TEXT,
    account_id TEXT,
    account_name TEXT,
    body TEXT,
    send_time INTEGER,
    send_time_jst TEXT,
    PRIMARY KEY (room_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_body ON messages(body);
CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(send_time);
CREATE TABLE IF NOT EXISTS sync_state (
    room_id TEXT PRIMARY KEY,
    last_synced TEXT
);
"""


_CHATWORK_ROOMS_TABLE = CacheTable(
    name="rooms",
    columns=("room_id", "name", "type", "updated_at"),
    primary_key=("room_id",),
)
_CHATWORK_MESSAGES_TABLE = CacheTable(
    name="messages",
    columns=("message_id", "room_id", "account_id", "account_name", "body", "send_time", "send_time_jst"),
    primary_key=("room_id", "message_id"),
    search_column="m.body",
    scope_column="m.room_id",
    order_by="m.send_time",
    from_clause="messages m LEFT JOIN rooms r ON m.room_id = r.room_id",
    select_columns="m.*, r.name as room_name",
)
_CHATWORK_SYNC_STATE_TABLE = CacheTable(
    name="sync_state",
    columns=("room_id", "last_synced"),
    primary_key=("room_id",),
)


# ── Helpers ──────────────────────────────────────────────────


def _format_timestamp(unix_ts: int) -> str:
    return datetime.fromtimestamp(unix_ts, tz=JST).strftime("%Y-%m-%d %H:%M")


def resolve_cache_db_path(client: ChatworkClient) -> Path:
    """Return the account-specific cache DB path for *client*."""
    try:
        DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # A read-only sandbox must not turn a cache miss into a hard failure
        # here; the caller still fails loudly if the DB itself is unusable.
        logger.warning("Chatwork cache directory is not writable (%s): %s", DEFAULT_CACHE_DIR, exc)
    map_path = DEFAULT_CACHE_DIR / "identity_map.json"
    token_fingerprint = hashlib.sha256(client.api_token.encode("utf-8")).hexdigest()[:16]

    identity_map: dict[str, str] = {}
    if map_path.exists():
        try:
            raw_map = json.loads(map_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ToolConfigError(f"Chatwork identity cache could not be read: {exc}") from exc
        if not isinstance(raw_map, dict):
            raise ToolConfigError("Chatwork identity cache must contain a JSON object")
        identity_map = {str(key): str(value) for key, value in raw_map.items()}

    account_id = identity_map.get(token_fingerprint)
    if account_id is None:
        me = client.me()
        account_id = str(me["account_id"])
        identity_map[token_fingerprint] = account_id
        try:
            atomic_write_json(map_path, identity_map, indent=2, ensure_ascii=False, sort_keys=True)
        except OSError as exc:
            # The account id was just resolved from the API, so the lookup can
            # proceed uncached instead of blocking every Chatwork read.
            logger.warning("Chatwork identity cache could not be updated (%s): %s", map_path, exc)

    return DEFAULT_CACHE_DIR / account_id / "messages.db"


# ── MessageCache ─────────────────────────────────────────────


class MessageCache(BaseMessageCache):
    """SQLite-backed cache for Chatwork messages, enabling offline search and
    unreplied-mention detection."""

    def __init__(self, db_path: Path):
        super().__init__(db_path, _CHATWORK_SCHEMA_SQL)

    def upsert_room(self, room: dict):
        self.upsert_rooms([room])

    def upsert_rooms(self, rooms: list[dict]):
        """Upsert room metadata in one transaction.

        One commit per room (600+ rooms, fsync each) held the exclusive lock
        for 10s+ and starved every other collector sharing the cache.
        """
        now = datetime.now(JST).isoformat()
        self.upsert_records(
            _CHATWORK_ROOMS_TABLE,
            [
                {
                    "room_id": str(room["room_id"]),
                    "name": room["name"],
                    "type": room.get("type", ""),
                    "updated_at": now,
                }
                for room in rooms
            ],
        )

    def upsert_messages(self, room_id: str, messages: list[dict]):
        def _records():
            for message in messages:
                send_time = message.get("send_time", 0)
                dt = datetime.fromtimestamp(send_time, tz=JST)
                account = message.get("account", {})
                yield {
                    "message_id": str(message["message_id"]),
                    "room_id": str(room_id),
                    "account_id": str(account.get("account_id", "")),
                    "account_name": account.get("name", ""),
                    "body": message.get("body", ""),
                    "send_time": send_time,
                    "send_time_jst": dt.strftime("%Y-%m-%d %H:%M:%S"),
                }

        self.upsert_records(_CHATWORK_MESSAGES_TABLE, _records())

    def update_sync_state(self, room_id: str):
        self.upsert_records(
            _CHATWORK_SYNC_STATE_TABLE,
            [{"room_id": room_id, "last_synced": datetime.now(JST).isoformat()}],
        )

    def search(
        self,
        keyword: str,
        room_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        return self.search_records(
            _CHATWORK_MESSAGES_TABLE,
            keyword,
            scope_value=room_id,
            limit=limit,
        )

    def get_recent(self, room_id: str, limit: int = 20) -> list[dict]:
        return self.get_recent_records(_CHATWORK_MESSAGES_TABLE, room_id, limit=limit)

    def get_room_name(self, room_id: str) -> str:
        row = self.conn.execute("SELECT name FROM rooms WHERE room_id = ?", (room_id,)).fetchone()
        return row["name"] if row else room_id

    def _get_personal_room_ids(self, config: dict) -> set[str]:
        """Return room IDs for DMs + watch_rooms from config."""
        personal: set[str] = set()
        unreplied_cfg = config.get("unreplied", {})

        # type=direct rooms from DB
        if unreplied_cfg.get("include_direct_messages", True):
            rows = self.conn.execute("SELECT room_id FROM rooms WHERE type = 'direct'").fetchall()
            personal.update(str(r["room_id"]) for r in rows)

        # Explicitly watched rooms
        for wr in unreplied_cfg.get("watch_rooms", []):
            personal.add(str(wr["room_id"]))

        return personal

    def find_mentions(
        self,
        my_account_id: str,
        exclude_toall: bool = True,
        limit: int = 200,
        config: dict | None = None,
    ) -> list[dict]:
        """Find messages addressed to me.

        - Group rooms: messages containing [To:my_id]
        - DM / watch_rooms: all messages from other people (no [To:] needed)
        """
        if config is None:
            config = {}
        personal_rooms = self._get_personal_room_ids(config)

        results: list[dict] = []
        seen: set[tuple[str, str]] = set()

        # 1) Normal [To:my_id] mentions (all rooms)
        to_tag = f"%[To:{my_account_id}]%"
        query = """
            SELECT m.*, r.name as room_name
            FROM messages m
            LEFT JOIN rooms r ON m.room_id = r.room_id
            WHERE m.body LIKE ?
              AND m.account_id != ?
        """
        params: list = [to_tag, my_account_id]
        if exclude_toall:
            query += " AND m.body NOT LIKE '%[toall]%'"
        query += " ORDER BY m.send_time DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        for r in rows:
            d = dict(r)
            key = (d["room_id"], d["message_id"])
            if key not in seen:
                seen.add(key)
                results.append(d)

        # 2) DM / watch_rooms: all messages from others
        if personal_rooms:
            placeholders = ",".join("?" for _ in personal_rooms)
            query2 = f"""
                SELECT m.*, r.name as room_name
                FROM messages m
                LEFT JOIN rooms r ON m.room_id = r.room_id
                WHERE m.room_id IN ({placeholders})
                  AND m.account_id != ?
                ORDER BY m.send_time DESC LIMIT ?
            """
            params2 = list(personal_rooms) + [my_account_id, limit]
            rows2 = self.conn.execute(query2, params2).fetchall()
            for r in rows2:
                d = dict(r)
                key = (d["room_id"], d["message_id"])
                if key not in seen:
                    seen.add(key)
                    results.append(d)

        # Sort by time descending
        results.sort(key=lambda x: x.get("send_time", 0), reverse=True)
        return results[:limit]

    def find_unreplied(
        self,
        my_account_id: str,
        exclude_toall: bool = True,
        limit: int = 200,
        config: dict | None = None,
    ) -> list[dict]:
        """Find messages addressed to me that I haven't replied to."""
        mentions = self.find_mentions(my_account_id, exclude_toall, limit, config=config)
        unreplied = []
        for m in mentions:
            # Check if I have sent any message in this room after this one
            row = self.conn.execute(
                """SELECT COUNT(*) as c FROM messages
                   WHERE room_id = ? AND account_id = ? AND send_time > ?""",
                (m["room_id"], my_account_id, m["send_time"]),
            ).fetchone()
            if row["c"] == 0:
                unreplied.append(m)
        return unreplied

    def get_stats(self) -> dict:
        """Return cache statistics."""
        rooms = self.conn.execute("SELECT COUNT(*) as c FROM rooms").fetchone()["c"]
        msgs = self.conn.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
        return {"rooms": rooms, "messages": msgs}
