"""Unit tests for core/memory/shortterm.py — ShortTermMemory."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

import pytest

from core.memory.shortterm import (
    _MAX_RESPONSE_CHARS,
    SessionState,
    ShortTermMemory,
    StreamCheckpoint,
)


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "anima"
    (d / "shortterm" / "chat" / "archive").mkdir(parents=True)
    return d


@pytest.fixture
def stm(anima_dir: Path) -> ShortTermMemory:
    return ShortTermMemory(anima_dir)


# ── SessionState ──────────────────────────────────────────


class TestSessionState:
    def test_defaults(self):
        ss = SessionState()
        assert ss.session_id == ""
        assert ss.timestamp == ""
        assert ss.trigger == ""
        assert ss.original_prompt == ""
        assert ss.accumulated_response == ""
        assert ss.tool_uses == []
        assert ss.context_usage_ratio == 0.0
        assert ss.turn_count == 0
        assert ss.notes == ""

    def test_custom_values(self):
        ss = SessionState(
            session_id="sess-1",
            timestamp="2026-01-15T10:00:00",
            trigger="heartbeat",
            original_prompt="Do stuff",
            accumulated_response="Did stuff",
            tool_uses=[{"name": "search", "input": "query"}],
            context_usage_ratio=0.6,
            turn_count=5,
            notes="Important note",
        )
        assert ss.session_id == "sess-1"
        assert ss.turn_count == 5
        assert len(ss.tool_uses) == 1


# ── has_pending ───────────────────────────────────────────


class TestHasPending:
    def test_no_pending(self, stm, anima_dir):
        assert stm.has_pending() is False

    def test_has_pending(self, stm, anima_dir):
        (anima_dir / "shortterm" / "chat" / "session_state.json").write_text("{}", encoding="utf-8")
        assert stm.has_pending() is True


# ── save ──────────────────────────────────────────────────


class TestSave:
    def test_saves_json_and_md(self, stm, anima_dir):
        state = SessionState(
            session_id="sess-1",
            timestamp="2026-01-15T10:00:00",
            trigger="heartbeat",
            original_prompt="Test prompt",
            accumulated_response="Test response",
            context_usage_ratio=0.45,
            turn_count=3,
        )
        result_path = stm.save(state)
        assert result_path.exists()
        assert (anima_dir / "shortterm" / "chat" / "session_state.json").exists()
        assert (anima_dir / "shortterm" / "chat" / "session_state.md").exists()

        # Verify JSON content
        data = json.loads(result_path.read_text(encoding="utf-8"))
        assert data["session_id"] == "sess-1"
        assert data["turn_count"] == 3

        # Verify Markdown content
        md = (anima_dir / "shortterm" / "chat" / "session_state.md").read_text(encoding="utf-8")
        assert "sess-1" in md
        assert "Test prompt" in md

    def test_archives_existing_before_save(self, stm, anima_dir):
        # Save first state
        stm.save(SessionState(session_id="first"))
        # Save second state
        stm.save(SessionState(session_id="second"))
        # First should be archived
        archive_files = list((anima_dir / "shortterm" / "chat" / "archive").glob("*.json"))
        assert len(archive_files) >= 1
        # Current should be "second"
        data = json.loads((anima_dir / "shortterm" / "chat" / "session_state.json").read_text(encoding="utf-8"))
        assert data["session_id"] == "second"

    def test_creates_dirs(self, tmp_path):
        anima_dir = tmp_path / "new_anima"
        stm = ShortTermMemory(anima_dir)
        stm.save(SessionState(session_id="test"))
        assert (anima_dir / "shortterm" / "chat" / "session_state.json").exists()


# ── save_if_not_exists ────────────────────────────────────


class TestSaveIfNotExists:
    def test_saves_when_no_md(self, stm, anima_dir):
        result = stm.save_if_not_exists(SessionState(session_id="fallback"))
        assert result is not None
        assert result.exists()

    def test_skips_when_md_exists(self, stm, anima_dir):
        (anima_dir / "shortterm" / "chat" / "session_state.md").write_text("Agent wrote this", encoding="utf-8")
        result = stm.save_if_not_exists(SessionState(session_id="fallback"))
        assert result is None


# ── load ──────────────────────────────────────────────────


class TestLoad:
    def test_load_existing(self, stm, anima_dir):
        stm.save(
            SessionState(
                session_id="sess-1",
                trigger="test",
                turn_count=5,
            )
        )
        loaded = stm.load()
        assert loaded is not None
        assert loaded.session_id == "sess-1"
        assert loaded.turn_count == 5

    def test_load_nonexistent(self, stm):
        assert stm.load() is None

    def test_load_malformed(self, stm, anima_dir):
        (anima_dir / "shortterm" / "chat" / "session_state.json").write_text("not json", encoding="utf-8")
        assert stm.load() is None


class TestLoadMarkdown:
    def test_load_existing(self, stm, anima_dir):
        stm.save(SessionState(session_id="test"))
        md = stm.load_markdown()
        assert "短期記憶" in md

    def test_load_nonexistent(self, stm):
        assert stm.load_markdown() == ""


# ── clear ─────────────────────────────────────────────────


class TestClear:
    def test_clears_and_archives(self, stm, anima_dir):
        stm.save(SessionState(session_id="to-clear"))
        assert stm.has_pending()
        stm.clear()
        assert not stm.has_pending()
        # Should be archived
        archive_files = list((anima_dir / "shortterm" / "chat" / "archive").glob("*.json"))
        assert len(archive_files) >= 1

    def test_clear_empty(self, stm):
        stm.clear()  # should not raise

    def test_clear_for_clean_start_archives_state_and_deletes_checkpoint(self, anima_dir):
        stm = ShortTermMemory(anima_dir, session_type="inbox", thread_id="inbox")
        stm.save(SessionState(session_id="stale", trigger="inbox:sakura"))
        checkpoint_path = stm.save_checkpoint(
            StreamCheckpoint(
                trigger="inbox:sakura",
                original_prompt="old prompt",
                completed_tools=[{"tool_name": "old", "tool_id": "1", "summary": "old"}],
            )
        )

        assert stm.has_pending()
        assert checkpoint_path.exists()

        stm.clear_for_clean_start()

        assert not stm.has_pending()
        assert not checkpoint_path.exists()
        archive_files = list((anima_dir / "shortterm" / "inbox" / "inbox" / "archive").glob("*.json"))
        assert len(archive_files) >= 1


# ── _archive_existing ─────────────────────────────────────


class TestArchiveExisting:
    def test_archives_both_files(self, stm, anima_dir):
        (anima_dir / "shortterm" / "chat" / "session_state.json").write_text("{}", encoding="utf-8")
        (anima_dir / "shortterm" / "chat" / "session_state.md").write_text("md", encoding="utf-8")
        stm._archive_existing()
        assert not (anima_dir / "shortterm" / "chat" / "session_state.json").exists()
        assert not (anima_dir / "shortterm" / "chat" / "session_state.md").exists()
        archive = anima_dir / "shortterm" / "chat" / "archive"
        assert len(list(archive.glob("*.json"))) == 1
        assert len(list(archive.glob("*.md"))) == 1

    def test_archive_no_collision_within_same_microsecond(self, stm, anima_dir, monkeypatch):
        """When now_local() returns the same instant on multiple calls
        (low-resolution clock or rapid back-to-back calls), the archive
        names must remain unique.  Regression test for Windows
        FileExistsError ([WinError 183]) at 2026-05-06 10:32:30 JST.
        """
        from datetime import datetime

        from core.memory import shortterm as stm_module

        fixed = datetime(2026, 5, 6, 10, 32, 30, 123456, tzinfo=UTC)
        monkeypatch.setattr(stm_module, "now_local", lambda: fixed)

        chat_dir = anima_dir / "shortterm" / "chat"
        archive = chat_dir / "archive"

        # 3 successive archive cycles at the exact same timestamp.
        for i in range(3):
            (chat_dir / "session_state.json").write_text(f'{{"i": {i}}}', encoding="utf-8")
            (chat_dir / "session_state.md").write_text(f"md{i}", encoding="utf-8")
            stm._archive_existing()

        # No exception raised, all three pairs landed in archive.
        assert len(list(archive.glob("*.json"))) == 3
        assert len(list(archive.glob("*.md"))) == 3
        # Source files have been moved out.
        assert not (chat_dir / "session_state.json").exists()
        assert not (chat_dir / "session_state.md").exists()

    def test_archive_pairs_share_base_when_counter_kicks_in(self, stm, anima_dir, monkeypatch):
        """The numeric counter fallback must be applied symmetrically so
        that the .json and .md from a single session stay paired (same
        base name) in the archive directory.
        """
        from datetime import datetime

        from core.memory import shortterm as stm_module

        fixed = datetime(2026, 5, 6, 10, 32, 30, 123456, tzinfo=UTC)
        monkeypatch.setattr(stm_module, "now_local", lambda: fixed)

        chat_dir = anima_dir / "shortterm" / "chat"
        archive = chat_dir / "archive"

        # Pre-seed an archive entry that occupies only the .json slot at
        # the base timestamp.  The next archive call must avoid colliding
        # for either suffix and must keep the new pair sharing one base.
        archive.mkdir(parents=True, exist_ok=True)
        (archive / "20260506_103230_123456.json").write_text("{}", encoding="utf-8")

        (chat_dir / "session_state.json").write_text("{}", encoding="utf-8")
        (chat_dir / "session_state.md").write_text("md", encoding="utf-8")
        stm._archive_existing()

        json_files = sorted(archive.glob("*.json"))
        md_files = sorted(archive.glob("*.md"))
        # 2 json (pre-seeded + new) and 1 md.
        assert len(json_files) == 2
        assert len(md_files) == 1
        # New pair shares one base, distinct from the pre-seeded entry.
        new_json = [p for p in json_files if p.stem != "20260506_103230_123456"][0]
        assert new_json.stem == md_files[0].stem


# ── _prune_archive ────────────────────────────────────────


class TestPruneArchive:
    def test_prunes_excess(self, stm, anima_dir):
        archive = anima_dir / "shortterm" / "chat" / "archive"
        # Create 110 files
        for i in range(110):
            (archive / f"{i:04d}.json").write_text("{}", encoding="utf-8")
        stm._prune_archive(max_files=100)
        remaining = list(archive.glob("*.json"))
        assert len(remaining) == 100

    def test_no_prune_when_under_limit(self, stm, anima_dir):
        archive = anima_dir / "shortterm" / "chat" / "archive"
        for i in range(5):
            (archive / f"{i:04d}.json").write_text("{}", encoding="utf-8")
        stm._prune_archive(max_files=100)
        assert len(list(archive.glob("*.json"))) == 5


# ── _render_markdown ──────────────────────────────────────


class TestRenderMarkdown:
    def test_basic_render(self, stm):
        state = SessionState(
            session_id="sess-1",
            timestamp="2026-01-15T10:00:00",
            trigger="heartbeat",
            original_prompt="Do something",
            accumulated_response="Did something",
            context_usage_ratio=0.45,
            turn_count=3,
        )
        md = stm._render_markdown(state)
        assert "短期記憶" in md
        assert "sess-1" in md
        assert "heartbeat" in md
        assert "Do something" in md
        assert "Did something" in md
        assert "45%" in md

    def test_truncates_long_response(self, stm):
        long_response = "x" * (_MAX_RESPONSE_CHARS + 500)
        state = SessionState(accumulated_response=long_response)
        md = stm._render_markdown(state)
        assert "前半省略" in md

    def test_tool_uses_in_markdown(self, stm):
        state = SessionState(
            tool_uses=[
                {"name": "search", "input": "query"},
                {"name": "read", "input": "file.txt"},
            ],
        )
        md = stm._render_markdown(state)
        assert "search" in md
        assert "read" in md

    def test_empty_tool_uses(self, stm):
        state = SessionState(tool_uses=[])
        md = stm._render_markdown(state)
        assert "(なし)" in md

    def test_empty_notes(self, stm):
        state = SessionState(notes="")
        md = stm._render_markdown(state)
        assert "(なし)" in md

    def test_with_notes(self, stm):
        state = SessionState(notes="Important info")
        md = stm._render_markdown(state)
        assert "Important info" in md
