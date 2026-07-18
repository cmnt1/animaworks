from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.project_threads — registry and thread routing."""

from pathlib import Path
from unittest.mock import patch

from core import project_threads as pt


def _use_tmp_registry(tmp_path: Path):
    return patch.object(pt, "_registry_path", lambda: tmp_path / "project_threads.json")


def test_registry_roundtrip(tmp_path: Path) -> None:
    with _use_tmp_registry(tmp_path):
        assert pt.load_registry() == {}
        pt.register_thread("FIN-047", channel_id="111", thread_id="222", title="VIX最適化")
        reg = pt.load_registry()
        assert reg["FIN-047"]["channel_id"] == "111"
        assert reg["FIN-047"]["thread_id"] == "222"
        assert pt.resolve_thread_for_code("FIN-047") == ("111", "222")
        assert pt.resolve_thread_for_code("FIN-999") is None


def test_register_preserves_created_at(tmp_path: Path) -> None:
    with _use_tmp_registry(tmp_path):
        pt.register_thread("FIN-047", channel_id="111", thread_id="222")
        first = pt.load_registry()["FIN-047"]["created_at"]
        pt.register_thread("FIN-047", channel_id="111", thread_id="333")
        assert pt.load_registry()["FIN-047"]["created_at"] == first
        assert pt.load_registry()["FIN-047"]["thread_id"] == "333"


def test_resolve_thread_for_text_matching(tmp_path: Path) -> None:
    with _use_tmp_registry(tmp_path):
        pt.register_thread("FIN-047", channel_id="111", thread_id="222")

        assert pt.resolve_thread_for_text("【FIN-047 方針追補】进捗") == ("FIN-047", "111", "222")
        assert pt.resolve_thread_for_text("fin-047 の件") == ("FIN-047", "111", "222")
        # 境界: FIN-0470 は別コード、XFIN-047 も不一致
        assert pt.resolve_thread_for_text("FIN-0470 は別タスク") is None
        assert pt.resolve_thread_for_text("XFIN-047") is None
        assert pt.resolve_thread_for_text("無関係の投稿") is None
        assert pt.resolve_thread_for_text("") is None


def test_resolve_thread_skips_incomplete_entries(tmp_path: Path) -> None:
    with _use_tmp_registry(tmp_path):
        pt.register_thread("FIN-047", channel_id="111", thread_id="")
        assert pt.resolve_thread_for_text("FIN-047") is None
        assert pt.resolve_thread_for_code("FIN-047") is None


def test_ensure_project_thread_rejects_invalid_code(tmp_path: Path) -> None:
    with _use_tmp_registry(tmp_path):
        assert pt.ensure_project_thread("") is None
        assert pt.ensure_project_thread("not a code") is None
        assert pt.ensure_project_thread("FIN047") is None


def test_ensure_project_thread_reuses_registered(tmp_path: Path) -> None:
    with _use_tmp_registry(tmp_path):
        pt.register_thread("FIN-047", channel_id="111", thread_id="222")
        # 登録済みなら Discord API に触れずそのまま返す
        assert pt.ensure_project_thread("FIN-047", title="x") == ("111", "222")
