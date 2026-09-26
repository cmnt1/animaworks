"""The Chatwork cache is shared by several collectors running concurrently
(5-min mention watch, 15-min unreplied tracker, heartbeat sessions).  With a
DELETE journal every commit takes the exclusive lock, so the cache must (a) not
commit once per room and (b) wait longer than sqlite's 5s default before giving
up with "database is locked"."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from core.tools import _cache
from core.tools._chatwork_cache import MessageCache

ROOMS = [{"room_id": i, "name": f"room-{i}", "type": "group"} for i in range(50)]


def test_connect_uses_long_busy_timeout(tmp_path: Path, monkeypatch) -> None:
    seen: list[float | None] = []
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        seen.append(kwargs.get("timeout"))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(_cache.sqlite3, "connect", spy)
    MessageCache(tmp_path / "messages.db").close()
    assert seen and all(t == _cache.BUSY_TIMEOUT_S for t in seen)
    assert _cache.BUSY_TIMEOUT_S >= 30


def test_upsert_rooms_is_one_transaction(tmp_path: Path) -> None:
    cache = MessageCache(tmp_path / "messages.db")
    statements: list[str] = []
    cache.conn.set_trace_callback(statements.append)
    cache.upsert_rooms(ROOMS)
    cache.conn.set_trace_callback(None)
    assert sum(1 for st in statements if st.strip().upper() == "COMMIT") == 1
    assert not cache.conn.in_transaction
    assert cache.conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == len(ROOMS)
    cache.close()


def test_upsert_room_still_works_for_a_single_room(tmp_path: Path) -> None:
    cache = MessageCache(tmp_path / "messages.db")
    cache.upsert_room({"room_id": 1, "name": "solo"})
    cache.upsert_room({"room_id": 1, "name": "solo-renamed"})
    rows = cache.conn.execute("SELECT room_id, name FROM rooms").fetchall()
    assert [(r["room_id"], r["name"]) for r in rows] == [("1", "solo-renamed")]
    cache.close()


def test_writer_outlives_a_short_foreign_lock(tmp_path: Path) -> None:
    """A sibling holding the write lock briefly must delay us, not kill us."""
    db = tmp_path / "messages.db"
    MessageCache(db).close()
    holder = sqlite3.connect(str(db), check_same_thread=False)
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO rooms (room_id, name, type, updated_at) VALUES ('x','x','','')")
    threading.Timer(1.0, holder.commit).start()
    cache = MessageCache(db)
    cache.upsert_rooms(ROOMS)  # waits ~1s for the holder instead of failing
    assert cache.conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == len(ROOMS) + 1
    cache.close()
    holder.close()
