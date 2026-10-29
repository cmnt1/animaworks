from __future__ import annotations

import errno
import sqlite3

from core.tasks.dispatch import is_task_permission_error


def test_is_task_permission_error_recognizes_readonly_filesystem() -> None:
    assert is_task_permission_error(PermissionError(errno.EACCES, "Permission denied"))


def test_is_task_permission_error_recognizes_readonly_database() -> None:
    assert is_task_permission_error(sqlite3.OperationalError("attempt to write a readonly database"))


def test_is_task_permission_error_rejects_other_operational_errors() -> None:
    assert not is_task_permission_error(sqlite3.OperationalError("database is locked"))


def test_task_store_leaves_wal_mode(tmp_path) -> None:
    from core.tasks.board.tasks import TaskStore

    db_path = tmp_path / "taskboard.sqlite3"
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA journal_mode=WAL")
    TaskStore(db_path)
    with sqlite3.connect(db_path) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
