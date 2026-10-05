# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Shared SQLite message cache base class for communication tools."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Several collectors (5-min mention watch, 15-min unreplied tracker, heartbeat
# sessions) sync the same cache concurrently.  In DELETE journal mode every
# commit takes the exclusive lock, so a sibling process must wait longer than
# sqlite's 5s default or it dies with "database is locked".
BUSY_TIMEOUT_S = 30.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CacheTable:
    """Static table metadata used by the shared cache CRUD helpers."""

    name: str
    columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    search_column: str | None = None
    scope_column: str | None = None
    order_by: str | None = None
    from_clause: str | None = None
    select_columns: str = "*"

    def __post_init__(self) -> None:
        if not self.primary_key or not set(self.primary_key).issubset(self.columns):
            raise ValueError(f"Cache table {self.name!r} must declare its primary-key columns")


# ── BaseMessageCache ───────────────────────────────────────


class BaseMessageCache:
    """SQLite-backed message cache base class.

    Provides common database lifecycle management, row mapping, and
    table-driven upsert/search/recent-message queries. Subclasses supply
    their schema SQL, table metadata, and domain-specific query methods.

    Args:
        db_path: Path to the SQLite database file.  Parent directories
            are created automatically.
        schema_sql: SQL script executed once at initialisation to
            create tables and indexes.
    """

    def __init__(self, db_path: Path, schema_sql: str) -> None:
        self.db_path = db_path
        self.readonly = False
        conn: sqlite3.Connection | None = None
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path), timeout=BUSY_TIMEOUT_S)
            # DELETE, not WAL: sandboxed animas mount the cache dir read-only
            # (write-access charter) and a WAL database cannot even be *read*
            # there, because SQLite must create a -shm file alongside it.
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.executescript(schema_sql)
            conn.commit()
        except (OSError, sqlite3.OperationalError) as exc:
            if conn is not None:
                conn.close()
            if not db_path.exists():
                raise
            # The cron collectors keep this cache fresh outside the sandbox,
            # so read-only access still answers search/unreplied/mentions.
            # Writes fail loudly on this connection -- never silently.
            logger.warning("Cache DB %s is not writable, opening read-only: %s", db_path, exc)
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=BUSY_TIMEOUT_S)
            self.readonly = True
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # ── Lifecycle ──────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    # ── Shared helpers ─────────────────────────────────────

    def _fetchall_dicts(self, query: str, params: list | tuple = ()) -> list[dict]:
        """Execute *query* and return rows as plain dicts."""
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def upsert_records(
        self,
        table: CacheTable,
        records: Iterable[Mapping[str, Any]],
        *,
        commit: bool = True,
    ) -> None:
        """Insert or replace rows using the declared table columns."""
        columns = ", ".join(table.columns)
        placeholders = ", ".join("?" for _ in table.columns)
        query = f"INSERT OR REPLACE INTO {table.name} ({columns}) VALUES ({placeholders})"  # noqa: S608
        self.conn.executemany(query, (tuple(record[column] for column in table.columns) for record in records))
        if commit:
            self.conn.commit()

    def search_records(
        self,
        table: CacheTable,
        keyword: str,
        *,
        scope_value: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search a message table by LIKE substring, with optional scope."""
        if table.search_column is None or table.order_by is None:
            raise ValueError(f"Cache table {table.name!r} is not searchable")
        from_clause = table.from_clause or table.name
        query = f"SELECT {table.select_columns} FROM {from_clause} WHERE {table.search_column} LIKE ?"  # noqa: S608
        params: list[Any] = [f"%{keyword}%"]
        if scope_value:
            if table.scope_column is None:
                raise ValueError(f"Cache table {table.name!r} has no scope column")
            query += f" AND {table.scope_column} = ?"  # noqa: S608
            params.append(scope_value)
        query += f" ORDER BY {table.order_by} DESC LIMIT ?"  # noqa: S608
        params.append(limit)
        return self._fetchall_dicts(query, params)

    def get_recent_records(
        self,
        table: CacheTable,
        scope_value: str,
        *,
        limit: int = 50,
    ) -> list[dict]:
        """Return the newest rows for one scope from a message table."""
        if table.scope_column is None or table.order_by is None:
            raise ValueError(f"Cache table {table.name!r} has no recent-message query metadata")
        from_clause = table.from_clause or table.name
        query = (
            f"SELECT {table.select_columns} FROM {from_clause} "
            f"WHERE {table.scope_column} = ? ORDER BY {table.order_by} DESC LIMIT ?"
        )  # noqa: S608
        return self._fetchall_dicts(query, (scope_value, limit))

    def get_stats(self) -> dict:
        """Return basic cache statistics.

        Subclasses may override to add domain-specific stats.
        """
        tables = self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        stats: dict[str, int] = {}
        for (tbl_name,) in tables:
            if tbl_name.startswith("sqlite_"):
                continue
            count = self.conn.execute(
                f"SELECT COUNT(*) FROM [{tbl_name}]"  # noqa: S608
            ).fetchone()[0]
            stats[tbl_name] = count
        return stats
