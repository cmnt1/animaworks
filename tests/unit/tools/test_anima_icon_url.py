"""Tests for core/tools/_anima_icon_url.py."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from core.config.models import (
    AnimaWorksConfig,
    HumanNotificationConfig,
    NotificationChannelConfig,
)
from core.tools._anima_icon_url import (
    _ICON_URL_TEMPLATE_ENV_KEY,
    DEFAULT_INTERNAL_ICON_PATH_TEMPLATE,
    persist_anima_icon_path_template,
    resolve_anima_icon_identity,
    resolve_anima_icon_url,
    template_is_external_icon_url,
)


def _animas_root(tmp_path):
    return tmp_path / "animas"


# ── template_is_external_icon_url ───────────────────────────────────────────


def test_template_is_external_icon_url() -> None:
    assert template_is_external_icon_url("https://cdn/x.png")
    assert template_is_external_icon_url("http://a/b")
    assert not template_is_external_icon_url("/api/animas/{name}/assets/icon.png")
    assert not template_is_external_icon_url("")


# ── Layer 1: Per-Anima icon_url from status.json ───────────────────────────


class TestPerAnimaIconUrl:
    def test_returns_icon_url_from_status_json(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
        anima_dir = _animas_root(tmp_path) / "sakura"
        anima_dir.mkdir(parents=True)
        (anima_dir / "status.json").write_text(
            json.dumps({"name": "sakura", "icon_url": "https://custom.cdn/sakura.png"}),
            encoding="utf-8",
        )
        assert resolve_anima_icon_url("sakura") == "https://custom.cdn/sakura.png"

    def test_empty_icon_url_falls_through(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
        anima_dir = _animas_root(tmp_path) / "mei"
        anima_dir.mkdir(parents=True)
        (anima_dir / "status.json").write_text(
            json.dumps({"name": "mei", "icon_url": ""}),
            encoding="utf-8",
        )
        assert resolve_anima_icon_url("mei") == ""

    def test_missing_status_json_falls_through(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
        assert resolve_anima_icon_url("nobody") == ""

    def test_non_http_icon_url_rejected(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
        anima_dir = _animas_root(tmp_path) / "evil"
        anima_dir.mkdir(parents=True)
        (anima_dir / "status.json").write_text(
            json.dumps({"name": "evil", "icon_url": "javascript:alert(1)"}),
            encoding="utf-8",
        )
        assert resolve_anima_icon_url("evil") == ""


# ── Layer 2: ICON_URL_TEMPLATE env var ──────────────────────────────────────


class TestEnvVarTemplate:
    def test_env_var_template_expands_name(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.setenv(_ICON_URL_TEMPLATE_ENV_KEY, "https://github.example/{name}.png")
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        assert resolve_anima_icon_url("alice") == "https://github.example/alice.png"

    def test_malformed_template_returns_empty(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.setenv(_ICON_URL_TEMPLATE_ENV_KEY, "https://cdn/{name}/{foo}.png")
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        assert resolve_anima_icon_url("alice") == ""

    def test_env_var_takes_priority_over_config(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.setenv(_ICON_URL_TEMPLATE_ENV_KEY, "https://env.example/{name}.png")
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        cfg = AnimaWorksConfig(icon_url_template="https://config.example/{name}.png")
        with patch("core.config.load_config", return_value=cfg):
            assert resolve_anima_icon_url("bob") == "https://env.example/bob.png"


# ── Layer 3: config.json icon_url_template ──────────────────────────────────


class TestGlobalConfigTemplate:
    def test_global_template_expands_name(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        cfg = AnimaWorksConfig(icon_url_template="https://mycdn.example/{name}.png")
        with patch("core.config.load_config", return_value=cfg):
            assert resolve_anima_icon_url("carol") == "https://mycdn.example/carol.png"

    def test_global_template_takes_priority_over_per_channel(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        cfg = AnimaWorksConfig(
            icon_url_template="https://global.example/{name}.png",
            human_notification=HumanNotificationConfig(
                enabled=True,
                channels=[
                    NotificationChannelConfig(
                        type="slack",
                        enabled=True,
                        config={
                            "channel": "C1",
                            "icon_path_template": "https://channel.example/{name}.png",
                        },
                    ),
                ],
            ),
        )
        with patch("core.config.load_config", return_value=cfg):
            assert resolve_anima_icon_url("dave") == "https://global.example/dave.png"


# ── Full priority chain ────────────────────────────────────────────────────


class TestResolutionPriority:
    """Verify per-Anima > env var > config > per-channel > internal fallback."""

    def test_per_anima_beats_everything(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.setenv(_ICON_URL_TEMPLATE_ENV_KEY, "https://env/{name}.png")
        monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "https://server.example")
        anima_dir = _animas_root(tmp_path) / "sakura"
        anima_dir.mkdir(parents=True)
        (anima_dir / "status.json").write_text(
            json.dumps({"name": "sakura", "icon_url": "https://override/sakura.png"}),
            encoding="utf-8",
        )
        cfg = AnimaWorksConfig(
            icon_url_template="https://config/{name}.png",
            human_notification=HumanNotificationConfig(
                enabled=True,
                channels=[
                    NotificationChannelConfig(
                        type="slack",
                        enabled=True,
                        config={"channel": "C1", "icon_path_template": "https://channel/{name}.png"},
                    ),
                ],
            ),
        )
        with patch("core.config.load_config", return_value=cfg):
            assert resolve_anima_icon_url("sakura") == "https://override/sakura.png"

    def test_env_var_beats_config_and_channel(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.setenv(_ICON_URL_TEMPLATE_ENV_KEY, "https://env/{name}.png")
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        cfg = AnimaWorksConfig(
            icon_url_template="https://config/{name}.png",
            human_notification=HumanNotificationConfig(
                enabled=True,
                channels=[
                    NotificationChannelConfig(
                        type="slack",
                        enabled=True,
                        config={"channel": "C1", "icon_path_template": "https://channel/{name}.png"},
                    ),
                ],
            ),
        )
        with patch("core.config.load_config", return_value=cfg):
            assert resolve_anima_icon_url("x") == "https://env/x.png"

    def test_config_beats_per_channel(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
        monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
        cfg = AnimaWorksConfig(
            icon_url_template="https://config/{name}.png",
            human_notification=HumanNotificationConfig(
                enabled=True,
                channels=[
                    NotificationChannelConfig(
                        type="slack",
                        enabled=True,
                        config={"channel": "C1", "icon_path_template": "https://channel/{name}.png"},
                    ),
                ],
            ),
        )
        with patch("core.config.load_config", return_value=cfg):
            assert resolve_anima_icon_url("y") == "https://config/y.png"


# ── Layer 4: per-channel backward compatibility ─────────────────────────────


def test_resolve_without_server_url_returns_empty(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
    monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    alice = _animas_root(tmp_path) / "alice" / "assets"
    alice.mkdir(parents=True)
    (alice / "icon.png").write_bytes(b"x")
    assert resolve_anima_icon_url("alice") == ""


def test_resolve_with_server_url_and_icon_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "https://anima.example.jp")
    monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
    d = _animas_root(tmp_path) / "rabbit" / "assets"
    d.mkdir(parents=True)
    (d / "icon.png").write_bytes(b"x")
    assert resolve_anima_icon_url("rabbit") == "https://anima.example.jp/api/animas/rabbit/assets/icon.png"


def test_resolve_with_server_url_and_bustup_file_when_icon_missing(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "https://anima.example.jp")
    monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
    rabbit = _animas_root(tmp_path) / "rabbit" / "assets"
    rabbit.mkdir(parents=True)
    (rabbit / "avatar_bustup_realistic.png").write_bytes(b"x")
    assert (
        resolve_anima_icon_url("rabbit")
        == "https://anima.example.jp/api/animas/rabbit/assets/avatar_bustup_realistic.png"
    )


def test_internal_path_template_prepends_server_url(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "https://anima.example.jp")
    monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
    cfg = AnimaWorksConfig(
        human_notification=HumanNotificationConfig(
            enabled=True,
            channels=[
                NotificationChannelConfig(
                    type="slack",
                    enabled=True,
                    config={
                        "channel": "C1",
                        "icon_path_template": DEFAULT_INTERNAL_ICON_PATH_TEMPLATE,
                    },
                ),
            ],
        ),
    )
    with patch("core.config.load_config", return_value=cfg):
        assert resolve_anima_icon_url("rabbit") == "https://anima.example.jp/api/animas/rabbit/assets/icon.png"


def test_http_template_no_file_check() -> None:
    cfg = AnimaWorksConfig(
        human_notification=HumanNotificationConfig(
            enabled=True,
            channels=[
                NotificationChannelConfig(
                    type="slack",
                    enabled=True,
                    config={
                        "channel": "C1",
                        "icon_path_template": "https://cdn.example.com/{name}/icon.png",
                    },
                ),
            ],
        ),
    )
    with patch("core.config.load_config", return_value=cfg):
        name, url = resolve_anima_icon_identity("me")
    assert name == "me"
    assert url == "https://cdn.example.com/me/icon.png"


def test_first_enabled_slack_channel_template_used_when_no_channel_config() -> None:
    """``channel_config=None`` → first enabled Slack channel's template."""
    cfg = AnimaWorksConfig(
        human_notification=HumanNotificationConfig(
            enabled=True,
            channels=[
                NotificationChannelConfig(
                    type="slack",
                    enabled=True,
                    config={
                        "channel": "C1",
                        "icon_path_template": "https://first.example/{name}.png",
                    },
                ),
            ],
        ),
    )
    with patch("core.config.load_config", return_value=cfg):
        url = resolve_anima_icon_url("x", channel_config=None)
    assert url == "https://first.example/x.png"


