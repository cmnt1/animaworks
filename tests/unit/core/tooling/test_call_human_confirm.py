"""call_human requires a per-session confirmation key before it notifies."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.exceptions import ConfigError
from core.notification import CallHumanKeys


def _make_handler(tmp_path: Path):
    anima_dir = tmp_path / "animas" / "mei"
    (anima_dir / "activity_log").mkdir(parents=True, exist_ok=True)
    memory = MagicMock()
    memory.anima_dir = anima_dir
    with (
        patch("core.tooling.handler.ExternalToolDispatcher"),
        patch("core.config.models.load_config", side_effect=ConfigError("skip")),
    ):
        from core.tooling.handler import ToolHandler

        handler = ToolHandler(anima_dir=anima_dir, memory=memory)
    notifier = MagicMock()
    notifier.channel_count = 1
    notifier.has_external_channels = True
    notifier.notify = AsyncMock(return_value=["ok"])
    handler._human_notifier = notifier
    return handler, notifier


def _issued_key(result: str) -> str:
    return json.loads(result)["message"].split('sha="')[1][:8]


def _confirmation_api(monkeypatch: pytest.MonkeyPatch, keys: CallHumanKeys) -> MagicMock:
    def confirm(path: str, *, json: dict, timeout: float):
        assert path == "/api/internal/call-human/confirm"
        assert timeout == 10.0
        issued_key = keys.check(json["anima_name"], json["session_id"], json.get("sha", ""))
        response = MagicMock()
        response.json.return_value = {"ok": issued_key is None, "sha": issued_key or ""}
        return response

    post = MagicMock(side_effect=confirm)
    monkeypatch.setattr("core.internal_api.host_api", SimpleNamespace(post=post))
    return post


def test_keys_are_random_per_session():
    keys = CallHumanKeys()
    k1 = keys.check("mei", "s1", "")
    assert k1 and len(k1) == 8
    assert keys.check("mei", "s1", "") == k1
    assert keys.check("mei", "s1", k1) is None
    assert keys.check("mei", "s2", k1) not in (None, k1)


def test_first_call_is_denied_with_key_and_nothing_sent(tmp_path: Path):
    handler, notifier = _make_handler(tmp_path)
    result = handler._handle_call_human({"subject": "s", "body": "b"})
    assert json.loads(result)["error_type"] == "ConfirmationRequired"
    assert len(_issued_key(result)) == 8
    notifier.notify.assert_not_called()


def test_wrong_key_is_denied(tmp_path: Path):
    handler, notifier = _make_handler(tmp_path)
    handler._handle_call_human({"subject": "s", "body": "b"})
    result = handler._handle_call_human({"subject": "s", "body": "b", "sha": "deadbeef"})
    assert "ConfirmationRequired" in result
    notifier.notify.assert_not_called()


def test_matching_key_sends_every_time(tmp_path: Path):
    handler, notifier = _make_handler(tmp_path)
    key = _issued_key(handler._handle_call_human({"subject": "s", "body": "b"}))
    for _ in range(2):
        result = handler._handle_call_human({"subject": "s", "body": "b", "sha": key.upper()})
        assert "ConfirmationRequired" not in result
    assert notifier.notify.call_count == 2


def test_denied_call_is_not_logged_as_human_notify(tmp_path: Path):
    handler, _ = _make_handler(tmp_path)
    logged: list[str] = []
    handler._activity.log = lambda event_type, **kw: logged.append(event_type)
    args = {"subject": "s", "body": "b"}
    key = _issued_key(handler._handle_call_human(args))
    handler._log_tool_activity("call_human", args)
    handler._handle_call_human({**args, "sha": key})
    handler._log_tool_activity("call_human", {**args, "sha": key})
    assert logged == ["tool_use", "human_notify"]


def test_cli_confirmation_survives_standalone_handler_processes(tmp_path: Path, monkeypatch, capsys):
    from core.integrations import call_human as cli

    keys = CallHumanKeys()
    post = _confirmation_api(monkeypatch, keys)
    first_handler, first_notifier = _make_handler(tmp_path)
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(first_handler._anima_dir))
    monkeypatch.setenv("ANIMAWORKS_TOOL_SESSION_ID", "sess1")
    monkeypatch.setattr(
        "core.tooling.standalone.run_tool_for_current_anima",
        lambda name, args: first_handler.handle(name, args),
    )

    with pytest.raises(SystemExit) as exc:
        cli.cli_main(["s", "b"])
    assert exc.value.code == 1
    first_result = capsys.readouterr().out
    key = _issued_key(first_result)
    assert len(key) == 8
    first_notifier.notify.assert_not_called()
    assert post.call_args.kwargs["json"]["session_id"] == "sess1"

    # A fresh standalone ToolHandler uses the same server-side key for the CLI session.
    next_handler, next_notifier = _make_handler(tmp_path)
    monkeypatch.setattr(
        "core.tooling.standalone.run_tool_for_current_anima",
        lambda name, args: next_handler.handle(name, args),
    )
    cli.cli_main(["s", "b", "--sha", key])

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "sent"
    next_notifier.notify.assert_awaited_once()
    assert post.call_count == 2


def test_cli_confirmation_fails_closed_when_server_unreachable(tmp_path: Path, monkeypatch):
    handler, notifier = _make_handler(tmp_path)
    monkeypatch.setenv("ANIMAWORKS_TOOL_SESSION_ID", "sess1")
    monkeypatch.setattr(
        "core.internal_api.host_api",
        SimpleNamespace(post=MagicMock(side_effect=RuntimeError("server unavailable"))),
    )

    result = json.loads(handler.handle("call_human", {"subject": "s", "body": "b"}))

    assert result["status"] == "error"
    assert result["error_type"] == "ConfirmationUnavailable"
    notifier.notify.assert_not_called()


def test_web_only_notification_skips_external_confirmation(tmp_path: Path, monkeypatch):
    handler, notifier = _make_handler(tmp_path)
    notifier.has_external_channels = False
    monkeypatch.setenv("ANIMAWORKS_TOOL_SESSION_ID", "sess1")
    post = MagicMock()
    monkeypatch.setattr("core.internal_api.host_api", SimpleNamespace(post=post))

    result = json.loads(handler.handle("call_human", {"subject": "s", "body": "b"}))

    assert result["status"] == "sent"
    post.assert_not_called()
    notifier.notify.assert_awaited_once()


def _phone_api(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {"status": "calling"}
    post = MagicMock(return_value=response)
    monkeypatch.setattr("core.internal_api.host_api", SimpleNamespace(post=post))
    return post


def test_urgent_tool_call_rings_phone_like_the_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    handler, notifier = _make_handler(tmp_path)
    post = _phone_api(monkeypatch)
    args = {"subject": "Outage", "body": "API is down", "priority": "urgent"}
    key = _issued_key(handler._handle_call_human(args))
    post.assert_not_called()

    result = json.loads(handler._handle_call_human({**args, "sha": key}))

    assert result["results"] == ["ok", "phone: calling"]
    notifier.notify.assert_awaited_once()
    post.assert_called_once_with(
        "/api/internal/phone/alert",
        json={"anima": handler._anima_name, "subject": "Outage", "body": "API is down"},
        timeout=10.0,
    )


def test_nonurgent_tool_call_does_not_ring_phone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    handler, _ = _make_handler(tmp_path)
    post = _phone_api(monkeypatch)
    args = {"subject": "s", "body": "b", "priority": "high"}
    key = _issued_key(handler._handle_call_human(args))
    handler._handle_call_human({**args, "sha": key})
    post.assert_not_called()


def test_urgent_tool_call_rings_phone_without_other_channels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    handler, notifier = _make_handler(tmp_path)
    notifier.channel_count = 0
    post = _phone_api(monkeypatch)

    result = json.loads(handler._handle_call_human({"subject": "s", "body": "b", "priority": "urgent"}))

    assert result["error_type"] == "NotConfigured"
    assert result["context"] == {"phone": "phone: calling"}
    post.assert_called_once()
