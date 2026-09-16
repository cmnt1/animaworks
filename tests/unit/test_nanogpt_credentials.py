"""Credential rotation must replace cached/configured nanoGPT keys everywhere."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.config import nanogpt
from core.config.schemas import AnimaWorksConfig, CredentialConfig


@pytest.fixture
def source(tmp_path, monkeypatch):
    path = tmp_path / "_local.py"
    path.write_text("nanogpt_api = 'new-key'\n", encoding="utf-8")
    monkeypatch.setenv(nanogpt.NANOGPT_SECRETS_PATH_ENV, str(path))
    return path


def test_local_rotation_overrides_cached_key_even_with_unchanged_mtime(source):
    assert nanogpt.nanogpt_api_key("old-key") == "new-key"
    stamp = source.stat()
    source.write_text("nanogpt_api = 'rotated'\n", encoding="utf-8")
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert nanogpt.nanogpt_api_key("old-key") == "rotated"


def test_reads_existing_secrets_local_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(nanogpt, "_DEFAULT_ABCONFIG_DIR", tmp_path)
    (tmp_path / "secrets_local.py").write_text("nanogpt_api: str = 'local'\n", encoding="utf-8-sig")
    assert nanogpt.nanogpt_api_key("old-key") == "local"


def test_respects_abconfig_location(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_ABCONFIG_PATH", str(tmp_path / "Cnct_Env.py"))
    (tmp_path / "secrets_local.py").write_text("nanogpt_api = 'bridge'\n", encoding="utf-8")
    assert nanogpt.nanogpt_api_key("old-key") == "bridge"


def test_without_local_files_preserves_config_and_environment(monkeypatch):
    monkeypatch.setenv("NANOGPT_API_KEY", "env-key")
    assert nanogpt.nanogpt_api_key("configured") == "configured"
    assert nanogpt.nanogpt_api_key() == "env-key"


@pytest.mark.parametrize(
    "content", ["nanogpt_api = ''", "other_key = 'secret'", "nanogpt_api = get_key()", "nanogpt_api = 'secret"]
)
def test_invalid_source_never_falls_back_or_exposes_values(source, content):
    source.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError) as caught:
        nanogpt.nanogpt_api_key("old-key")
    assert "old-key" not in str(caught.value)
    assert "'secret" not in str(caught.value)


def test_missing_explicit_source_does_not_use_old_key(source):
    source.unlink()
    with pytest.raises(ValueError, match="not found"):
        nanogpt.nanogpt_api_key("old-key")


def test_does_not_execute_secrets_file(source):
    source.write_text("raise RuntimeError('must not run')\nnanogpt_api = 'safe-read'\n", encoding="utf-8")
    assert nanogpt.nanogpt_api_key() == "safe-read"


def test_executor_rereads_for_front_and_background_models(source, tmp_path):
    from core.execution.base import BaseExecutor
    from core.schemas import ModelConfig

    for model in ["nanogpt/zai-org/glm-5.2", "nanogpt/deepseek/deepseek-v4-flash"]:
        config = ModelConfig(model=model, api_key="old-key", api_key_env="NANOGPT_API_KEY")
        executor = SimpleNamespace(_model_config=config)
        assert BaseExecutor._resolve_api_key(executor) == "new-key"
        source.write_text("nanogpt_api = 'rotated'\n", encoding="utf-8")
        assert BaseExecutor._resolve_api_key(executor) == "rotated"
        source.write_text("nanogpt_api = 'new-key'\n", encoding="utf-8")


def test_resolution_does_not_persist_local_key_in_config(source):
    from core.config.resolver import resolve_anima_config

    config = AnimaWorksConfig(credentials={"nanogpt": CredentialConfig(api_key="old-key")})
    config.anima_defaults.credential = "nanogpt"
    _, credential = resolve_anima_config(config, "example")
    assert credential.api_key == "new-key"
    assert config.credentials["nanogpt"].api_key == "old-key"


def test_usage_images_and_tools_use_current_key(source):
    from core.tools._base import get_credential
    from server.routes.assets import _nanogpt_image_api_key
    from server.routes.usage_routes import _read_nanogpt_api_key

    config = AnimaWorksConfig(credentials={"nanogpt": CredentialConfig(api_key="old-key")})
    with patch("core.config.models.load_config", return_value=config):
        assert _read_nanogpt_api_key() == "new-key"
        assert _nanogpt_image_api_key() == "new-key"
        assert get_credential("nanogpt", "image_gen", env_var="NANOGPT_API_KEY") == "new-key"


def test_model_catalog_uses_local_key(source):
    from server.routes.config_routes import _refresh_nanogpt_models

    config = AnimaWorksConfig(credentials={"nanogpt": CredentialConfig(api_key="old-key")})
    with (
        patch("server.routes.config_routes._list_nanogpt_models", return_value=["model"]) as request,
        patch("server.routes.config_routes._cache_provider_models"),
    ):
        assert _refresh_nanogpt_models(config)["status"] == "ok"
    assert request.call_args.args[1] == "new-key"


def test_memory_helper_does_not_restore_stale_model_key(source):
    from core.memory._llm_utils import get_llm_kwargs_for_model, get_llm_kwargs_for_model_config
    from core.schemas import ModelConfig

    config = AnimaWorksConfig(credentials={"nanogpt": CredentialConfig(api_key="old-key")})
    model = ModelConfig(model="nanogpt/deepseek/deepseek-v4-flash", api_key="old-key", api_key_env="NANOGPT_API_KEY")
    with (
        patch("core.config.load_config", return_value=config),
        patch("core.memory._llm_utils.ensure_credentials_in_env"),
    ):
        assert get_llm_kwargs_for_model(model.model)["api_key"] == "new-key"
        assert get_llm_kwargs_for_model_config(model)["api_key"] == "new-key"
