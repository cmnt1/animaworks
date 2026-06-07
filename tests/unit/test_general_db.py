from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import sqlite3

from core.general_db import SnsSearchStore, get_general_db_path


class TestSnsSearchStore:
    def test_general_db_path_uses_shared_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        assert get_general_db_path() == tmp_path / "shared" / "general_db.sqlite3"

    def test_creates_table_and_crud_entries(self, tmp_path):
        db_path = tmp_path / "general_db.sqlite3"
        store = SnsSearchStore(db_path)

        created = store.create_entry("Finance", "$NVDA OR NVIDIA")
        assert created.ID_Sns_Search == 1
        assert created.Division == "Finance"
        assert created.Words == "$NVDA OR NVIDIA"

        updated = store.update_entry(created.ID_Sns_Search, "Finance", "$TSLA OR Tesla")
        assert updated is not None
        assert updated.Words == "$TSLA OR Tesla"

        assert [entry.to_dict() for entry in store.list_entries()] == [
            {
                "ID_Sns_Search": 1,
                "Division": "Finance",
                "Words": "$TSLA OR Tesla",
            }
        ]
        assert store.delete_entry(created.ID_Sns_Search) is True
        assert store.list_entries() == []

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='T_Sns_Search'"
            ).fetchone()
        assert row is not None

    def test_update_and_delete_missing_entry(self, tmp_path):
        store = SnsSearchStore(tmp_path / "general_db.sqlite3")
        assert store.update_entry(404, "Finance", "market") is None
        assert store.delete_entry(404) is False
