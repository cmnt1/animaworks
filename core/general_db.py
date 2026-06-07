# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared general database helpers."""

from __future__ import annotations

import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.paths import get_shared_dir

ABCONFIG_DIR = Path(r"E:\OneDriveBiz\Tools\abconfig")
GENERAL_DB_NAME = "general_db"
SNS_SEARCH_TABLE = "dbo.T_Sns_Search"


def get_general_db_path() -> Path:
    """Return the shared general database path."""
    return get_shared_dir() / "general_db.sqlite3"


@dataclass(frozen=True)
class SnsSearchEntry:
    ID_Sns_Search: int
    Division: str
    Words: str

    def to_dict(self) -> dict[str, int | str]:
        return {
            "ID_Sns_Search": self.ID_Sns_Search,
            "Division": self.Division,
            "Words": self.Words,
        }


class SnsSearchStore:
    """CRUD store for general_db.T_Sns_Search."""

    def __init__(self, db_path: Path | None = None, engine: Any | None = None) -> None:
        self.db_path = db_path
        self.engine = engine
        if self.db_path is None and self.engine is None:
            self.engine = _create_general_db_engine()
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:
            raise RuntimeError("SQLite db_path is not configured")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        if self.engine is not None:
            self._ensure_sql_server_schema()
            return
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS T_Sns_Search (
                    ID_Sns_Search INTEGER PRIMARY KEY AUTOINCREMENT,
                    Division TEXT NOT NULL,
                    Words TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS IX_T_Sns_Search_Division
                ON T_Sns_Search (Division)
                """
            )

    def _ensure_sql_server_schema(self) -> None:
        from sqlalchemy import text

        schema_sql = f"""
        IF OBJECT_ID(N'{SNS_SEARCH_TABLE}', N'U') IS NULL
        BEGIN
            CREATE TABLE {SNS_SEARCH_TABLE} (
                ID_Sns_Search INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                Division NVARCHAR(100) NOT NULL,
                Words NVARCHAR(MAX) NOT NULL
            );
        END;
        IF NOT EXISTS (
            SELECT 1
            FROM sys.indexes
            WHERE name = N'IX_T_Sns_Search_Division'
              AND object_id = OBJECT_ID(N'{SNS_SEARCH_TABLE}')
        )
        BEGIN
            CREATE INDEX IX_T_Sns_Search_Division
            ON {SNS_SEARCH_TABLE} (Division);
        END;
        """
        with self.engine.begin() as conn:
            conn.execute(text(schema_sql))

    def list_entries(self) -> list[SnsSearchEntry]:
        if self.engine is not None:
            from sqlalchemy import text

            with self.engine.connect() as conn:
                rows = (
                    conn.execute(
                        text(
                            f"""
                        SELECT ID_Sns_Search, Division, Words
                        FROM {SNS_SEARCH_TABLE}
                        ORDER BY Division, ID_Sns_Search
                        """
                        )
                    )
                    .mappings()
                    .all()
                )
            return [_entry_from_mapping(row) for row in rows]

        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT ID_Sns_Search, Division, Words
                FROM T_Sns_Search
                ORDER BY Division COLLATE NOCASE, ID_Sns_Search
                """
            ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def create_entry(self, division: str, words: str) -> SnsSearchEntry:
        division = _clean_required(division, "Division")
        words = _clean_required(words, "Words")
        if self.engine is not None:
            from sqlalchemy import text

            with self.engine.begin() as conn:
                row = (
                    conn.execute(
                        text(
                            f"""
                        INSERT INTO {SNS_SEARCH_TABLE} (Division, Words)
                        OUTPUT INSERTED.ID_Sns_Search, INSERTED.Division, INSERTED.Words
                        VALUES (:division, :words)
                        """
                        ),
                        {"division": division, "words": words},
                    )
                    .mappings()
                    .first()
                )
            if row is None:
                raise RuntimeError("Failed to read inserted T_Sns_Search row")
            return _entry_from_mapping(row)

        with self._connection() as conn:
            cur = conn.execute(
                "INSERT INTO T_Sns_Search (Division, Words) VALUES (?, ?)",
                (division, words),
            )
            entry_id = int(cur.lastrowid)
            row = conn.execute(
                """
                SELECT ID_Sns_Search, Division, Words
                FROM T_Sns_Search
                WHERE ID_Sns_Search = ?
                """,
                (entry_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to read inserted T_Sns_Search row")
        return _entry_from_row(row)

    def update_entry(self, entry_id: int, division: str, words: str) -> SnsSearchEntry | None:
        division = _clean_required(division, "Division")
        words = _clean_required(words, "Words")
        if self.engine is not None:
            from sqlalchemy import text

            with self.engine.begin() as conn:
                row = (
                    conn.execute(
                        text(
                            f"""
                        UPDATE {SNS_SEARCH_TABLE}
                        SET Division = :division, Words = :words
                        OUTPUT INSERTED.ID_Sns_Search, INSERTED.Division, INSERTED.Words
                        WHERE ID_Sns_Search = :entry_id
                        """
                        ),
                        {"entry_id": int(entry_id), "division": division, "words": words},
                    )
                    .mappings()
                    .first()
                )
            return _entry_from_mapping(row) if row is not None else None

        with self._connection() as conn:
            cur = conn.execute(
                """
                UPDATE T_Sns_Search
                SET Division = ?, Words = ?
                WHERE ID_Sns_Search = ?
                """,
                (division, words, int(entry_id)),
            )
            if cur.rowcount == 0:
                return None
            row = conn.execute(
                """
                SELECT ID_Sns_Search, Division, Words
                FROM T_Sns_Search
                WHERE ID_Sns_Search = ?
                """,
                (int(entry_id),),
            ).fetchone()
        return _entry_from_row(row) if row is not None else None

    def delete_entry(self, entry_id: int) -> bool:
        if self.engine is not None:
            from sqlalchemy import text

            with self.engine.begin() as conn:
                result = conn.execute(
                    text(f"DELETE FROM {SNS_SEARCH_TABLE} WHERE ID_Sns_Search = :entry_id"),
                    {"entry_id": int(entry_id)},
                )
            return bool(result.rowcount and result.rowcount > 0)

        with self._connection() as conn:
            cur = conn.execute(
                "DELETE FROM T_Sns_Search WHERE ID_Sns_Search = ?",
                (int(entry_id),),
            )
            return cur.rowcount > 0


def _clean_required(value: str, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _create_general_db_engine() -> Any:
    if str(ABCONFIG_DIR) not in sys.path:
        sys.path.insert(0, str(ABCONFIG_DIR))
    import Cnct_Env as CE  # type: ignore

    return CE.create_connection(GENERAL_DB_NAME)


def _entry_from_row(row: sqlite3.Row) -> SnsSearchEntry:
    return SnsSearchEntry(
        ID_Sns_Search=int(row["ID_Sns_Search"]),
        Division=str(row["Division"]),
        Words=str(row["Words"]),
    )


def _entry_from_mapping(row: Any) -> SnsSearchEntry:
    return SnsSearchEntry(
        ID_Sns_Search=int(row["ID_Sns_Search"]),
        Division=str(row["Division"]),
        Words=str(row["Words"]),
    )
