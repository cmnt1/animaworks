# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for core.tooling.permissions — evaluate_tool_access / check_tool_access and gate integration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.models import ExternalToolsPermission, PermissionsConfig
from core.tooling.permissions import (
    ToolAccessDecision,
    check_tool_access,
    evaluate_tool_access,
    get_permitted_tools,
)

# ── Helpers ─────────────────────────────────────────────────


def _config(
    *,
    allow_all: bool = True,
    allow: list[str] | None = None,
    deny: list[str] | None = None,
) -> PermissionsConfig:
    return PermissionsConfig(
        external_tools=ExternalToolsPermission(
            allow_all=allow_all,
            allow=allow or [],
            deny=deny or [],
        )
    )


def _ok_decision(decision: ToolAccessDecision, *, reason: str = "ok") -> None:
    assert decision.allowed is True
    assert decision.reason == reason


# ── evaluate_tool_access: table-driven core decision rules ──


class TestEvaluateCore:
    def test_deny_wins_over_everything(self) -> None:
        decision = evaluate_tool_access("slack", None, config=_config(deny=["slack"]), origin="core", profile=None)
        assert decision.allowed is False
        assert decision.reason == "tool_denied"

    def test_allow_all_still_requires_gated_action_permit(self) -> None:
        decision = evaluate_tool_access(
            "gmail",
            "send",
            config=_config(allow_all=True),
            origin="core",
            profile={"send": {"gated": True}},
        )
        assert decision.allowed is False
        assert decision.reason == "action_gated"

    def test_gated_action_allowed_with_explicit_allow(self) -> None:
        decision = evaluate_tool_access(
            "gmail",
            "send",
            config=_config(allow_all=True, allow=["gmail_send"]),
            origin="core",
            profile={"send": {"gated": True}},
        )
        assert decision.allowed is True
        assert decision.reason == "ok"

    def test_gated_action_denied_by_deny_key(self) -> None:
        decision = evaluate_tool_access(
            "gmail",
            "send",
            config=_config(allow_all=True, allow=["gmail_send"], deny=["gmail_send"]),
            origin="core",
            profile={"send": {"gated": True}},
        )
        assert decision.allowed is False
        assert decision.reason == "action_gated"

    def test_non_gated_action_allowed_with_tool_permit(self) -> None:
        decision = evaluate_tool_access(
            "gmail",
            "unread",
            config=_config(allow_all=True),
            origin="core",
            profile={"unread": {"gated": False}},
        )
        assert decision.allowed is True

    def test_gated_as_uses_renamed_key(self) -> None:
        profile = {"upload": {"gated": True, "gated_as": "send"}}
        allowed = evaluate_tool_access(
            "chatwork",
            "upload",
            config=_config(allow_all=True, allow=["chatwork_send"]),
            origin="core",
            profile=profile,
        )
        assert allowed.allowed is True
        blocked = evaluate_tool_access(
            "chatwork", "upload", config=_config(allow_all=True), origin="core", profile=profile
        )
        assert blocked.allowed is False
        assert blocked.reason == "action_gated"

    def test_hyphen_underscore_readthrough(self) -> None:
        profile = {"draft-update": {"gated": True}}
        assert (
            evaluate_tool_access(
                "gmail", "draft_update", config=_config(allow_all=True), origin="core", profile=profile
            ).allowed
            is False
        )
        assert (
            evaluate_tool_access(
                "gmail",
                "draft-update",
                config=_config(allow_all=True, allow=["gmail_draft-update"]),
                origin="core",
                profile=profile,
            ).allowed
            is True
        )
        assert (
            evaluate_tool_access(
                "gmail",
                "draft_update",
                config=_config(allow_all=True, allow=["gmail_draft-update"]),
                origin="core",
                profile=profile,
            ).allowed
            is True
        )

    def test_disabled_service_excluded(self) -> None:
        decision = evaluate_tool_access(
            "slack",
            None,
            config=_config(allow_all=True),
            origin="core",
            profile=None,
            disabled_services=frozenset({"slack"}),
        )
        assert decision.allowed is False
        assert decision.reason == "tool_not_permitted"

    def test_core_tool_not_in_permitted(self) -> None:
        decision = evaluate_tool_access(
            "no_such_tool_xyz", None, config=_config(allow_all=True), origin="core", profile=None
        )
        assert decision.allowed is False
        assert decision.reason == "tool_not_permitted"


