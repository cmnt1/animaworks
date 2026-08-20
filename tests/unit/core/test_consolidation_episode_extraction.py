"""Unit tests for Phase A episode heading format (## HH:MM — タイトル).

Ensures the collector (_collect_recent_episodes) splits an episode file that uses
the prompt-instructed em-dash heading format into separate timeline entries
instead of falling back to a single mtime-based entry (which would discard
entry boundaries and timestamps).
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from core.memory.consolidation import ConsolidationEngine

_FIXED_NOW = datetime(2026, 8, 20, 12, 0, 0, tzinfo=timezone.utc)

_EMDASH = "\u2014"


def _write_episode(episodes_dir: Path) -> Path:
    """Write an episode file using the em-dash heading the prompt now emits."""
    target = _FIXED_NOW.date().isoformat()
    path = episodes_dir / f"{target}.md"
    path.write_text(
        "\n".join(
            [
                f"## 09:00 {_EMDASH} 朝のタスク整理",
                "",
                "- 09:05 メールを確認した",
                "  - クライアント返信を整理",
                "- 09:30 スケジュール調整",
                "",
                f"## 11:00 {_EMDASH} ミーティング",
                "",
                "- 11:00 定例ミーティングに参加",
                "  - 各チームの進捗共有",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


class TestEmitDashEpisodeHeading:
    def _make_engine(self, tmp_path: Path) -> ConsolidationEngine:
        return ConsolidationEngine(tmp_path, "test_anima")

    def test_prompt_instructed_heading_splits_entries(self, tmp_path):
        engine = self._make_engine(tmp_path)
        _write_episode(engine.episodes_dir)

        with patch("core.memory.consolidation.now_local", return_value=_FIXED_NOW):
            entries = engine._collect_recent_episodes(hours=24)

        # Two em-dash sections should be split into two entries (not a single
        # mtime fallback), each carrying the correct timestamp and content.
        assert len(entries) == 2, f"expected 2 entries, got {len(entries)}"
        times = {e["time"] for e in entries}
        assert times == {"09:00", "11:00"}
        morning = next(e for e in entries if e["time"] == "09:00")
        assert "朝のタスク整理" in morning["content"]
        assert "メールを確認した" in morning["content"]
        afternoon = next(e for e in entries if e["time"] == "11:00")
        assert "ミーティング" in afternoon["content"]

    def test_old_hyphen_range_heading_falls_back_to_single_entry(self, tmp_path):
        """A legacy `## HH:MM-HH:MM タイトル` heading must NOT be treated as
        an em-dash entry and falls back to the mtime single-entry behaviour."""
        engine = self._make_engine(tmp_path)
        target = _FIXED_NOW.date().isoformat()
        path = engine.episodes_dir / f"{target}.md"
        path.write_text("## 09:00-11:00 レガシー形式\n\n- 何らかの内容\n", encoding="utf-8")

        with patch("core.memory.consolidation.now_local", return_value=_FIXED_NOW):
            entries = engine._collect_recent_episodes(hours=24)

        assert len(entries) == 1
        # Single fallback entry keeps the whole file content.
        assert "レガシー形式" in entries[0]["content"]
