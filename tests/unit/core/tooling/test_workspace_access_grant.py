from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.models import AnimaModelConfig, AnimaWorksConfig, load_config, save_config
from core.platform.process_role import PROCESS_ROLE_ENV
from core.tooling.handler import ToolHandler
from core.tooling.policy.schemas import build_unified_tool_list


def _write_config(animas: dict[str, AnimaModelConfig]) -> None:
    save_config(AnimaWorksConfig(animas=animas))


def _make_anima(data_dir: Path, name: str, *, file_roots: list[str] | None = None) -> Path:
    anima_dir = data_dir / "animas" / name
    anima_dir.mkdir(parents=True, exist_ok=True)
    (anima_dir / "permissions.json").write_text(
        json.dumps({"version": 1, "file_roots": file_roots or []}, indent=2),
        encoding="utf-8",
    )
    (anima_dir / "status.json").write_text("{}", encoding="utf-8")
    return anima_dir


def _handler(anima_dir: Path) -> ToolHandler:
    return ToolHandler(
        anima_dir=anima_dir,
        memory=MagicMock(),
        messenger=None,
        tool_registry=[],
    )


def _grant(handler: ToolHandler, alias: str, path: Path, **kwargs: object) -> dict:
    result = handler.handle(
        "grant_workspace_access",
        {
            "alias": alias,
            "path": str(path),
            **kwargs,
        },
    )
    return json.loads(result)


def _root_response(**values: object) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"status": "ok", **values}
    return response


def test_top_level_human_can_grant_self_workspace(data_dir: Path, tmp_path: Path, monkeypatch) -> None:
    top_dir = _make_anima(data_dir, "ritsu")
    _write_config({"ritsu": AnimaModelConfig(supervisor=None)})
    workspace = tmp_path / "finance-dashboard"
    workspace.mkdir()

    monkeypatch.setenv(PROCESS_ROLE_ENV, "task_runner")
    handler = _handler(top_dir)
    handler.set_session_origin("human")
    result = {
        "qualified_alias": "finance-dashboard#12345678",
        "target_anima": "ritsu",
        "permissions_changed": True,
    }
    with patch("core.host_api.host_api.post", return_value=_root_response(**result)) as mock_post:
        parsed = _grant(handler, "finance-dashboard", workspace)

    assert parsed["status"] == "ok"
    assert parsed["target_anima"] == "ritsu"
    assert parsed["permissions_changed"] is True
    assert load_config().workspaces == {}
    payload = mock_post.call_args.kwargs["json"]
    assert payload["alias"] == "finance-dashboard"
    assert payload["path"] == str(workspace.resolve())
    assert payload["target_anima"] == "ritsu"
    assert payload["human_origin"] is True
    assert not json.loads((top_dir / "permissions.json").read_text(encoding="utf-8"))["file_roots"]
    assert "default_workspace" not in json.loads((top_dir / "status.json").read_text(encoding="utf-8"))


def test_workspace_grant_is_delegated_to_root(data_dir: Path, tmp_path: Path, monkeypatch) -> None:
    top_dir = _make_anima(data_dir, "ritsu")
    _write_config({"ritsu": AnimaModelConfig(supervisor=None)})
    workspace = tmp_path / "finance-dashboard"
    workspace.mkdir()

    monkeypatch.setenv(PROCESS_ROLE_ENV, "task_runner")
    handler = _handler(top_dir)
    handler.set_session_origin("human")
    with patch("core.host_api.host_api.post", return_value=_root_response(permissions_changed=True)) as mock_post:
        parsed = _grant(handler, "finance-dashboard", workspace)

    assert parsed["permissions_changed"] is True
    mock_post.assert_called_once()
    assert mock_post.call_args.args == ("/api/internal/workspace/grant",)


def test_non_top_level_cannot_self_grant(data_dir: Path, tmp_path: Path) -> None:
    _make_anima(data_dir, "owner")
    child_dir = _make_anima(data_dir, "ritsu")
    _write_config(
        {
            "owner": AnimaModelConfig(supervisor=None),
            "ritsu": AnimaModelConfig(supervisor="owner"),
        }
    )
    workspace = tmp_path / "finance-dashboard"
    workspace.mkdir()

    handler = _handler(child_dir)
    handler.set_session_origin("human")
    parsed = _grant(handler, "finance-dashboard", workspace)

    assert parsed["status"] == "error"
    assert parsed["error_type"] == "PermissionDenied"
    permissions = json.loads((child_dir / "permissions.json").read_text(encoding="utf-8"))
    assert str(workspace.resolve()) not in permissions["file_roots"]


def test_top_level_can_grant_descendant_workspace(data_dir: Path, tmp_path: Path, monkeypatch) -> None:
    top_dir = _make_anima(data_dir, "owner")
    _make_anima(data_dir, "manager")
    child_dir = _make_anima(data_dir, "ritsu")
    _write_config(
        {
            "owner": AnimaModelConfig(supervisor=None),
            "manager": AnimaModelConfig(supervisor="owner"),
            "ritsu": AnimaModelConfig(supervisor="manager"),
        }
    )
    workspace = tmp_path / "finance-dashboard"
    workspace.mkdir()

    monkeypatch.setenv(PROCESS_ROLE_ENV, "task_runner")
    handler = _handler(top_dir)
    handler.set_session_origin("human")
    with patch("core.host_api.host_api.post", return_value=_root_response(target_anima="ritsu")) as mock_post:
        parsed = _grant(handler, "finance-dashboard", workspace, target_anima="ritsu")

    assert parsed["status"] == "ok"
    assert parsed["target_anima"] == "ritsu"
    assert mock_post.call_args.kwargs["json"]["target_anima"] == "ritsu"
    assert not json.loads((child_dir / "permissions.json").read_text(encoding="utf-8"))["file_roots"]


def test_non_human_origin_is_denied(data_dir: Path, tmp_path: Path) -> None:
    top_dir = _make_anima(data_dir, "ritsu")
    _write_config({"ritsu": AnimaModelConfig(supervisor=None)})
    workspace = tmp_path / "finance-dashboard"
    workspace.mkdir()

    handler = _handler(top_dir)
    handler.set_session_origin("system")
    handler._trigger = "heartbeat"
    parsed = _grant(handler, "finance-dashboard", workspace)

    assert parsed["status"] == "error"
    assert parsed["error_type"] == "PermissionDenied"


def test_anima_home_path_is_denied(data_dir: Path) -> None:
    top_dir = _make_anima(data_dir, "owner")
    child_dir = _make_anima(data_dir, "ritsu")
    _write_config(
        {
            "owner": AnimaModelConfig(supervisor=None),
            "ritsu": AnimaModelConfig(supervisor="owner"),
        }
    )

    handler = _handler(top_dir)
    handler.set_session_origin("human")
    parsed = _grant(handler, "ritsu-home", child_dir, target_anima="ritsu")

    assert parsed["status"] == "error"
    assert parsed["error_type"] == "PermissionDenied"


def test_grant_workspace_access_is_exposed_in_tool_schemas() -> None:
    mode_ab_names = {tool["name"] for tool in build_unified_tool_list(trigger="message:human")}

    assert "grant_workspace_access" in mode_ab_names


def test_grant_workspace_access_is_exposed_via_mcp() -> None:
    from core.mcp.server import MCP_TOOLS
    from core.tooling.policy.surface import MCP_TOOL_NAMES

    assert "grant_workspace_access" in MCP_TOOL_NAMES
    assert any(tool.name == "grant_workspace_access" for tool in MCP_TOOLS)