# ── evaluate_tool_access: common / personal allow-list ─────


class TestEvaluateCommonPersonal:
    def test_allowlist_blocks_unlisted(self) -> None:
        decision = evaluate_tool_access(
            "bar", None, config=_config(allow_all=False, allow=["foo"]), origin="personal", profile=None
        )
        assert decision.allowed is False
        assert decision.reason == "tool_not_permitted"

    def test_allowlist_allows_listed(self) -> None:
        decision = evaluate_tool_access(
            "foo", None, config=_config(allow_all=False, allow=["foo"]), origin="common", profile=None
        )
        assert decision.allowed is True

    def test_allow_all_deny_only(self) -> None:
        denied = evaluate_tool_access(
            "foo", None, config=_config(allow_all=True, deny=["foo"]), origin="personal", profile=None
        )
        assert denied.allowed is False
        assert denied.reason == "tool_denied"
        allowed = evaluate_tool_access(
            "other", None, config=_config(allow_all=True, deny=["foo"]), origin="personal", profile=None
        )
        assert allowed.allowed is True

    def test_gated_action_allowlist_still_required(self) -> None:
        decision = evaluate_tool_access(
            "mytool",
            "deploy",
            config=_config(allow_all=False, allow=["mytool"]),
            origin="personal",
            profile={"deploy": {"gated": True}},
        )
        assert decision.allowed is False
        assert decision.reason == "action_gated"

    def test_reply_grant_override_is_limited_to_slack_reply_actions(self) -> None:
        slack_send = evaluate_tool_access(
            "slack",
            "send",
            config=_config(allow_all=True),
            origin="core",
            profile={"send": {"gated": True}},
            reply_grant_ok=True,
        )
        other_send = evaluate_tool_access(
            "gmail",
            "send",
            config=_config(allow_all=True),
            origin="core",
            profile={"send": {"gated": True}},
            reply_grant_ok=True,
        )
        slack_update = evaluate_tool_access(
            "slack",
            "channel_update",
            config=_config(allow_all=True),
            origin="core",
            profile={"channel_update": {"gated": True}},
            reply_grant_ok=True,
        )

        assert slack_send.allowed is True
        assert other_send.allowed is False
        assert other_send.reason == "action_gated"
        assert slack_update.allowed is False
        assert slack_update.reason == "action_gated"


# ── get_permitted_tools (moved parse cases) ───────────────


class TestGetPermittedTools:
    def test_all_yes_does_not_auto_allow_gated(self) -> None:
        permitted = get_permitted_tools(_config(allow_all=True))
        assert "gmail" in permitted
        assert "gmail_send" not in permitted

    def test_action_level_deny_excludes(self) -> None:
        permitted = get_permitted_tools(_config(allow_all=True, allow=["gmail_send"], deny=["gmail_send"]))
        assert "gmail" in permitted
        assert "gmail_send" not in permitted

    def test_explicit_gated_allow_included(self) -> None:
        permitted = get_permitted_tools(_config(allow_all=True, allow=["gmail_send"]))
        assert "gmail_send" in permitted
        assert "gmail" in permitted


# ── check_tool_access (loader) ───────────────────────────


