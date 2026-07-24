"""Tests for ordered runtime model fallback configuration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.io import invalidate_cache
from core.config.model_config import (
    fallback_event_meta,
    load_model_config,
    resolve_effective_model_config,
)
from core.config.model_mode import parse_fallback_entry
from core.config.resolver import resolve_anima_config
from core.config.schemas import AnimaDefaults, AnimaWorksConfig, CredentialConfig
from core.memory.config_reader import ConfigReader
from core.schemas import ModelConfig


@pytest.fixture
def fallback_config() -> AnimaWorksConfig:
    return AnimaWorksConfig(
        credentials={
            "anthropic": CredentialConfig(type="claude_code_login"),
            "openai": CredentialConfig(
                type="api_key",
                api_key="sk-openai",
                base_url="https://openai.example/v1",
                keys={"organization": "org-test"},
            ),
            "grok": CredentialConfig(
                type="api_key",
                api_key="sk-grok",
                base_url="https://grok.example/v1",
                keys={"account": "test"},
            ),
        },
    )


@pytest.fixture
def primary_config() -> ModelConfig:
    return ModelConfig(
        model="codex/gpt-5.4",
        execution_mode="C",
        resolved_mode="C",
        credential="openai",
        fallback_models=["a:openai/gpt-4.1", "x:grok/grok-4.5"],
    )


def _guard_with_blocks(blocks: dict[str, float]) -> MagicMock:
    guard = MagicMock()
    guard.blocked_remaining.side_effect = lambda key: blocks.get(key, 0.0)
    return guard


class TestParseFallbackEntry:
    def test_explicit_mode(self, fallback_config: AnimaWorksConfig) -> None:
        assert parse_fallback_entry("x:grok/grok-4.5", fallback_config) == (
            "x",
            "grok/grok-4.5",
        )

    def test_omitted_mode_uses_resolver(
        self,
        fallback_config: AnimaWorksConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("core.config.model_mode._match_models_json", lambda _model: None)
        assert parse_fallback_entry("grok/grok-4.5", fallback_config) == (
            "x",
            "grok/grok-4.5",
        )

    def test_model_tag_colon_is_not_treated_as_mode(
        self,
        fallback_config: AnimaWorksConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("core.config.model_mode._match_models_json", lambda _model: None)
        assert parse_fallback_entry("ollama/qwen3:14b", fallback_config) == (
            "a",
            "ollama/qwen3:14b",
        )

    @pytest.mark.parametrize("entry", ["z:model", "X:grok/grok-4.5"])
    def test_invalid_explicit_mode_warns_and_skips(
        self,
        entry: str,
        fallback_config: AnimaWorksConfig,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="animaworks.config"):
            assert parse_fallback_entry(entry, fallback_config) is None
        assert "invalid mode" in caplog.text

    @pytest.mark.parametrize("entry", ["", "   ", "x:"])
    def test_empty_entry_warns_and_skips(
        self,
        entry: str,
        fallback_config: AnimaWorksConfig,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="animaworks.config"):
            assert parse_fallback_entry(entry, fallback_config) is None
        assert "empty" in caplog.text


class TestFallbackConfigMerge:
    def test_status_fallback_models_override_defaults(self, tmp_path: Path) -> None:
        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        (anima_dir / "status.json").write_text(
            json.dumps({"fallback_models": ["x:grok/grok-4.5"]}),
            encoding="utf-8",
        )
        config = AnimaWorksConfig(
            credentials={"anthropic": CredentialConfig()},
            anima_defaults=AnimaDefaults(
                fallback_models=["a:openai/gpt-4.1"],
            ),
        )

        resolved, _credential = resolve_anima_config(config, "alice", anima_dir)

        assert resolved.fallback_models == ["x:grok/grok-4.5"]

    def test_both_model_config_loaders_propagate_fallback_models(
        self,
        tmp_path: Path,
    ) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "credentials": {"anthropic": {"api_key": "sk-test"}},
                    "anima_defaults": {
                        "model": "claude-sonnet-4-6",
                        "credential": "anthropic",
                        "fallback_models": ["a:openai/gpt-4.1"],
                    },
                },
            ),
            encoding="utf-8",
        )
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "status.json").write_text(
            json.dumps({"fallback_models": ["x:grok/grok-4.5"]}),
            encoding="utf-8",
        )
        invalidate_cache()

        with (
            patch("core.config.models.get_config_path", return_value=config_path),
            patch("core.config.get_config_path", return_value=config_path),
        ):
            standalone = load_model_config(anima_dir)
            memory = ConfigReader(anima_dir).read_model_config()

        assert standalone.fallback_models == ["x:grok/grok-4.5"]
        assert memory.fallback_models == ["x:grok/grok-4.5"]
        invalidate_cache()


class TestResolveEffectiveModelConfig:
    def test_primary_not_blocked_returns_same_object(
        self,
        fallback_config: AnimaWorksConfig,
        primary_config: ModelConfig,
    ) -> None:
        guard = _guard_with_blocks({})
        with (
            patch("core.config.io.load_config", return_value=fallback_config),
            patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
        ):
            result = resolve_effective_model_config(primary_config)

        assert result is primary_config
        guard.blocked_remaining.assert_called_once_with("openai:codex")

    def test_primary_blocked_selects_first_candidate_and_credentials(
        self,
        fallback_config: AnimaWorksConfig,
        primary_config: ModelConfig,
    ) -> None:
        guard = _guard_with_blocks({"openai:codex": 120.0})
        with (
            patch("core.config.io.load_config", return_value=fallback_config),
            patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
        ):
            result = resolve_effective_model_config(primary_config)

        assert result is not primary_config
        assert result.model == "openai/gpt-4.1"
        assert result.execution_mode == "A"
        assert result.resolved_mode == "A"
        assert result.credential == "openai"
        assert result.credential_type == "api_key"
        assert result.api_key == "sk-openai"
        assert result.api_key_env == "OPENAI_API_KEY"
        assert result.api_base_url == "https://openai.example/v1"
        assert result.extra_keys == {"organization": "org-test"}
        assert result.mode_s_auth is None
        assert primary_config.model == "codex/gpt-5.4"

    def test_blocked_first_candidate_selects_second(
        self,
        fallback_config: AnimaWorksConfig,
        primary_config: ModelConfig,
    ) -> None:
        guard = _guard_with_blocks(
            {
                "openai:codex": 120.0,
                "openai:api": 60.0,
            },
        )
        with (
            patch("core.config.io.load_config", return_value=fallback_config),
            patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
        ):
            result = resolve_effective_model_config(primary_config)

        assert result.model == "grok/grok-4.5"
        assert result.resolved_mode == "X"
        assert result.credential == "grok"
        assert result.api_key == "sk-grok"
        assert result.extra_keys == {"account": "test"}
        assert guard.blocked_remaining.call_args_list[-1].args == ("grok:grok",)

    def test_all_candidates_blocked_keeps_primary(
        self,
        fallback_config: AnimaWorksConfig,
        primary_config: ModelConfig,
    ) -> None:
        guard = _guard_with_blocks(
            {
                "openai:codex": 120.0,
                "openai:api": 60.0,
                "grok:grok": 30.0,
            },
        )
        with (
            patch("core.config.io.load_config", return_value=fallback_config),
            patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
        ):
            result = resolve_effective_model_config(primary_config)

        assert result is primary_config

    def test_empty_fallback_list_is_noop(self) -> None:
        primary = ModelConfig(
            model="codex/gpt-5.4",
            resolved_mode="C",
            fallback_models=[],
        )

        assert resolve_effective_model_config(primary) is primary

    def test_unresolved_credential_candidate_is_skipped(
        self,
        fallback_config: AnimaWorksConfig,
        primary_config: ModelConfig,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        primary = primary_config.model_copy(
            update={
                "fallback_models": [
                    "a:unknown-provider/model",
                    "a:openai/gpt-4.1",
                ],
            },
        )
        guard = _guard_with_blocks({"openai:codex": 120.0})
        with (
            patch("core.config.io.load_config", return_value=fallback_config),
            patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
            caplog.at_level(logging.WARNING, logger="animaworks.config"),
        ):
            result = resolve_effective_model_config(primary)

        assert result.model == "openai/gpt-4.1"
        assert "no credential configured" in caplog.text

    def test_mode_s_uses_auth_realm(
        self,
        fallback_config: AnimaWorksConfig,
    ) -> None:
        primary = ModelConfig(
            model="claude-sonnet-4-6",
            resolved_mode="S",
            mode_s_auth="api",
            fallback_models=["a:openai/gpt-4.1"],
        )
        guard = _guard_with_blocks({"anthropic:api": 120.0})
        with (
            patch("core.config.io.load_config", return_value=fallback_config),
            patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
        ):
            result = resolve_effective_model_config(primary)

        assert result.model == "openai/gpt-4.1"
        assert guard.blocked_remaining.call_args_list[0].args == ("anthropic:api",)

    def test_fallback_event_metadata(
        self,
        fallback_config: AnimaWorksConfig,
        primary_config: ModelConfig,
    ) -> None:
        effective = primary_config.model_copy(
            update={
                "model": "openai/gpt-4.1",
                "execution_mode": "A",
                "resolved_mode": "A",
            },
        )
        guard = _guard_with_blocks({"openai:codex": 42.0})
        with (
            patch("core.config.io.load_config", return_value=fallback_config),
            patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
        ):
            meta = fallback_event_meta(primary_config, effective)

        assert meta == {
            "primary": "codex/gpt-5.4",
            "fallback": "a:openai/gpt-4.1",
            "reason": "rate_guard_blocked",
            "remaining": 42.0,
        }
        assert fallback_event_meta(primary_config, primary_config) is None
