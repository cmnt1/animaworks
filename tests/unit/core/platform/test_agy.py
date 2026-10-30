"""Unit tests for core.platform.agy."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from core.platform import agy


class TestAgyCliAvailability:
    def test_returns_executable_when_agy_on_path(self):
        with patch("core.platform.agy.shutil.which", return_value="/usr/bin/agy"):
            assert agy.find_agy_binary() == "/usr/bin/agy"
            assert agy.is_agy_cli_available() is True

    def test_returns_none_when_not_on_path(self):
        with patch("core.platform.agy.shutil.which", return_value=None):
            assert agy.find_agy_binary() is None
            assert agy.is_agy_cli_available() is False


class TestAgyConfigDir:
    def test_uses_home_directory(self, tmp_path: Path):
        with patch.dict("os.environ", {"HOME": str(tmp_path)}, clear=False):
            assert agy.agy_config_dir() == tmp_path / ".gemini" / "antigravity-cli"

    def test_falls_back_to_userprofile(self, tmp_path: Path):
        with patch.dict("os.environ", {"HOME": "", "USERPROFILE": str(tmp_path)}, clear=False):
            assert agy.agy_config_dir() == tmp_path / ".gemini" / "antigravity-cli"


class TestAgyAuthentication:
    def test_returns_true_with_oauth_token(self, tmp_path: Path):
        config_dir = tmp_path / ".gemini" / "antigravity-cli"
        config_dir.mkdir(parents=True)
        (config_dir / "antigravity-oauth-token").write_text("token", encoding="utf-8")

        with patch("core.platform.agy.agy_config_dir", return_value=config_dir):
            assert agy.is_agy_authenticated() is True

    def test_returns_false_without_oauth_token(self, tmp_path: Path):
        config_dir = tmp_path / ".gemini" / "antigravity-cli"

        with patch("core.platform.agy.agy_config_dir", return_value=config_dir):
            assert agy.is_agy_authenticated() is False