class TestCheckToolAccess:
    def test_corrupt_permissions_json_is_check_failed(self, tmp_path: Path) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text("not json", encoding="utf-8")
        decision = check_tool_access(anima, "gmail", None, origin="core")
        assert decision.allowed is False
        assert decision.reason == "check_failed"

    def test_profile_import_exception_is_check_failed(self, tmp_path: Path) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(json.dumps({"external_tools": {"allow_all": True}}), encoding="utf-8")
        with patch("core.tooling.permissions._load_execution_profile", side_effect=RuntimeError("boom")):
            decision = check_tool_access(anima, "gmail", "send", origin="core")
        assert decision.allowed is False
        assert decision.reason == "check_failed"

    def test_none_anima_dir_gated_action_denied(self) -> None:
        decision = check_tool_access(None, "gmail", "send", origin="core")
        assert decision.allowed is False
        assert decision.reason == "action_gated"

    def test_personal_tool_gated_action_denied(self, tmp_path: Path) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(json.dumps({"external_tools": {"allow_all": True}}), encoding="utf-8")
        tool_file = anima / "mytool.py"
        tool_file.write_text(
            'EXECUTION_PROFILE = {"deploy": {"gated": True}}\n',
            encoding="utf-8",
        )
        decision = check_tool_access(anima, "mytool", "deploy", origin="personal", tool_file=tool_file)
        assert decision.allowed is False
        assert decision.reason == "action_gated"

    def test_personal_tool_gated_action_allowed(self, tmp_path: Path) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(
            json.dumps({"external_tools": {"allow_all": True, "allow": ["mytool_deploy"]}}),
            encoding="utf-8",
        )
        tool_file = anima / "mytool.py"
        tool_file.write_text('EXECUTION_PROFILE = {"deploy": {"gated": True}}\n', encoding="utf-8")
        decision = check_tool_access(anima, "mytool", "deploy", origin="personal", tool_file=tool_file)
        assert decision.allowed is True

    def test_core_denied_tool(self, tmp_path: Path) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(
            json.dumps({"external_tools": {"allow_all": True, "deny": ["slack"]}}),
            encoding="utf-8",
        )
        decision = check_tool_access(anima, "slack", None, origin="core")
        assert decision.allowed is False
        assert decision.reason == "tool_denied"

    def test_disabled_inbound_service_does_not_block_call(self, tmp_path: Path) -> None:
        # external_messaging.chatwork.enabled=false disables the inbound
        # integration only; explicit tool calls must keep working.
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(json.dumps({"external_tools": {"allow_all": True}}), encoding="utf-8")
        with patch("core.tooling.permissions._disabled_service_tools", return_value={"chatwork"}):
            decision = check_tool_access(anima, "chatwork", "stats", origin="core")
        assert decision.allowed is True


# ── ExternalToolDispatcher.dispatch fail-closed ────────────


class TestDispatcherFailClosed:
    def test_load_permissions_raises_returns_permission_denied(self, tmp_path: Path) -> None:
        from core.tooling.dispatch import ExternalToolDispatcher

        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text("broken", encoding="utf-8")
        dispatcher = ExternalToolDispatcher(tool_registry=["gmail"], personal_tools={})
        with patch("core.config.models.load_permissions", side_effect=RuntimeError("boom")):
            result = dispatcher.dispatch("gmail_send", {"anima_dir": str(anima), "to": "x@y.z"})
        parsed = json.loads(result)
        assert parsed["error_type"] == "PermissionDenied"
        assert parsed["status"] == "error"


