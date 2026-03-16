# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Tests for current_state.md bloat prevention.

Issue: 20260312_current-task-md-bloat-prevention

Covers:
- _prune_auto_detected_resolved() logic
- HB prompt cleanup instruction injection
- Integration with _update_state_from_summary()
"""

from unittest.mock import MagicMock, patch

import pytest

from core.memory.conversation import (
    ConversationMemory,
    ParsedSessionSummary,
    _prune_auto_detected_resolved,
)
from core.schemas import ModelConfig
from tests.helpers.filesystem import create_anima_dir, create_test_data_dir

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    from core.config import invalidate_cache
    from core.paths import _prompt_cache

    d = create_test_data_dir(tmp_path)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(d))
    invalidate_cache()
    _prompt_cache.clear()
    yield d
    invalidate_cache()
    _prompt_cache.clear()


@pytest.fixture
def anima_dir(data_dir):
    return create_anima_dir(data_dir, "test-bloat")


@pytest.fixture
def model_config():
    return ModelConfig(
        model="claude-sonnet-4-6",
        fallback_model="claude-sonnet-4-6",
        max_turns=5,
    )


@pytest.fixture
def conv_memory(anima_dir, model_config):
    return ConversationMemory(anima_dir, model_config)


# ── _prune_auto_detected_resolved tests ──────────────────────


class TestPruneAutoDetectedResolved:
    """Tests for the _prune_auto_detected_resolved() helper function."""

    def test_no_auto_detected_lines(self):
        """Non-auto-detected content is left untouched."""
        text = "## 現在対応中\n- [ ] タスクA\n- [x] タスクB\n## 解決済み\n- ☑ 手動完了タスク\n"
        result, removed = _prune_auto_detected_resolved(text)
        assert result == text
        assert removed == []

    def test_under_threshold(self):
        """When auto-detected lines <= max_keep, nothing is pruned."""
        lines = []
        for i in range(8):
            lines.append(f"- ✅ Task {i}（自動検出: 03/{i + 1:02d} 10:00）")
        text = "\n".join(lines)
        result, removed = _prune_auto_detected_resolved(text, max_keep=10)
        assert result == text
        assert removed == []

    def test_exactly_at_threshold(self):
        """When auto-detected lines == max_keep, nothing is pruned."""
        lines = [f"- ✅ Task {i}（自動検出: 03/{i + 1:02d} 10:00）" for i in range(10)]
        text = "\n".join(lines)
        result, removed = _prune_auto_detected_resolved(text, max_keep=10)
        assert result == text
        assert removed == []

    def test_prune_oldest(self):
        """Oldest auto-detected lines are pruned, newest max_keep are kept."""
        lines = [f"- ✅ Task {i}（自動検出: 03/{i + 1:02d} 10:00）" for i in range(15)]
        text = "\n".join(lines)
        result, removed = _prune_auto_detected_resolved(text, max_keep=10)

        assert len(removed) == 5
        for i in range(5):
            assert f"Task {i}" in removed[i]

        result_lines = result.split("\n")
        assert len(result_lines) == 10
        for i in range(10):
            assert f"Task {i + 5}" in result_lines[i]

    def test_preserves_non_auto_detected_lines(self):
        """LLM-written lines (various formats) are never pruned."""
        text = (
            "## 現在対応中\n"
            "- [ ] 進行中タスク\n"
            "- ✅ Task 0（自動検出: 03/01 10:00）\n"
            "- ✅ Task 1（自動検出: 03/02 10:00）\n"
            "- [x] LLMが書いた完了\n"
            "- ✅ Task 2（自動検出: 03/03 10:00）\n"
            "- ☑ 別フォーマット完了\n"
            "## 解決済み\n"
            "- ✅ Task 3（自動検出: 03/04 10:00）\n"
        )
        result, removed = _prune_auto_detected_resolved(text, max_keep=2)

        assert len(removed) == 2
        assert "Task 0" in removed[0]
        assert "Task 1" in removed[1]

        assert "進行中タスク" in result
        assert "[x] LLMが書いた完了" in result
        assert "☑ 別フォーマット完了" in result
        assert "## 現在対応中" in result
        assert "## 解決済み" in result

    def test_preserves_incomplete_auto_detected(self):
        """Incomplete auto-detected tasks (- [ ] ... 自動検出) are not pruned."""
        text = (
            "- [ ] 未完了タスク（自動検出: 03/01 10:00）\n"
            "- ✅ Task 0（自動検出: 03/02 10:00）\n"
            "- ✅ Task 1（自動検出: 03/03 10:00）\n"
        )
        result, removed = _prune_auto_detected_resolved(text, max_keep=1)

        assert len(removed) == 1
        assert "Task 0" in removed[0]
        assert "未完了タスク" in result
        assert "Task 1" in result

    def test_english_auto_detected_pattern(self):
        """English 'auto-detected:' pattern is also matched."""
        lines = [f"- ✅ Task {i} (auto-detected: 03/{i + 1:02d} 10:00)" for i in range(5)]
        text = "\n".join(lines)
        result, removed = _prune_auto_detected_resolved(text, max_keep=3)

        assert len(removed) == 2
        assert "Task 0" in removed[0]
        assert "Task 1" in removed[1]

    def test_mixed_ja_en_patterns(self):
        """Both Japanese and English auto-detected patterns are handled together."""
        text = (
            "- ✅ タスクA（自動検出: 03/01 10:00）\n"
            "- ✅ TaskB (auto-detected: 03/02 10:00)\n"
            "- ✅ タスクC（自動検出: 03/03 10:00）\n"
            "- ✅ TaskD (auto-detected: 03/04 10:00)\n"
        )
        result, removed = _prune_auto_detected_resolved(text, max_keep=2)

        assert len(removed) == 2
        assert "タスクA" in removed[0]
        assert "TaskB" in removed[1]
        assert "タスクC" in result
        assert "TaskD" in result

    def test_empty_text(self):
        """Empty text returns empty."""
        result, removed = _prune_auto_detected_resolved("")
        assert result == ""
        assert removed == []


# ── _update_state_from_summary pruning integration ────────────


class TestUpdateStatePruning:
    """Tests that _update_state_from_summary() prunes and archives."""

    def test_prune_archives_to_episodes(self, conv_memory, anima_dir):
        """Pruned auto-detected lines are written to episodes."""
        from core.memory.manager import MemoryManager
        from core.time_utils import today_local

        memory_mgr = MemoryManager(anima_dir)

        existing_lines = [f"- ✅ Old {i}（自動検出: 03/{i + 1:02d} 10:00）" for i in range(12)]
        state_text = "## 現在の状態\n" + "\n".join(existing_lines)
        (anima_dir / "state" / "current_state.md").write_text(state_text, encoding="utf-8")

        parsed = ParsedSessionSummary(
            title="test",
            episode_body="test body",
            resolved_items=["new resolved item"],
            new_tasks=[],
            current_status="",
            has_state_changes=True,
        )

        conv_memory._update_state_from_summary(memory_mgr, parsed)

        episode_file = anima_dir / "episodes" / f"{today_local().isoformat()}.md"
        assert episode_file.exists()
        episode_content = episode_file.read_text(encoding="utf-8")
        assert "current_state.md" in episode_content
        assert "Old 0" in episode_content or "Old 1" in episode_content

        updated_state = (anima_dir / "state" / "current_state.md").read_text(encoding="utf-8")
        auto_lines = [ln for ln in updated_state.split("\n") if "自動検出" in ln and "✅" in ln]
        assert len(auto_lines) <= 10

    def test_no_prune_when_below_threshold(self, conv_memory, anima_dir):
        """No pruning when auto-detected count is within threshold.

        Note: resolved_marker i18n adds '自動検出' to the new item too,
        so 5 existing + 1 new = 6 total (still under max_keep=10).
        """
        from core.memory.manager import MemoryManager

        memory_mgr = MemoryManager(anima_dir)

        existing_lines = [f"- ✅ Task {i}（自動検出: 03/{i + 1:02d} 10:00）" for i in range(5)]
        state_text = "\n".join(existing_lines)
        (anima_dir / "state" / "current_state.md").write_text(state_text, encoding="utf-8")

        parsed = ParsedSessionSummary(
            title="test",
            episode_body="test body",
            resolved_items=["another item"],
            new_tasks=[],
            current_status="",
            has_state_changes=True,
        )

        conv_memory._update_state_from_summary(memory_mgr, parsed)

        updated = (anima_dir / "state" / "current_state.md").read_text(encoding="utf-8")
        auto_lines = [ln for ln in updated.split("\n") if "自動検出" in ln and "✅" in ln]
        assert len(auto_lines) == 6  # 5 existing + 1 newly added resolved


# ── HB cleanup instruction injection ─────────────────────────


class TestHeartbeatCleanupInstruction:
    """Tests for _build_heartbeat_prompt() cleanup instruction injection."""

    @pytest.fixture
    def mock_heartbeat_mixin(self, anima_dir):
        """Create a minimal HeartbeatMixin-like object for testing."""
        from core._anima_heartbeat import HeartbeatMixin

        mixin = MagicMock(spec=HeartbeatMixin)
        mixin._CURRENT_STATE_CLEANUP_THRESHOLD = HeartbeatMixin._CURRENT_STATE_CLEANUP_THRESHOLD
        mixin.name = "test-bloat"
        mixin.anima_dir = anima_dir

        memory_mock = MagicMock()
        mixin.memory = memory_mock

        return mixin

    @pytest.mark.asyncio
    async def test_cleanup_injected_when_over_threshold(self, mock_heartbeat_mixin, anima_dir):
        """Cleanup instruction is injected when current_state.md exceeds threshold."""
        from core._anima_heartbeat import HeartbeatMixin

        big_state = "x" * 4000
        mock_heartbeat_mixin.memory.read_current_state.return_value = big_state
        mock_heartbeat_mixin.memory.read_heartbeat_config.return_value = None
        mock_heartbeat_mixin._build_background_context_parts = MagicMock(return_value=[])

        with patch("core._anima_heartbeat.load_prompt", return_value="heartbeat prompt"):
            parts = await HeartbeatMixin._build_heartbeat_prompt(mock_heartbeat_mixin)

        cleanup_parts = [p for p in parts if "current_state.md" in p and ("圧縮" in p or "cleanup" in p)]
        assert len(cleanup_parts) == 1
        assert "4000" in cleanup_parts[0]

    @pytest.mark.asyncio
    async def test_no_cleanup_when_under_threshold(self, mock_heartbeat_mixin):
        """No cleanup instruction when current_state.md is under threshold."""
        from core._anima_heartbeat import HeartbeatMixin

        small_state = "x" * 500
        mock_heartbeat_mixin.memory.read_current_state.return_value = small_state
        mock_heartbeat_mixin.memory.read_heartbeat_config.return_value = None
        mock_heartbeat_mixin._build_background_context_parts = MagicMock(return_value=[])

        with patch("core._anima_heartbeat.load_prompt", return_value="heartbeat prompt"):
            parts = await HeartbeatMixin._build_heartbeat_prompt(mock_heartbeat_mixin)

        cleanup_parts = [p for p in parts if "圧縮" in p or "cleanup" in p]
        assert len(cleanup_parts) == 0

    @pytest.mark.asyncio
    async def test_no_cleanup_at_exact_threshold(self, mock_heartbeat_mixin):
        """No cleanup instruction when current_state.md is exactly at threshold."""
        from core._anima_heartbeat import HeartbeatMixin

        exact_state = "x" * 3000
        mock_heartbeat_mixin.memory.read_current_state.return_value = exact_state
        mock_heartbeat_mixin.memory.read_heartbeat_config.return_value = None
        mock_heartbeat_mixin._build_background_context_parts = MagicMock(return_value=[])

        with patch("core._anima_heartbeat.load_prompt", return_value="heartbeat prompt"):
            parts = await HeartbeatMixin._build_heartbeat_prompt(mock_heartbeat_mixin)

        cleanup_parts = [p for p in parts if "圧縮" in p or "cleanup" in p]
        assert len(cleanup_parts) == 0


# ── Builder truncation (existing defense) ─────────────────────


class TestBuilderTruncation:
    """Verify builder.py's existing _CURRENT_STATE_MAX_CHARS defense."""

    def test_constant_exists(self):
        """_CURRENT_STATE_MAX_CHARS is defined and equals 3000."""
        from core.prompt.builder import _CURRENT_STATE_MAX_CHARS

        assert _CURRENT_STATE_MAX_CHARS == 3000
