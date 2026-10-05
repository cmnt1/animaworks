"""Unit tests for core/memory/config_reader.py — ConfigReader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from core.config.model_config import load_model_config
from core.memory.config_reader import ConfigReader
from core.schemas import ModelConfig


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "anima"
    directory.mkdir()
    return directory


@pytest.fixture
def reader(anima_dir: Path) -> ConfigReader:
    return ConfigReader(anima_dir)


class TestResolveApiKey:
    def test_uses_config_api_key_when_available(self, reader: ConfigReader) -> None:
        config = ModelConfig(api_key="sk-direct-key", api_key_env="SHOULD_NOT_USE")
        assert reader.resolve_api_key(config) == "sk-direct-key"

    def test_falls_back_to_env_var(self, reader: ConfigReader, monkeypatch: pytest.MonkeyPatch) -> None:
        config = ModelConfig(api_key=None, api_key_env="TEST_RESOLVE_KEY")
        monkeypatch.setenv("TEST_RESOLVE_KEY", "sk-from-env")
        assert reader.resolve_api_key(config) == "sk-from-env"

    def test_returns_none_when_no_key(self, reader: ConfigReader, monkeypatch: pytest.MonkeyPatch) -> None:
        config = ModelConfig(api_key=None, api_key_env="NONEXISTENT_KEY_XYZ_123")
        monkeypatch.delenv("NONEXISTENT_KEY_XYZ_123", raising=False)
        assert reader.resolve_api_key(config) is None

    def test_empty_string_api_key_uses_env_var(
        self,
        reader: ConfigReader,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        config = ModelConfig(api_key="", api_key_env="TEST_FALLBACK_KEY")
        monkeypatch.setenv("TEST_FALLBACK_KEY", "sk-fallback")
        assert reader.resolve_api_key(config) == "sk-fallback"

    def test_reads_config_when_none_passed(self, reader: ConfigReader) -> None:
        mock_config = ModelConfig(api_key="sk-auto-read")
        with patch.object(reader, "read_model_config", return_value=mock_config) as read_config:
            result = reader.resolve_api_key()

        read_config.assert_called_once()
        assert result == "sk-auto-read"


class TestReadModelConfig:
    def test_missing_config_json_returns_default_model_config(self, anima_dir: Path, tmp_path: Path) -> None:
        config_path = tmp_path / "missing-config.json"
        with patch("core.config.models.get_config_path", return_value=config_path):
            assert load_model_config(anima_dir) == ModelConfig()

    def test_reader_returns_shared_loader_value(self, reader: ConfigReader) -> None:
        expected = ModelConfig(model="openai/custom-model", execution_mode="A")
        with patch("core.config.model_config.load_model_config", return_value=expected) as loader:
            result = reader.read_model_config()

        loader.assert_called_once_with(reader._anima_dir)
        assert result is expected