class TestSlackReplyGrantGate:
    def test_manual_timestamp_gate_sample(self, cli_anima: Path) -> None:
        from core.messaging.reply_grants import record_reply_grant
        from core.tooling.dispatch import ExternalToolDispatcher

        assert record_reply_grant(cli_anima, "slack", "C123", "1791155828.085789") is True
        dispatcher = ExternalToolDispatcher(tool_registry=["slack"])

        allowed = dispatcher._check_access(
            "slack_send",
            {
                "anima_dir": str(cli_anima),
                "channel": "C123",
                "message": "reply",
                "thread_ts": "1791155828.085789",
            },
        )
        channel_post_allowed = dispatcher._check_access(
            "slack_channel_post",
            {
                "anima_dir": str(cli_anima),
                "channel_id": "C123",
                "text": "reply",
                "thread_ts": "1791155828.085789",
            },
        )
        denied = dispatcher._check_access(
            "slack_send",
            {
                "anima_dir": str(cli_anima),
                "channel": "C123",
                "message": "reply",
                "thread_ts": "9999.0001",
            },
        )

        assert allowed is None
        assert channel_post_allowed is None
        assert denied is not None
        assert json.loads(denied)["error_type"] == "PermissionDenied"

    @pytest.mark.parametrize(
        ("schema_name", "reply_args"),
        [
            ("slack_send", {"channel": "C123", "thread_ts": "wrong-ts"}),
            ("slack_send", {"channel": "C123"}),
            ("slack_send", {"channel": "C999", "thread_ts": "parent-ts"}),
            ("slack_send", {"channel": "#general", "thread_ts": "parent-ts"}),
            ("slack_channel_post", {"channel_id": "C123", "thread_ts": "wrong-ts"}),
            ("slack_channel_post", {"channel_id": "C123"}),
            ("slack_channel_post", {"channel_id": "C999", "thread_ts": "parent-ts"}),
        ],
    )
    def test_mismatched_target_keeps_gate(self, cli_anima: Path, schema_name: str, reply_args: dict[str, str]) -> None:
        from core.messaging.reply_grants import record_reply_grant
        from core.tooling.dispatch import ExternalToolDispatcher

        assert record_reply_grant(cli_anima, "slack", "C123", "parent-ts") is True
        dispatcher = ExternalToolDispatcher(tool_registry=["slack"])
        error = dispatcher._check_access(schema_name, {"anima_dir": str(cli_anima), **reply_args})

        assert error is not None
        assert json.loads(error)["error_type"] == "PermissionDenied"

    @pytest.mark.parametrize(
        ("denied_name", "schema_name", "reply_args"),
        [
            ("slack", "slack_send", {"channel": "C123", "message": "reply", "thread_ts": "parent-ts"}),
            ("slack_send", "slack_send", {"channel": "C123", "message": "reply", "thread_ts": "parent-ts"}),
            (
                "slack_channel_post",
                "slack_channel_post",
                {"channel_id": "C123", "text": "reply", "thread_ts": "parent-ts"},
            ),
        ],
    )
    def test_explicit_deny_still_wins(
        self,
        cli_anima: Path,
        denied_name: str,
        schema_name: str,
        reply_args: dict[str, str],
    ) -> None:
        from core.messaging.reply_grants import record_reply_grant
        from core.tooling.dispatch import ExternalToolDispatcher

        (cli_anima / "permissions.json").write_text(
            json.dumps({"external_tools": {"allow_all": True, "deny": [denied_name]}}),
            encoding="utf-8",
        )
        assert record_reply_grant(cli_anima, "slack", "C123", "parent-ts") is True
        dispatcher = ExternalToolDispatcher(tool_registry=["slack"])
        error = dispatcher._check_access(schema_name, {"anima_dir": str(cli_anima), **reply_args})

        assert error is not None
        assert json.loads(error)["error_type"] == "PermissionDenied"

    @pytest.mark.parametrize(
        ("action", "tool_args"),
        [
            ("send", {"channel": "C123", "message": "reply", "thread_ts": "parent-ts"}),
            ("channel_post", {"channel_id": "C123", "text": "reply", "thread_ts": "parent-ts"}),
        ],
    )
    def test_use_tool_handler_checks_reply_grant(self, cli_anima: Path, action: str, tool_args: dict[str, str]) -> None:
        from core.messaging.reply_grants import record_reply_grant
        from core.tooling.handler import ToolHandler

        assert record_reply_grant(cli_anima, "slack", "C123", "parent-ts") is True
        handler = ToolHandler(anima_dir=cli_anima, memory=MagicMock(), tool_registry=["slack"])
        with (
            patch("core.integrations.slack.dispatch", return_value="posted") as slack_dispatch,
            patch.object(handler, "_attach_action_rules", side_effect=lambda _name, _args, result: result),
        ):
            result = handler._handle_use_tool(
                {
                    "tool_name": "slack",
                    "action": action,
                    "args": tool_args,
                }
            )

        assert result == "posted"
        slack_dispatch.assert_called_once()
        assert slack_dispatch.call_args.args[0] == f"slack_{action}"


# ── cli_dispatch ─────────────────────────────────────────


@pytest.fixture
def cli_anima(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "cli-anima"
    d.mkdir(parents=True)
    (d / "permissions.json").write_text(
        json.dumps({"external_tools": {"allow_all": True}}),
        encoding="utf-8",
    )
    return d


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, cli_anima: Path) -> None:
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(cli_anima))


