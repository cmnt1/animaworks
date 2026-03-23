"""Tests for core/tools/_anima_icon_url.py."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.config.models import (
    AnimaWorksConfig,
    HumanNotificationConfig,
    NotificationChannelConfig,
)
from core.tools._anima_icon_url import (
    DEFAULT_INTERNAL_ICON_PATH_TEMPLATE,
    resolve_anima_icon_identity,
    resolve_anima_icon_url,
    template_is_external_icon_url,
)


def _animas_root(tmp_path):
    return tmp_path / "animas"


def test_resolve_without_server_url_returns_empty(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANIMAWORKS_SERVER_URL", raising=False)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    alice = _animas_root(tmp_path) / "alice" / "assets"
    alice.mkdir(parents=True)
    (alice / "icon.png").write_bytes(b"x")
    assert resolve_anima_icon_url("alice") == ""


def test_resolve_with_server_url_and_icon_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "https://anima.example.jp")
    d = _animas_root(tmp_path) / "rabbit" / "assets"
    d.mkdir(parents=True)
    (d / "icon.png").write_bytes(b"x")
    assert (
        resolve_anima_icon_url("rabbit")
        == "https://anima.example.jp/api/animas/rabbit/assets/icon.png"
    )


def test_internal_path_template_prepends_server_url(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "https://anima.example.jp")
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
        assert (
            resolve_anima_icon_url("rabbit")
            == "https://anima.example.jp/api/animas/rabbit/assets/icon.png"
        )


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


def test_template_is_external_icon_url() -> None:
    assert template_is_external_icon_url("https://cdn/x.png")
    assert template_is_external_icon_url("http://a/b")
    assert not template_is_external_icon_url("/api/animas/{name}/assets/icon.png")
    assert not template_is_external_icon_url("")
