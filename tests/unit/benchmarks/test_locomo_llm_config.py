from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from benchmarks.locomo.llm_config import (
    default_answer_model,
    default_baseline_path,
    default_judge_llm_credential,
    default_llm_credential,
    resolve_locomo_judge_litellm_kwargs,
    resolve_locomo_litellm_kwargs,
)


class TestLoCoMoLlmConfig:
    def test_default_answer_model_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOCOMO_ANSWER_MODEL", "custom-model")
        assert default_answer_model() == "custom-model"

    def test_default_llm_credential_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOCOMO_LLM_CREDENTIAL", "my-cred")
        assert default_llm_credential() == "my-cred"

    def test_default_judge_llm_credential_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOCOMO_JUDGE_LLM_CREDENTIAL", "judge-cred")
        assert default_judge_llm_credential() == "judge-cred"

    def test_resolve_via_vllm_lb_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.setenv("LOCOMO_LLM_CREDENTIAL", "vllm-lb")

        host_cfg = {
            "credentials": {
                "vllm-lb": {"api_key": "dummy", "base_url": "http://localhost:4000/v1"},
            },
            "consolidation": {"llm_credential": "vllm-lb"},
        }
        with patch("benchmarks.locomo.llm_config._load_host_config", return_value=host_cfg):
            model, kwargs = resolve_locomo_litellm_kwargs("deepseek-v4-flash")

        assert model == "openai/deepseek-v4-flash"
        assert kwargs["api_base"] == "http://localhost:4000/v1"
        assert kwargs["api_key"] == "dummy"

    def test_resolve_via_explicit_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

        host_cfg = {
            "credentials": {
                "answer-host": {"api_key": "answer-key", "base_url": "http://answer.example/v1"},
                "judge-host": {"api_key": "judge-key", "base_url": "http://judge.example/v1"},
            },
            "consolidation": {"llm_credential": "answer-host"},
        }
        with patch("benchmarks.locomo.llm_config._load_host_config", return_value=host_cfg):
            model, kwargs = resolve_locomo_litellm_kwargs("mlx-community/Qwen3.5", credential="judge-host")

        assert model == "openai/mlx-community/Qwen3.5"
        assert kwargs["api_base"] == "http://judge.example/v1"
        assert kwargs["api_key"] == "judge-key"

    def test_resolve_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_BASE", "http://proxy.example/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        model, kwargs = resolve_locomo_litellm_kwargs("deepseek-v4-flash")

        assert model == "openai/deepseek-v4-flash"
        assert kwargs["api_base"] == "http://proxy.example/v1"
        assert kwargs["api_key"] == "test-key"

    def test_qwen_disables_thinking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_BASE", "http://proxy.example/v1")

        _, kwargs = resolve_locomo_litellm_kwargs("openai/mlx-community/Qwen3.5-397B-A17B-4bit")

        assert kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}

    def test_deepseek_disables_thinking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_BASE", "http://proxy.example/v1")

        _, kwargs = resolve_locomo_litellm_kwargs("deepseek-v4-flash")

        assert kwargs["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}

    def test_resolve_ignores_temp_animaworks_data_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """LoCoMo sets ANIMAWORKS_DATA_DIR to temp dir; host config must still win."""
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        host_cfg = {
            "credentials": {
                "vllm-lb": {"api_key": "dummy", "base_url": "http://localhost:4000/v1"},
            },
            "consolidation": {"llm_credential": "vllm-lb", "llm_model": "openai/deepseek-v4-flash"},
        }
        with patch("benchmarks.locomo.llm_config._load_host_config", return_value=host_cfg):
            model, kwargs = resolve_locomo_litellm_kwargs("deepseek-v4-flash")

        assert model == "openai/deepseek-v4-flash"
        assert kwargs["api_base"] == "http://localhost:4000/v1"

    def test_resolve_judge_proxy_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_BASE", "http://proxy.example/v1")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        model, kwargs = resolve_locomo_judge_litellm_kwargs("deepseek-chat")

        assert model == "openai/deepseek-chat"
        assert kwargs["api_base"] == "http://proxy.example/v1"
        assert kwargs["api_key"] == "test-key"

    def test_resolve_judge_proxy_model_uses_judge_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.setenv("LOCOMO_LLM_CREDENTIAL", "answer-host")
        monkeypatch.setenv("LOCOMO_JUDGE_LLM_CREDENTIAL", "judge-host")

        host_cfg = {
            "credentials": {
                "answer-host": {"api_key": "answer-key", "base_url": "http://answer.example/v1"},
                "judge-host": {"api_key": "judge-key", "base_url": "http://judge.example/v1"},
            },
            "consolidation": {"llm_credential": "answer-host"},
        }
        with patch("benchmarks.locomo.llm_config._load_host_config", return_value=host_cfg):
            model, kwargs = resolve_locomo_judge_litellm_kwargs("mlx-community/Qwen3.5")

        assert model == "openai/mlx-community/Qwen3.5"
        assert kwargs["api_base"] == "http://judge.example/v1"
        assert kwargs["api_key"] == "judge-key"

    def test_resolve_judge_standard_model_uses_judge_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.setenv("LOCOMO_JUDGE_LLM_CREDENTIAL", "azure-host")
        monkeypatch.setenv("AZURE_API_VERSION", "2025-01-01-preview")

        host_cfg = {
            "credentials": {
                "azure-host": {"api_key": "azure-key", "base_url": "https://azure.example"},
            },
            "consolidation": {"llm_credential": "answer-host"},
        }
        with patch("benchmarks.locomo.llm_config._load_host_config", return_value=host_cfg):
            model, kwargs = resolve_locomo_judge_litellm_kwargs("azure/gpt-4.1")

        assert model == "azure/gpt-4.1"
        assert kwargs["api_base"] == "https://azure.example"
        assert kwargs["api_key"] == "azure-key"
        assert kwargs["api_version"] == "2025-01-01-preview"

    def test_resolve_judge_preserves_standard_openai_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("LOCOMO_JUDGE_LLM_CREDENTIAL", raising=False)

        model, kwargs = resolve_locomo_judge_litellm_kwargs("gpt-4o")

        assert model == "gpt-4o"
        assert kwargs == {}

    def test_default_baseline_deepseek(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOCOMO_BASELINE", raising=False)
        path = default_baseline_path("deepseek-v4-flash")
        assert path.name == "legacy_scope_all_deepseek_v4_flash_20260525.json"
        assert path.is_file()

    def test_default_baseline_qwen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LOCOMO_BASELINE", raising=False)
        path = default_baseline_path("openai/mlx-community/Qwen3.5-397B-A17B-4bit")
        assert path.name == "legacy_scope_all_20260522.json"