def test_channel_config_overrides_first_slack() -> None:
    cfg = AnimaWorksConfig(
        human_notification=HumanNotificationConfig(
            enabled=True,
            channels=[
                NotificationChannelConfig(
                    type="slack",
                    enabled=True,
                    config={
                        "channel": "C1",
                        "icon_path_template": "https://first.example/{name}.png",
                    },
                ),
            ],
        ),
    )
    with patch("core.config.load_config", return_value=cfg):
        url = resolve_anima_icon_url(
            "x",
            channel_config={"icon_path_template": "https://override.example/{name}.png"},
        )
    assert url == "https://override.example/x.png"


def test_empty_name_returns_empty() -> None:
    assert resolve_anima_icon_url("") == ""
    assert resolve_anima_icon_identity("") == ("", "")


def test_legacy_icon_url_template_key_still_read() -> None:
    """Old config key ``icon_url_template`` is used when ``icon_path_template`` is absent."""
    cfg = AnimaWorksConfig(
        human_notification=HumanNotificationConfig(
            enabled=True,
            channels=[
                NotificationChannelConfig(
                    type="slack",
                    enabled=True,
                    config={
                        "channel": "C1",
                        "icon_url_template": "https://legacy.example/{name}.png",
                    },
                ),
            ],
        ),
    )
    with patch("core.config.load_config", return_value=cfg):
        assert resolve_anima_icon_url("z") == "https://legacy.example/z.png"


