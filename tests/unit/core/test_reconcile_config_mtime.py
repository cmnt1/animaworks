"""Unit tests for ReconcileMixin._check_config_freshness()."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from unittest.mock import patch


class FakeReconcileMixin:
    """Minimal stand-in that inherits _check_config_freshness from the mixin."""

    def __init__(self):
        pass

    # Import the method from the actual mixin
    from core.supervisor._mgr_reconcile import ReconcileMixin
    _check_config_freshness = ReconcileMixin._check_config_freshness


class TestCheckConfigFreshness:
    """Tests for content-hash config detection in the reconciliation loop."""

    @patch("core.config.models.load_config")
    @patch("core.config.models.get_config_path")
    def test_first_call_stores_hash(self, mock_path, mock_load, tmp_path: Path):
        config_path = tmp_path / "config.json"
        content = b'{"setting": 1}\n'
        config_path.write_bytes(content)
        mock_path.return_value = config_path

        obj = FakeReconcileMixin()
        obj._check_config_freshness()

        assert obj._last_config_hash == hashlib.sha256(content).hexdigest()
        mock_load.assert_not_called()

    @patch("core.config.models.load_config")
    @patch("core.config.models.get_config_path")
    def test_no_change_does_not_reload(self, mock_path, mock_load, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"setting": 1}\n', encoding="utf-8")
        mock_path.return_value = config_path

        obj = FakeReconcileMixin()
        obj._check_config_freshness()  # first call stores hash
        obj._check_config_freshness()  # second call has same content

        mock_load.assert_not_called()

    @patch("core.config.models.load_config")
    @patch("core.config.models.get_config_path")
    def test_mtime_only_change_does_not_reload(self, mock_path, mock_load, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"setting": 1}\n', encoding="utf-8")
        mock_path.return_value = config_path

        obj = FakeReconcileMixin()
        obj._check_config_freshness()

        new_mtime = config_path.stat().st_mtime + 10
        os.utime(config_path, (new_mtime, new_mtime))
        obj._check_config_freshness()

        mock_load.assert_not_called()

    @patch("core.config.models.load_config")
    @patch("core.config.models.get_config_path")
    def test_content_change_triggers_reload(self, mock_path, mock_load, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"setting": 1}\n', encoding="utf-8")
        mock_path.return_value = config_path

        obj = FakeReconcileMixin()
        obj._check_config_freshness()  # stores initial hash

        config_path.write_text('{"setting": 2}\n', encoding="utf-8")
        obj._check_config_freshness()  # detects content change

        mock_load.assert_called_once()
        assert obj._last_config_hash == hashlib.sha256(b'{"setting": 2}\n').hexdigest()

    @patch("core.config.models.get_config_path")
    def test_exception_is_silently_caught(self, mock_path):
        mock_path.side_effect = RuntimeError("boom")

        obj = FakeReconcileMixin()
        obj._check_config_freshness()  # should not raise

    @patch("core.config.models.load_config")
    @patch("core.config.models.get_config_path")
    def test_multiple_content_changes_trigger_multiple_reloads(self, mock_path, mock_load, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config_path.write_text('{"setting": 1}\n', encoding="utf-8")
        mock_path.return_value = config_path

        obj = FakeReconcileMixin()
        obj._check_config_freshness()  # stores initial hash

        config_path.write_text('{"setting": 2}\n', encoding="utf-8")
        obj._check_config_freshness()  # change 1
        assert mock_load.call_count == 1

        config_path.write_text('{"setting": 3}\n', encoding="utf-8")
        obj._check_config_freshness()  # change 2
        assert mock_load.call_count == 2
