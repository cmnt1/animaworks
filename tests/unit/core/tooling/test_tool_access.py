# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for core.tooling.permissions — evaluate_tool_access / check_tool_access and gate integration."""

from __future__ import annotations

import argparse
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
        from core.integrations import cli_dispatch

        with pytest.raises(SystemExit) as e:
            cli_dispatch()
        assert e.value.code == 1
        assert "Error" in capsys.readouterr().err

    def test_gated_action_with_option_val_not_smuggled(self, monkeypatch, cli_anima: Path, capsys) -> None:
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(cli_anima))
        monkeypatch.setattr(sys, "argv", ["animaworks-tool", "gmail", "--account", "foo", "send"])
        from core.integrations import cli_dispatch

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
        from core.integrations import cli_dispatch

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
        from core.integrations import cli_dispatch

        cli_dispatch()  # must not raise SystemExit
        mock_cli.assert_called_once()


# ── internal check-permissions ───────────────────────────


class TestCmdCheckPermissions:
    def test_denied_tool_reported(self, tmp_path: Path, capsys) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(
            json.dumps({"external_tools": {"allow_all": True, "deny": ["gmail"]}}),
            encoding="utf-8",
        )
        from cli.commands.internal_cmd import _cmd_check_permissions

        args = argparse.Namespace(tool_name="gmail", action=None)
        _cmd_check_permissions(args, anima)
        out = json.loads(capsys.readouterr().out)
        assert out["permitted"] is False
        assert out["reason"] == "tool_denied"

    def test_gated_action_not_allowed(self, tmp_path: Path, capsys) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(json.dumps({"external_tools": {"allow_all": True}}), encoding="utf-8")
        from cli.commands.internal_cmd import _cmd_check_permissions

        _cmd_check_permissions(argparse.Namespace(tool_name="gmail", action="send"), anima)
        out = json.loads(capsys.readouterr().out)
        assert out["permitted"] is False
        assert out["reason"] == "action_gated"
        assert out["action"] == "send"

    def test_allowed_gated_action(self, tmp_path: Path, capsys) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(
            json.dumps({"external_tools": {"allow_all": True, "allow": ["gmail_send"]}}),
            encoding="utf-8",
        )
        from cli.commands.internal_cmd import _cmd_check_permissions

        _cmd_check_permissions(argparse.Namespace(tool_name="gmail", action="send"), anima)
        out = json.loads(capsys.readouterr().out)
        assert out["permitted"] is True
        assert out["reason"] == "ok"

    def test_unknown_tool(self, tmp_path: Path, capsys) -> None:
        anima = tmp_path / "a"
        anima.mkdir()
        (anima / "permissions.json").write_text(json.dumps({"external_tools": {"allow_all": True}}), encoding="utf-8")
        from cli.commands.internal_cmd import _cmd_check_permissions

        _cmd_check_permissions(argparse.Namespace(tool_name="no_such_tool_xyz", action=None), anima)
        out = json.loads(capsys.readouterr().out)
        assert out["permitted"] is False
        assert out["reason"] == "unknown_tool"


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
