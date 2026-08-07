# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for company-fixed GitHub identity env injection."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.models import AnimaWorksConfig
from core.execution import github_identity
from core.execution.github_identity import resolve_github_token_env


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    github_identity._clear_token_cache()
    yield
    github_identity._clear_token_cache()


def _anima_dir(tmp_path: Path, company: str | None = "fs") -> Path:
    anima = tmp_path / "animas" / "natsume"
    anima.mkdir(parents=True)
    if company is None:
        (anima / "status.json").write_text("{}", encoding="utf-8")
    else:
        (anima / "status.json").write_text(
            f'{{"company": "{company}"}}',
            encoding="utf-8",
        )
    return anima


class TestResolveGithubTokenEnv:
    def test_injects_gh_token_when_identity_mapped(self, tmp_path: Path) -> None:
        anima = _anima_dir(tmp_path, company="fs")
        cfg = AnimaWorksConfig()
        cfg.github_identities = {"fs": "animaworks-dev-team"}

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "gho_test_token_value_not_real\n"
        completed.stderr = ""

        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch("subprocess.run", return_value=completed) as mock_run,
        ):
            env = resolve_github_token_env(anima)

        assert env == {"GH_TOKEN": "gho_test_token_value_not_real"}
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["gh", "auth", "token", "-u", "animaworks-dev-team"]
        # Token must never appear in log-related kwargs
        assert "gho_test_token_value_not_real" not in str(mock_run.call_args)

    def test_no_injection_when_github_identities_empty(self, tmp_path: Path) -> None:
        anima = _anima_dir(tmp_path, company="fs")
        cfg = AnimaWorksConfig()
        cfg.github_identities = {}

        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch("subprocess.run") as mock_run,
        ):
            env = resolve_github_token_env(anima)

        assert env == {}
        mock_run.assert_not_called()

    def test_no_injection_when_gh_auth_token_fails(self, tmp_path: Path) -> None:
        anima = _anima_dir(tmp_path, company="fs")
        cfg = AnimaWorksConfig()
        cfg.github_identities = {"fs": "animaworks-dev-team"}

        completed = MagicMock()
        completed.returncode = 1
        completed.stdout = ""
        completed.stderr = "not logged in"

        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch("subprocess.run", return_value=completed),
        ):
            env = resolve_github_token_env(anima)

        assert env == {}

    def test_no_injection_when_company_missing(self, tmp_path: Path) -> None:
        anima = _anima_dir(tmp_path, company=None)
        cfg = AnimaWorksConfig()
        cfg.github_identities = {"fs": "animaworks-dev-team"}

        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch("subprocess.run") as mock_run,
        ):
            env = resolve_github_token_env(anima)

        assert env == {}
        mock_run.assert_not_called()

    def test_timeout_falls_back_empty(self, tmp_path: Path) -> None:
        anima = _anima_dir(tmp_path, company="fs")
        cfg = AnimaWorksConfig()
        cfg.github_identities = {"fs": "animaworks-dev-team"}

        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=5),
            ),
        ):
            env = resolve_github_token_env(anima)

        assert env == {}

    def test_token_cached_within_ttl(self, tmp_path: Path) -> None:
        anima = _anima_dir(tmp_path, company="fs")
        cfg = AnimaWorksConfig()
        cfg.github_identities = {"fs": "animaworks-dev-team"}

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "cached_token\n"
        completed.stderr = ""

        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch("subprocess.run", return_value=completed) as mock_run,
        ):
            first = resolve_github_token_env(anima)
            second = resolve_github_token_env(anima)

        assert first == second == {"GH_TOKEN": "cached_token"}
        assert mock_run.call_count == 1

    def test_per_anima_override_takes_priority_over_company(self, tmp_path: Path) -> None:
        anima = _anima_dir(tmp_path, company="fs")
        # anima dir is named "natsume" via helper
        cfg = AnimaWorksConfig()
        cfg.github_identities = {
            "fs": "animaworks-dev-team",
            "anima:natsume": "animaworks-reviewer",
        }

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "reviewer_token\n"
        completed.stderr = ""

        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch("subprocess.run", return_value=completed) as mock_run,
        ):
            env = resolve_github_token_env(anima)

        assert env == {"GH_TOKEN": "reviewer_token"}
        args = mock_run.call_args[0][0]
        assert args == ["gh", "auth", "token", "-u", "animaworks-reviewer"]

    def test_company_fallback_when_per_anima_unset(self, tmp_path: Path) -> None:
        anima = _anima_dir(tmp_path, company="fs")
        cfg = AnimaWorksConfig()
        cfg.github_identities = {
            "fs": "animaworks-dev-team",
            "anima:sumire": "animaworks-reviewer",
        }

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "company_token\n"
        completed.stderr = ""

        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch("subprocess.run", return_value=completed) as mock_run,
        ):
            env = resolve_github_token_env(anima)

        assert env == {"GH_TOKEN": "company_token"}
        args = mock_run.call_args[0][0]
        assert args == ["gh", "auth", "token", "-u", "animaworks-dev-team"]

    def test_exception_returns_empty_dict(self, tmp_path: Path) -> None:
        anima = _anima_dir(tmp_path, company="fs")

        with patch(
            "core.config.models.load_config",
            side_effect=RuntimeError("config boom"),
        ):
            env = resolve_github_token_env(anima)

        assert env == {}
