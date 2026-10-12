"""Tests for core.config.model_discovery.

Covers the pure parse functions, cache behaviour, static fallback, and
fault-isolation between probes.  No real subprocess / network is invoked.
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.config.model_catalog as model_catalog
import core.config.model_discovery as model_discovery
from core.config.model_discovery import (
    DiscoveredModel,
    _parse_claude_help,
    _parse_codex_models,
    _parse_grok_models,
    discover_models,
    discovered_model_ids,
    invalidate_cache,
)
from core.config.models import AnimaWorksConfig

CODEX_JSON = """{"models": [
  {"slug":"gpt-6-astra","display_name":"GPT-6-Astra","visibility":"list","priority":1},
  {"slug":"gpt-5.6-sol","display_name":"GPT-5.6-Sol","visibility":"list","priority":2},
  {"slug":"gpt-reserve","display_name":"GPT-Reserve","visibility":"hide","priority":0},
  {"slug":"codex-auto-review","display_name":"Auto Review","visibility":"hide","priority":3},
  {"slug":"gpt-5.5","display_name":"GPT-5.5","visibility":"list","priority":5}
]}"""

GROK_TEXT = """You are logged in with grok.com.

Default model: grok-4.6

Available models:
  * grok-4.6 (default)
  - grok-4.5
"""


@pytest.fixture(autouse=True)
def _clear_discovery_cache():
    invalidate_cache()
    yield
    invalidate_cache()


def _configure_discovery_backends(
    monkeypatch: pytest.MonkeyPatch,
    *,
    codex: bool = False,
    grok: bool = False,
    codex_error: bool = False,
) -> MagicMock:
    """Stub CLI/network boundaries while exercising the public discovery API."""
    monkeypatch.setattr(model_discovery, "is_codex_login_available", lambda: codex)
    monkeypatch.setattr(
        model_discovery,
        "get_codex_executable",
        lambda: (
            (_ for _ in ()).throw(RuntimeError("codex probe failed"))
            if codex_error
            else "/usr/bin/codex"
            if codex
            else None
        ),
    )
    monkeypatch.setattr(model_discovery, "is_grok_authenticated", lambda: grok)
    monkeypatch.setattr(model_discovery, "get_grok_executable", lambda: "/usr/bin/grok" if grok else None)
    monkeypatch.setattr(model_discovery.shutil, "which", lambda _name: None)
    monkeypatch.setattr(model_catalog, "is_codex_login_available", lambda: False)
    monkeypatch.setattr(model_catalog, "is_grok_authenticated", lambda: False)

    def _run(command, **_kwargs):
        output = CODEX_JSON if command[-2:] == ["debug", "models"] else GROK_TEXT
        return SimpleNamespace(stdout=output, stderr="")

    run = MagicMock(side_effect=_run)
    monkeypatch.setattr(model_discovery.subprocess, "run", run)

    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"data": [], "models": []}
    monkeypatch.setattr(model_discovery.httpx, "get", lambda *_args, **_kwargs: response)
    return run


CLAUDE_HELP = """Usage: claude [options]

Options:
  --model <model>                      Model for the current session. Provide
                                       an alias for the latest model (e.g.
                                       'fable', 'opus', or 'sonnet') or a
                                       model's full name (e.g.
                                       'claude-fable-5').
  --print                             Print response and exit.
