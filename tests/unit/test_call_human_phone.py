from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import core.integrations.call_human as call_human
from core.exceptions import ConfigError
from core.notification.notifier import HumanNotifier
from core.phone.urgent import request_phone_alert


def _host_api(monkeypatch: pytest.MonkeyPatch, post: MagicMock) -> None:
    monkeypatch.setattr("core.internal_api.host_api", SimpleNamespace(post=post))


def _make_handler(tmp_path, notifier: HumanNotifier):
    anima_dir = tmp_path / "animas" / "aoi"
    (anima_dir / "activity_log").mkdir(parents=True)
    memory = MagicMock()
    memory.anima_dir = anima_dir
    with (
        patch("core.tooling.handler.ExternalToolDispatcher"),
        patch("core.config.models.load_config", side_effect=ConfigError("skip config discovery")),
    ):
        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir=anima_dir, memory=memory, human_notifier=notifier)
    return handler


def test_phone_alert_helper_maps_calling_and_skipped_statuses(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.json.side_effect = [{"status": "calling"}, {"status": "skipped", "reason": "disabled"}]
    post = MagicMock(return_value=response)
    _host_api(monkeypatch, post)

    assert request_phone_alert("Subject", "Body", "aoi") == "phone: calling"
    assert request_phone_alert("Subject", "Body", "aoi") == "phone: skipped (disabled)"
    assert post.call_count == 2
    assert post.call_args.kwargs["json"] == {"anima": "aoi", "subject": "Subject", "body": "Body"}
    assert post.call_args.kwargs["timeout"] == 10.0


def test_phone_alert_helper_does_not_expose_exception_details(monkeypatch: pytest.MonkeyPatch) -> None:
    post = MagicMock(side_effect=RuntimeError("contains-a-secret-value"))
    _host_api(monkeypatch, post)

    result = request_phone_alert("Subject", "Body", "aoi")

    assert result == "phone: ERROR - RuntimeError"
    assert "contains-a-secret-value" not in result


def test_cli_call_human_delegates_flags_to_tool_handler(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    anima_dir = tmp_path / "animas" / "aoi"
    anima_dir.mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))
    result = '{"status":"sent","results":["chatwork: OK"]}'
    run_tool = MagicMock(return_value=result)
    monkeypatch.setattr("core.tooling.standalone.run_tool_for_current_anima", run_tool)

    call_human.cli_main(
        [
            "Approval",
            "Please review",
            "--priority",
            "high",
            "--interactive",
            "--callback-id",
            "cb-fixed",
            "--options",
            "approve,reject",
            "--category",
            "review",
            "--sha",
            "deadbeef",
        ]
    )

    run_tool.assert_called_once_with(
        "call_human",
        {
            "subject": "Approval",
            "body": "Please review",
            "priority": "high",
            "interactive": True,
            "category": "review",
            "options": ["approve", "reject"],
            "callback_id": "cb-fixed",
            "sha": "deadbeef",
        },
    )
    assert capsys.readouterr().out == result + "\n"


def test_cli_call_human_exits_nonzero_for_handler_errors(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    result = '{"status":"error","error_type":"ConfirmationRequired","message":"not sent"}\n[ACTION-RULE]'
    monkeypatch.setattr("core.tooling.standalone.run_tool_for_current_anima", MagicMock(return_value=result))

    with pytest.raises(SystemExit) as exc_info:
        call_human.cli_main(["Subject", "Body"])

    assert exc_info.value.code == 1
    assert capsys.readouterr().out == result + "\n"


def test_cli_uses_non_slack_handler_channel_and_urgent_rings_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    capsys,
) -> None:
    channel = MagicMock()
    channel.channel_type = "chatwork"
    channel.send = AsyncMock(return_value="chatwork: OK")
    notifier = HumanNotifier([channel])
    handler = _make_handler(tmp_path, notifier)
    key = handler._call_human_keys.check(handler._anima_name, handler.session_id, "")
    assert key is not None

    monkeypatch.delenv("ANIMAWORKS_TOOL_SESSION_ID", raising=False)
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(handler._anima_dir))
    monkeypatch.setattr(
        "core.tooling.standalone.run_tool_for_current_anima",
        lambda name, args: handler.handle(name, args),
    )
    response = MagicMock()
    response.json.return_value = {"status": "calling"}
    post = MagicMock(return_value=response)
    _host_api(monkeypatch, post)

    call_human.cli_main(["Outage", "API is down", "--priority", "urgent", "--sha", key])

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "sent"
    assert result["results"].count("chatwork: OK") == 1
    assert result["results"].count("phone: calling") == 1
    channel.send.assert_awaited_once()
    post.assert_called_once_with(
        "/api/internal/phone/alert",
        json={"anima": "aoi", "subject": "Outage", "body": "API is down"},
        timeout=10.0,
    )