# ── persist_anima_icon_path_template ────────────────────────────────────────


class TestPersistGuard:
    """persist_anima_icon_path_template should skip when higher layers set."""

    def test_skips_when_env_var_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(_ICON_URL_TEMPLATE_ENV_KEY, "https://env/{name}.png")
        cfg = AnimaWorksConfig(
            human_notification=HumanNotificationConfig(
                enabled=True,
                channels=[
                    NotificationChannelConfig(
                        type="slack",
                        enabled=True,
                        config={"channel": "C1"},
                    ),
                ],
            ),
        )
        with patch("core.config.load_config", return_value=cfg) as mock_load:
            persist_anima_icon_path_template()
        mock_load.assert_not_called()

    def test_skips_when_global_template_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
        cfg = AnimaWorksConfig(icon_url_template="https://global/{name}.png")
        with (
            patch("core.config.load_config", return_value=cfg),
            patch("core.config.save_config") as mock_save,
        ):
            persist_anima_icon_path_template()
        mock_save.assert_not_called()

    def test_skips_external_url_channels(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
        cfg = AnimaWorksConfig(
            human_notification=HumanNotificationConfig(
                enabled=True,
                channels=[
                    NotificationChannelConfig(
                        type="slack",
                        enabled=True,
                        config={
                            "channel": "C1",
                            "icon_path_template": "https://github.example/{name}.png",
                        },
                    ),
                ],
            ),
        )
        with (
            patch("core.config.load_config", return_value=cfg),
            patch("core.config.save_config") as mock_save,
        ):
            persist_anima_icon_path_template()
        mock_save.assert_not_called()

    def test_updates_internal_channel_without_template(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from core.config.models import ImageGenConfig

        monkeypatch.delenv(_ICON_URL_TEMPLATE_ENV_KEY, raising=False)
        cfg = AnimaWorksConfig(
            image_gen=ImageGenConfig(image_style="anime"),
            human_notification=HumanNotificationConfig(
                enabled=True,
                channels=[
                    NotificationChannelConfig(
                        type="slack",
                        enabled=True,
                        config={"channel": "C1"},
                    ),
                ],
            ),
        )
        with (
            patch("core.config.load_config", return_value=cfg),
            patch("core.config.save_config") as mock_save,
        ):
            persist_anima_icon_path_template()
        mock_save.assert_called_once()
        assert cfg.human_notification.channels[0].config["icon_path_template"] == DEFAULT_INTERNAL_ICON_PATH_TEMPLATE