"""


class TestParseCodex:
    def test_hide_excluded_and_priority_sorted(self):
        result = _parse_codex_models(CODEX_JSON)
        slugs = [m["slug"] for m in result]
        assert slugs == ["gpt-6-astra", "gpt-5.6-sol", "gpt-5.5"]
        # hide entries must not appear
        assert "gpt-reserve" not in slugs
        assert "codex-auto-review" not in slugs
        # label takes display_name
        assert result[0]["label"] == "GPT-6-Astra"

    def test_invalid_json_returns_empty(self):
        assert _parse_codex_models("not json {") == []


class TestParseGrok:
    def test_extracts_models_without_default_marker(self):
        result = _parse_grok_models(GROK_TEXT)
        assert result == ["grok-4.6", "grok-4.5"]
        assert all("default" not in name for name in result)

    def test_empty_text_returns_empty(self):
        assert _parse_grok_models("") == []


class TestParseClaude:
    def test_extracts_aliases_ignores_full_name(self):
        result = _parse_claude_help(CLAUDE_HELP)
        assert result == ["fable", "opus", "sonnet"]
        assert "claude-fable-5" not in result

    def test_no_model_option_returns_empty(self):
        assert _parse_claude_help("no options") == []


class TestDiscoverModels:
    def test_static_fallback_when_all_probes_empty(self, monkeypatch):
        _configure_discovery_backends(monkeypatch)

        models = discover_models(config=AnimaWorksConfig(), refresh=True)

        assert models
        assert all(model.source == "static" for model in models)

    def test_cache_reuses_result(self, monkeypatch):
        run = _configure_discovery_backends(monkeypatch, codex=True)
        config = AnimaWorksConfig()

        first = discover_models(config=config)
        second = discover_models(config=config)

        assert [model.id for model in first] == [model.id for model in second]
        assert run.call_count == 1

    def test_expired_cache_is_returned_while_background_refresh_starts(self, monkeypatch):
        """A model picker must not wait for probes every time the TTL expires."""
        run = _configure_discovery_backends(monkeypatch, codex=True)
        config = AnimaWorksConfig()

        class _Clock:
            now = 1.0

            def monotonic(self):
                return self.now

        clock = _Clock()
        monkeypatch.setattr(model_discovery, "time", clock)
        first = discover_models(config=config)
        clock.now += model_discovery.CACHE_TTL_SECONDS + 1
        thread_factory = MagicMock()
        monkeypatch.setattr(model_discovery, "threading", SimpleNamespace(Thread=thread_factory))
        stale = discover_models(config=config)

        assert [model.id for model in stale] == [model.id for model in first]
        assert run.call_count == 1
        thread_factory.assert_called_once()
        thread_factory.return_value.start.assert_called_once()

    def test_refresh_reruns_probes(self, monkeypatch):
        run = _configure_discovery_backends(monkeypatch, codex=True)
        config = AnimaWorksConfig()

        discover_models(config=config)
        discover_models(refresh=True, config=config)

        assert run.call_count == 2

    def test_one_probe_exception_ignored(self, monkeypatch):
        _configure_discovery_backends(monkeypatch, codex=True, grok=True, codex_error=True)

        models = discover_models(config=AnimaWorksConfig())

        assert any(model.id == "x:grok/grok-4.6" for model in models)

    def test_catalog_models_without_credentials_are_hidden(self, monkeypatch):
        """models.json lists every routable model; only usable ones are offered."""
        _configure_discovery_backends(monkeypatch, grok=True)
        monkeypatch.setattr(
            "core.config.model_mode._load_models_json",
            lambda: {"deepseek/deepseek-chat": {}, "grok-4.6": {}},
        )
        config = AnimaWorksConfig()
        config.anima_defaults.model = "deepseek/deepseek-chat"

        ids = {model.model for model in discover_models(config=config)}

        # Configured for an Anima → stays; catalog-only without a key → hidden.
        assert "deepseek/deepseek-chat" in ids

        config.anima_defaults.model = "grok/grok-4.6"
        invalidate_cache()
        ids = {model.model for model in discover_models(config=config, refresh=True)}
        assert "deepseek/deepseek-chat" not in ids

    def test_cli_listed_mode_drops_stale_catalog_names(self, monkeypatch):
        _configure_discovery_backends(monkeypatch, codex=True)
        monkeypatch.setattr("core.config.model_mode._load_models_json", lambda: {"codex/o3": {}})
        monkeypatch.setattr(model_catalog, "is_codex_login_available", lambda: True)

        ids = {model.model for model in discover_models(config=AnimaWorksConfig())}

        assert "codex/gpt-6-astra" in ids
        assert "codex/o3" not in ids

    def test_discovered_model_ids_include_three_forms(self):
        models = [
            DiscoveredModel("c:codex/gpt-5.6-sol", "c", "codex/gpt-5.6-sol", "GPT-5.6-Sol", "Codex", source="codex-cli")
        ]
        with patch("core.config.model_discovery.discover_models", return_value=models) as dm:
            ids = discovered_model_ids()
            assert "c:codex/gpt-5.6-sol" in ids
            assert "codex/gpt-5.6-sol" in ids
            assert "gpt-5.6-sol" in ids
            dm.assert_called_once()
