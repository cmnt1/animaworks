from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import core.integrations.call_human as call_human


def _host_api(monkeypatch: pytest.MonkeyPatch, post: MagicMock) -> None:
    monkeypatch.setattr("core.internal_api.host_api", SimpleNamespace(post=post))


def test_phone_alert_helper_maps_calling_and_skipped_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.json.side_effect = [{"status": "calling"}, {"status": "skipped", "reason": "disabled"}]
    post = MagicMock(return_value=response)
    _host_api(monkeypatch, post)

    assert call_human._send_phone_alert("Subject", "Body", "aoi") == "phone: calling"
    assert call_human._send_phone_alert("Subject", "Body", "aoi") == "phone: skipped (disabled)"
    assert post.call_count == 2
    assert post.call_args.kwargs["json"] == {"anima": "aoi", "subject": "Subject", "body": "Body"}
    assert post.call_args.kwargs["timeout"] == 10.0


def test_phone_alert_helper_does_not_expose_exception_details(monkeypatch: pytest.MonkeyPatch) -> None:
    post = MagicMock(side_effect=RuntimeError("contains-a-secret-value"))
    _host_api(monkeypatch, post)

    result = call_human._send_phone_alert("Subject", "Body", "aoi")

    assert result == "phone: ERROR - RuntimeError"
    assert "contains-a-secret-value" not in result


def _configure_cli(monkeypatch: pytest.MonkeyPatch, *, priority_config: dict | None = None) -> MagicMock:
    monkeypatch.delenv("ANIMAWORKS_TOOL_SESSION_ID", raising=False)
    config = priority_config or {
        "human_notification": {
            "enabled": True,
            "channels": [{"type": "slack", "enabled": True, "config": {"channel": "C123"}}],
        }
    }
    monkeypatch.setattr(call_human, "_load_config", lambda: config)
    monkeypatch.setattr(call_human, "_get_bot_token", lambda _channel_cfg: "test-slack-token")
    monkeypatch.setattr(call_human, "_resolve_cli_anima_identity", lambda _channel_cfg: ("aoi", ""))
    monkeypatch.setattr(call_human, "_resolve_cli_anima_name", lambda: "aoi")
    slack = AsyncMock(return_value=("OK", "1712345678.123"))
    monkeypatch.setattr(call_human, "_send_slack", slack)
    return slack


def test_cli_urgent_sends_phone_alert_after_slack(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    slack = _configure_cli(monkeypatch)
    response = MagicMock()
    response.json.return_value = {"status": "calling"}
    post = MagicMock(return_value=response)
    _host_api(monkeypatch, post)

    call_human.cli_main(["Outage", "API is down", "--priority", "urgent"])

    output = capsys.readouterr().out
    assert "slack: OK" in output
    assert "phone: calling" in output
    slack.assert_awaited_once()
    post.assert_called_once_with(
        "/api/internal/phone/alert",
        json={"anima": "aoi", "subject": "Outage", "body": "API is down"},
        timeout=10.0,
    )


def test_phone_failure_does_not_fail_successful_slack_notification(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    _configure_cli(monkeypatch)
    _host_api(monkeypatch, MagicMock(side_effect=RuntimeError("private detail")))

    call_human.cli_main(["Outage", "API is down", "--priority", "urgent"])

    output = capsys.readouterr().out
    assert "slack: OK" in output
    assert "phone: ERROR - RuntimeError" in output
    assert "private detail" not in output


def test_nonurgent_cli_does_not_call_phone_api(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _configure_cli(monkeypatch)
    post = MagicMock()
    _host_api(monkeypatch, post)

    call_human.cli_main(["Done", "Task complete"])

    assert "slack: OK" in capsys.readouterr().out
    post.assert_not_called()
