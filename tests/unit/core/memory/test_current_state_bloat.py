# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Tests for current_state.md bloat controls."""

from unittest.mock import MagicMock, patch

import pytest

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


# ── Heartbeat prompt (cleanup instruction removed) ─────────────


class TestHeartbeatPromptCleanup:
    """Heartbeat cleanup injection only when heartbeat.current_state_max_chars > 0."""

    @pytest.fixture
    def mock_heartbeat_mixin(self, anima_dir):
        from core.anima.heartbeat import HeartbeatMixin

        mixin = MagicMock(spec=HeartbeatMixin)
        mixin.name = "test-bloat"
        mixin.anima_dir = anima_dir
        memory_mock = MagicMock()
        mixin.memory = memory_mock
        mixin._build_state_cleanup_instruction = lambda: HeartbeatMixin._build_state_cleanup_instruction(mixin)
        mixin._build_heartbeat_md_cleanup_instruction = MagicMock(return_value=None)
        mixin._build_preobserved_heartbeat_snapshot_part = MagicMock(return_value=None)

        return mixin

    @pytest.mark.asyncio
    async def test_no_cleanup_even_when_large(self, mock_heartbeat_mixin):
        """No cleanup instruction when max_chars is 0 (default disabled)."""
        from core.anima.heartbeat import HeartbeatMixin

        big_state = "x" * 10000
        mock_heartbeat_mixin.memory.read_current_state.return_value = big_state
        mock_heartbeat_mixin.memory.read_heartbeat_config.return_value = None
        mock_heartbeat_mixin._build_background_context_parts = MagicMock(return_value=[])
        mock_heartbeat_mixin._get_current_state_max_chars = MagicMock(return_value=0)

        with patch("core.anima.heartbeat.load_prompt", return_value="heartbeat prompt"):
            parts = await HeartbeatMixin._build_heartbeat_prompt(mock_heartbeat_mixin)

        cleanup_parts = [p for p in parts if "圧縮" in p or "cleanup" in p]
        assert len(cleanup_parts) == 0

    @pytest.mark.asyncio
    async def test_no_cleanup_when_small(self, mock_heartbeat_mixin):
        """No cleanup instruction when current_state is below threshold."""
        from core.anima.heartbeat import HeartbeatMixin

        mock_heartbeat_mixin.memory.read_current_state.return_value = "x" * 500
        mock_heartbeat_mixin.memory.read_heartbeat_config.return_value = None
        mock_heartbeat_mixin._build_background_context_parts = MagicMock(return_value=["bg context"])
        mock_heartbeat_mixin._get_current_state_max_chars = MagicMock(return_value=0)

        with patch("core.anima.heartbeat.load_prompt", return_value="heartbeat prompt"):
            parts = await HeartbeatMixin._build_heartbeat_prompt(mock_heartbeat_mixin)

        assert parts == ["heartbeat prompt", "bg context"]


# ── Builder truncation (existing defense) ─────────────────────


class TestBuilderTruncation:
    """Verify builder.py's existing _CURRENT_STATE_MAX_CHARS defense."""

    def test_constant_exists(self):
        """_CURRENT_STATE_MAX_CHARS is defined and equals 3000."""
        from core.prompt.builder import _CURRENT_STATE_MAX_CHARS

        assert _CURRENT_STATE_MAX_CHARS == 3000
