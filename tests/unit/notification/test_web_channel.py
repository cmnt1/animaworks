from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Built-in Web UI notification channel and its tool exposure."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.models import HumanNotificationConfig
from core.notification.channels.web import WebChannel


@pytest.mark.asyncio
async def test_web_channel_posts_to_internal_api():
    resp = MagicMock()
    with patch("core.internal_api.host_api") as host_api:
        host_api.post.return_value = resp
        result = await WebChannel({}).send("Team update", "hinata finished", "normal", anima_name="sakura")

    assert result == "web: OK"
    path = host_api.post.call_args.args[0]
    payload = host_api.post.call_args.kwargs["json"]
    assert path == "/api/internal/notify-web"
    assert payload["anima"] == "sakura"
    assert payload["subject"] == "Team update"
    assert payload["body"] == "hinata finished"
    resp.raise_for_status.assert_called_once()


def _write_status(anima_dir: Path, supervisor: str | None) -> None:
    anima_dir.mkdir(parents=True)
    (anima_dir / "status.json").write_text(json.dumps({"supervisor": supervisor or ""}), encoding="utf-8")


@pytest.mark.parametrize(("supervisor", "expected"), [(None, True), ("sakura", False)])
def test_mcp_exposes_call_human_to_top_level_only(tmp_path, monkeypatch, supervisor, expected):
    import core.mcp.server as mcp_mod

    anima_dir = tmp_path / "animas" / "x"
    _write_status(anima_dir, supervisor)
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))
    cfg = MagicMock()
    cfg.human_notification = HumanNotificationConfig()
    with patch("core.config.models.load_config", return_value=cfg):
        assert mcp_mod._has_notification_channels_for_anima() is expected


def test_mcp_hides_call_human_when_web_ui_off(tmp_path, monkeypatch):
    import core.mcp.server as mcp_mod

    anima_dir = tmp_path / "animas" / "x"
    _write_status(anima_dir, None)
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))
    cfg = MagicMock()
    cfg.human_notification = HumanNotificationConfig(web_ui=False)
    with patch("core.config.models.load_config", return_value=cfg):
        assert mcp_mod._has_notification_channels_for_anima() is False


def test_image_cli_accepts_negative_prompt_alias(tmp_path):
    """The character design guide says "negative prompt"; both spellings work."""
    from core.integrations import _image_cli

    with patch.object(_image_cli, "ImageGenPipeline") as pipeline:
        pipeline.return_value.generate_all.return_value.to_dict.return_value = {}
        _image_cli.cli_main(["pipeline", "1girl", "--anima-dir", str(tmp_path), "--negative-prompt", "lowres"])

    assert pipeline.return_value.generate_all.call_args.kwargs["negative_prompt"] == "lowres"
