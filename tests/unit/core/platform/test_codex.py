"""Unit tests for core.platform.codex."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from core.platform import codex


class TestDefaultHomeDir:
    def test_prefers_home_env(self):
        with patch.dict("os.environ", {"HOME": "/tmp/home", "USERPROFILE": "C:/Users/test"}, clear=True):
            assert codex.default_home_dir() == "/tmp/home"

    def test_falls_back_to_userprofile(self):
        with patch.dict("os.environ", {"USERPROFILE": "C:/Users/test"}, clear=True):
            assert codex.default_home_dir() == "C:/Users/test"


class TestCodexLoginAvailability:
    def test_returns_false_when_auth_missing(self, tmp_path: Path):
        with patch("core.platform.codex.default_home_dir", return_value=str(tmp_path)):
            assert codex.is_codex_login_available() is False

    def test_returns_true_for_valid_auth_file(self, tmp_path: Path):
        auth_path = tmp_path / ".codex" / "auth.json"
        auth_path.parent.mkdir(parents=True)
        auth_path.write_text('{"access_token":"abc"}', encoding="utf-8")

        with patch("core.platform.codex.default_home_dir", return_value=str(tmp_path)):
            assert codex.codex_auth_path() == auth_path
            assert codex.is_codex_login_available() is True

    def test_returns_false_for_invalid_json(self, tmp_path: Path):
        auth_path = tmp_path / ".codex" / "auth.json"
        auth_path.parent.mkdir(parents=True)
        auth_path.write_text("{not-json", encoding="utf-8")

        with patch("core.platform.codex.default_home_dir", return_value=str(tmp_path)):
            assert codex.is_codex_login_available() is False
