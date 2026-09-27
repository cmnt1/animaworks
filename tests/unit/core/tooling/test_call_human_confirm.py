"""call_human requires a per-session confirmation key before it notifies."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.exceptions import ConfigError
from core.notification import CallHumanKeys


def _make_handler(tmp_path: Path):
    anima_dir = tmp_path / "animas" / "mei"
    (anima_dir / "activity_log").mkdir(parents=True)
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
    notifier.notify = AsyncMock(return_value=["ok"])
    handler._human_notifier = notifier
    return handler, notifier


def _issued_key(result: str) -> str:
    return json.loads(result)["message"].split('sha="')[1][:8]


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


def test_cli_requires_key_only_inside_anima_session(tmp_path: Path, monkeypatch, capsys):
    from core.integrations import call_human as cli

    server_keys = CallHumanKeys()
    monkeypatch.setattr(cli, "_check_confirm_key_via_server", lambda a, s, sha: server_keys.check(a, s, sha) or "")
    monkeypatch.setattr(cli, "_load_config", lambda: {"human_notification": {"enabled": False}})
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(tmp_path / "mei"))
    monkeypatch.setenv("ANIMAWORKS_TOOL_SESSION_ID", "sess1")
    with pytest.raises(SystemExit) as exc:
        cli.cli_main(["s", "b"])
    assert exc.value.code == 2
    key = capsys.readouterr().err.split('--sha "')[1][:8]

    # Correct key passes the gate (then stops at the disabled-config check).
    with pytest.raises(SystemExit) as exc:
        cli.cli_main(["s", "b", "--sha", key])
    assert exc.value.code == 1

    # Humans (no session id) are not gated.
    monkeypatch.delenv("ANIMAWORKS_TOOL_SESSION_ID")
    with pytest.raises(SystemExit) as exc:
        cli.cli_main(["s", "b"])
    assert exc.value.code == 1


def test_cli_fails_open_when_server_unreachable(monkeypatch):
    from core.integrations import call_human as cli

    monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://127.0.0.1:9")
    assert cli._check_confirm_key_via_server("mei", "sess1", "") == ""