class TestCliDispatch:
    def test_denied_tool_exits(self, monkeypatch: pytest.MonkeyPatch, cli_anima: Path, capsys) -> None:
        (cli_anima / "permissions.json").write_text(
            json.dumps({"external_tools": {"allow_all": True, "deny": ["slack"]}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(cli_anima))
        monkeypatch.setattr(sys, "argv", ["animaworks-tool", "slack", "messages"])
        from cli.tool_dispatch import cli_dispatch

        with pytest.raises(SystemExit) as e:
            cli_dispatch()
        assert e.value.code == 1
        assert "Error" in capsys.readouterr().err

    def test_gated_action_with_option_val_not_smuggled(self, monkeypatch, cli_anima: Path, capsys) -> None:
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(cli_anima))
        monkeypatch.setattr(sys, "argv", ["animaworks-tool", "gmail", "--account", "foo", "send"])
        from cli.tool_dispatch import cli_dispatch

        with pytest.raises(SystemExit) as e:
            cli_dispatch()
        assert e.value.code == 1
        assert "send" in capsys.readouterr().err

    def test_personal_gated_action_exits(self, monkeypatch, cli_anima: Path, capsys) -> None:
        personal_dir = cli_anima / "tools"
        personal_dir.mkdir()
        (personal_dir / "mytool.py").write_text(
            'EXECUTION_PROFILE = {"deploy": {"gated": True}}\ndef cli_main(argv=None):\n    pass\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(cli_anima))
        monkeypatch.setattr(sys, "argv", ["animaworks-tool", "mytool", "deploy"])
        from cli.tool_dispatch import cli_dispatch

        with pytest.raises(SystemExit) as e:
            cli_dispatch()
        assert e.value.code == 1
        assert "deploy" in capsys.readouterr().err

    def test_permitted_gated_action_reaches_cli_main(self, monkeypatch, cli_anima: Path, capsys) -> None:
        (cli_anima / "permissions.json").write_text(
            json.dumps({"external_tools": {"allow_all": True, "allow": ["gmail_send"]}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(cli_anima))
        monkeypatch.setattr(sys, "argv", ["animaworks-tool", "gmail", "send", "--to", "x"])
        import core.integrations.gmail as gmail_mod

        mock_cli = MagicMock()
        monkeypatch.setattr(gmail_mod, "cli_main", mock_cli)
        from cli.tool_dispatch import cli_dispatch

        cli_dispatch()  # must not raise SystemExit
        mock_cli.assert_called_once()

    def test_slack_send_with_matching_grant_reaches_mock_api(
        self,
        monkeypatch: pytest.MonkeyPatch,
        cli_anima: Path,
    ) -> None:
        from core.integrations import _slack_cli, _slack_client
        from core.messaging.reply_grants import record_reply_grant

        thread_ts = "1791155828.085789"
        assert record_reply_grant(cli_anima, "slack", "C123", thread_ts) is True
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(cli_anima))
        monkeypatch.setattr(
            sys,
            "argv",
            ["animaworks-tool", "slack", "send", "C123", "<@U123> reply", "--thread", thread_ts],
        )
        monkeypatch.setattr(_slack_cli, "_require_slack_sdk", lambda: None)
        monkeypatch.setattr(_slack_client, "SlackApiError", type("FakeSlackApiError", (Exception,), {}))
        monkeypatch.setattr(_slack_cli, "_resolve_cli_token", lambda: "xoxb-test")
        monkeypatch.setattr(_slack_cli, "_resolve_cli_identity", lambda: ("alice", ""))
        mock_client = MagicMock()
        mock_client.resolve_channel.return_value = "C123"
        mock_client.post_message.return_value = {"channel": "C123", "ts": "new-ts"}
        mock_client_factory = MagicMock(return_value=mock_client)
        monkeypatch.setattr(_slack_cli, "SlackClient", mock_client_factory)

        from cli.tool_dispatch import cli_dispatch

        cli_dispatch()

        mock_client_factory.assert_called_once_with(token="xoxb-test")
        mock_client.resolve_channel.assert_called_once_with("C123")
        mock_client.post_message.assert_called_once()
        assert mock_client.post_message.call_args.args == ("C123", "<@U123> reply")
        assert mock_client.post_message.call_args.kwargs["thread_ts"] == thread_ts

    def test_slack_send_with_duplicate_thread_options_does_not_use_a_grant(
        self,
        monkeypatch: pytest.MonkeyPatch,
        cli_anima: Path,
    ) -> None:
        from core.integrations import _slack_cli
        from core.messaging.reply_grants import record_reply_grant

        assert record_reply_grant(cli_anima, "slack", "C123", "parent-ts") is True
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(cli_anima))
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "animaworks-tool",
                "slack",
                "send",
                "C123",
                "reply",
                "--thread",
                "parent-ts",
                "--thread",
                "other-ts",
            ],
        )
        mock_client_factory = MagicMock()
        monkeypatch.setattr(_slack_cli, "SlackClient", mock_client_factory)

        from cli.tool_dispatch import cli_dispatch

        with pytest.raises(SystemExit) as exc_info:
            cli_dispatch()

        assert exc_info.value.code == 1
        mock_client_factory.assert_not_called()

    def test_slack_send_without_grant_is_blocked_before_api(
        self,
        monkeypatch: pytest.MonkeyPatch,
        cli_anima: Path,
        capsys,
    ) -> None:
        from core.integrations import _slack_cli

        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(cli_anima))
        monkeypatch.setattr(
            sys,
            "argv",
            ["animaworks-tool", "slack", "send", "C123", "reply", "--thread", "parent-ts"],
        )
        mock_client_factory = MagicMock()
        monkeypatch.setattr(_slack_cli, "SlackClient", mock_client_factory)

        from cli.tool_dispatch import cli_dispatch

        with pytest.raises(SystemExit) as exc_info:
            cli_dispatch()

        assert exc_info.value.code == 1
        assert "Error" in capsys.readouterr().err
        mock_client_factory.assert_not_called()


