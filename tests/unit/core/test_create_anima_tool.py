"""Unit tests for the root-API-backed create_anima tool handler."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from core.tooling.handler import ToolHandler

_SHEET_CONTENT = """\
# Character: hinata

## 基本情報

| 項目 | 設定 |
|------|------|
| 英名 | hinata |

## 人格

test

## 役割・行動方針

test
"""


def _make_handler(tmp_path: Path) -> ToolHandler:
    """Build a minimal ToolHandler with mocked dependencies."""
    anima_dir = tmp_path / "animas" / "boss"
    anima_dir.mkdir(parents=True)
    (anima_dir / "permissions.md").write_text("", encoding="utf-8")

    memory = MagicMock()
    memory.read_permissions.return_value = ""
    return ToolHandler(anima_dir=anima_dir, memory=memory, messenger=MagicMock())


def _response(status_code: int, payload: dict[str, object]) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = json.dumps(payload)
    return response


class TestHandleCreateAnima:
    def test_successful_creation_always_uses_root_api(self, tmp_path):
        handler = _make_handler(tmp_path)
        sheet = tmp_path / "sheet.md"
        sheet.write_text(_SHEET_CONTENT, encoding="utf-8")
        response = _response(200, {"status": "ok", "anima_dir": str(tmp_path / "animas" / "hinata")})

        with patch("core.host_api.host_api.post", return_value=response) as mock_post:
            result = handler.handle("create_anima", {"character_sheet_path": str(sheet), "supervisor": "boss"})

        assert "hinata" in result
        assert "created successfully" in result
        mock_post.assert_called_once()
        (path,) = mock_post.call_args.args
        assert path == "/api/internal/anima/create"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["character_sheet_content"] == _SHEET_CONTENT
        assert payload["calling_anima"] == "boss"
        assert payload["supervisor"] == "boss"

    def test_file_not_found(self, tmp_path):
        handler = _make_handler(tmp_path)
        result = handler.handle(
            "create_anima",
            {"character_sheet_path": str(tmp_path / "nonexistent.md")},
        )
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "FileNotFound"

    def test_missing_source(self, tmp_path):
        handler = _make_handler(tmp_path)
        parsed = json.loads(handler.handle("create_anima", {}))
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "MissingParameter"

    def test_duplicate_anima(self, tmp_path):
        handler = _make_handler(tmp_path)
        response = _response(409, {"detail": "Anima 'hinata' already exists"})

        with patch("core.host_api.host_api.post", return_value=response):
            result = handler.handle("create_anima", {"character_sheet_content": _SHEET_CONTENT, "name": "hinata"})

        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "AnimaExists"

    def test_invalid_character_sheet(self, tmp_path):
        handler = _make_handler(tmp_path)
        response = _response(422, {"detail": "Missing required sections: 基本情報"})

        with patch("core.host_api.host_api.post", return_value=response):
            result = handler.handle("create_anima", {"character_sheet_content": "bad"})

        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "InvalidCharacterSheet"

    def test_unreachable_root_returns_error_without_local_write(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch("core.host_api.host_api.post", side_effect=httpx.ConnectError("connection refused")):
            result = handler.handle(
                "create_anima",
                {"character_sheet_content": _SHEET_CONTENT, "name": "hinata"},
            )

        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert "root API unreachable" in parsed["message"]
        assert not (tmp_path / "animas" / "hinata").exists()
