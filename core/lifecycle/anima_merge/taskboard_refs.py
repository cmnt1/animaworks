from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Transactional TaskBoard reference updates for Anima merge."""

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any


def taskboard_ids(db_path: Path, anima_name: str) -> set[str]:
    """Read TaskBoard IDs without creating or migrating the database."""
    if not db_path.is_file():
        return set()
    try:
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='taskboard_metadata'"
            ).fetchone()
            if table is None:
                return set()
            result = {
                str(row[0])
                for row in conn.execute(
                    "SELECT task_id FROM taskboard_metadata WHERE anima_name = ?",
                    (anima_name,),
                )
                if row[0]
            }
            events = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='taskboard_events'"
            ).fetchone()
            if events is not None:
                result.update(
                    str(row[0])
                    for row in conn.execute(
                        "SELECT task_id FROM taskboard_events WHERE anima_name = ?",
                        (anima_name,),
                    )
                    if row[0]
                )
            return result
    except sqlite3.Error:
        return set()


def rewrite_taskboard(
    db_path: Path,
    source: str,
    target: str,
    mapping: dict[str, str],
    rewrite_value: Callable[..., Any],
) -> dict[str, int]:
    """Move metadata and rewrite audit events in one SQLite transaction."""
    if not db_path.is_file():
        return {"metadata_moved": 0, "metadata_references_updated": 0, "events_updated": 0}
    metadata_moved = 0
    metadata_refs = 0
    events_updated = 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "taskboard_metadata" in tables:
            rows = conn.execute("SELECT * FROM taskboard_metadata ORDER BY anima_name, task_id").fetchall()
            columns = [str(item[1]) for item in conn.execute("PRAGMA table_info(taskboard_metadata)")]
            placeholders = ", ".join("?" for _ in columns)
            for row in rows:
                original = dict(row)
                owner_is_source = original["anima_name"] == source
                rewritten = rewrite_value(
                    original,
                    source=source,
                    target=target,
                    mapping=mapping,
                    owner_is_source=owner_is_source,
                )
                if rewritten == original:
                    continue
                new_key = (rewritten["anima_name"], rewritten["task_id"])
                old_key = (original["anima_name"], original["task_id"])
                if new_key != old_key:
                    existing = conn.execute(
                        "SELECT 1 FROM taskboard_metadata WHERE anima_name=? AND task_id=?",
                        new_key,
                    ).fetchone()
                    if existing is not None:
                        raise ValueError(f"Conflicting TaskBoard metadata row: {new_key[0]}:{new_key[1]}")
                    conn.execute(
                        f"INSERT INTO taskboard_metadata ({', '.join(columns)}) VALUES ({placeholders})",
                        tuple(rewritten[column] for column in columns),
                    )
                    conn.execute(
                        "DELETE FROM taskboard_metadata WHERE anima_name=? AND task_id=?",
                        old_key,
                    )
                    metadata_moved += 1
                else:
                    assignments = ", ".join(f"{column}=?" for column in columns)
                    conn.execute(
                        f"UPDATE taskboard_metadata SET {assignments} WHERE anima_name=? AND task_id=?",
                        (*[rewritten[column] for column in columns], *old_key),
                    )
                    metadata_refs += 1

        if "taskboard_events" in tables:
            for row in conn.execute("SELECT * FROM taskboard_events ORDER BY id").fetchall():
                original = dict(row)
                owner_is_source = original["anima_name"] == source
                rewritten = dict(original)
                rewritten["anima_name"] = target if owner_is_source else original["anima_name"]
                if owner_is_source:
                    rewritten["task_id"] = mapping.get(original["task_id"], original["task_id"])
                if original.get("actor") == source:
                    rewritten["actor"] = target
                try:
                    payload = json.loads(original.get("payload_json") or "{}")
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict):
                    payload = rewrite_value(
                        payload,
                        source=source,
                        target=target,
                        mapping=mapping,
                        owner_is_source=owner_is_source,
                    )
                    rewritten["payload_json"] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                if rewritten != original:
                    conn.execute(
                        """
                        UPDATE taskboard_events
                        SET actor=?, anima_name=?, task_id=?, payload_json=?
                        WHERE id=?
                        """,
                        (
                            rewritten["actor"],
                            rewritten["anima_name"],
                            rewritten["task_id"],
                            rewritten["payload_json"],
                            rewritten["id"],
                        ),
                    )
                    events_updated += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "metadata_moved": metadata_moved,
        "metadata_references_updated": metadata_refs,
        "events_updated": events_updated,
    }