# ── focused check_permissions tool query ──────────────────


class TestCheckPermissionsToolQuery:
    def _handler(self, anima: Path):
        from core.tooling.handler import ToolHandler

        return ToolHandler(anima_dir=anima, memory=MagicMock(), tool_registry=[])

    def test_known_tool_query_uses_shared_access_checker(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        anima = tmp_path / "animas" / "worker"
        anima.mkdir(parents=True)
        handler = self._handler(anima)
        decision = ToolAccessDecision(False, "action_gated")

        with (
            patch("core.integrations.TOOL_MODULES", {"gmail": "core.integrations.gmail"}),
            patch("core.tooling.permissions.check_tool_access", return_value=decision) as check,
        ):
            result = json.loads(handler.handle("check_permissions", {"tool_name": "gmail", "action": "send"}))

        check.assert_called_once_with(anima, "gmail", "send", origin="core", tool_file=None)
        assert result == {"tool": "gmail", "action": "send", "permitted": False, "reason": "action_gated"}

    def test_unknown_tool_query_returns_narrow_denial(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        anima = tmp_path / "animas" / "worker"
        anima.mkdir(parents=True)
        handler = self._handler(anima)

        with (
            patch("core.integrations.TOOL_MODULES", {}),
            patch("core.integrations.discover_common_tools", return_value={}),
            patch("core.integrations.discover_personal_tools", return_value={}),
            patch("core.tooling.permissions.check_tool_access") as check,
        ):
            result = json.loads(handler.handle("check_permissions", {"tool_name": "unknown"}))

        check.assert_not_called()
        assert result == {"tool": "unknown", "action": None, "permitted": False, "reason": "unknown_tool"}


# ── _handle_web_search ──────────────────────────────────


class TestHandleWebSearch:
    def _handler(self, anima: Path) -> MagicMock:
        from core.tooling.handler import ToolHandler

        return ToolHandler(
            anima_dir=anima,
            memory=MagicMock(),
            tool_registry=["web_search"],
        )

    def test_denied_web_search(self, tmp_path: Path) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(
            json.dumps({"external_tools": {"allow_all": True, "deny": ["web_search"]}}),
            encoding="utf-8",
        )
        handler = self._handler(anima)
        with patch("core.integrations.web_search.dispatch") as ws_dispatch:
            result = handler.handle("web_search", {"query": "hello"})
            ws_dispatch.assert_not_called()
        parsed = json.loads(result)
        assert parsed["error_type"] == "PermissionDenied"

    def test_allowed_web_search_calls_dispatch(self, tmp_path: Path) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(json.dumps({"external_tools": {"allow_all": True}}), encoding="utf-8")
        handler = self._handler(anima)
        with patch("core.integrations.web_search.dispatch", return_value=[]) as ws_dispatch:
            result = handler.handle("web_search", {"query": "hello"})
            ws_dispatch.assert_called_once()
        assert "No results found" in result
