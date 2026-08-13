from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.tools.google_sheets import (
    GoogleSheetsClient,
    _credentials_dir,
    get_tool_schemas,
)


def test_credentials_dir_prefers_running_animas_company(tmp_path: Path, monkeypatch) -> None:
    anima_dir = tmp_path / "animas" / "sakura"
    anima_dir.mkdir(parents=True)
    (anima_dir / "status.json").write_text(json.dumps({"company": "fs"}), encoding="utf-8")
    credentials_dir = tmp_path / "companies" / "fs" / "credentials" / "fs" / "google_sheets"
    credentials_dir.mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))

    assert _credentials_dir() == credentials_dir


def test_get_tool_schemas_returns_four_tools() -> None:
    schemas = get_tool_schemas()
    assert len(schemas) == 4
    names = {s["name"] for s in schemas}
    # list_tabs / read_values / write_values / append_values
    assert names == {
        "google_sheets_tabs",
        "google_sheets_read",
        "google_sheets_write_values",
        "google_sheets_append_values",
    }
    write_schema = next(s for s in schemas if s["name"] == "google_sheets_write_values")
    assert "上書きに注意" in write_schema["description"]
    assert "read_values" in write_schema["description"]


def _mock_values_service(execute_return=None, execute_side_effect=None) -> MagicMock:
    """Build a nested MagicMock for service.spreadsheets().values().*."""
    values = MagicMock()
    if execute_side_effect is not None:
        values.update.return_value.execute.side_effect = execute_side_effect
        values.append.return_value.execute.side_effect = execute_side_effect
    else:
        values.update.return_value.execute.return_value = execute_return or {}
        values.append.return_value.execute.return_value = execute_return or {}
    service = MagicMock()
    service.spreadsheets.return_value.values.return_value = values
    return service, values


def test_write_values_success() -> None:
    client = GoogleSheetsClient()
    service, values = _mock_values_service(
        execute_return={"updatedRange": "Sheet1!A1:B2", "updatedCells": 4},
    )
    with patch.object(client, "_build_service", return_value=service):
        result = client.write_values(
            "spreadsheet123",
            "Sheet1!A1:B2",
            [["a", "b"], ["c", "d"]],
        )
    assert result == {"updated_range": "Sheet1!A1:B2", "updated_cells": 4}
    values.update.assert_called_once_with(
        spreadsheetId="spreadsheet123",
        range="Sheet1!A1:B2",
        valueInputOption="USER_ENTERED",
        body={"values": [["a", "b"], ["c", "d"]]},
    )


def test_write_values_api_error() -> None:
    client = GoogleSheetsClient()
    service, _values = _mock_values_service(
        execute_side_effect=RuntimeError("Sheets API 403: The caller does not have permission"),
    )
    with patch.object(client, "_build_service", return_value=service):
        with pytest.raises(RuntimeError, match="403"):
            client.write_values("spreadsheet123", "Sheet1!A1", [["x"]])


def test_append_values_success() -> None:
    client = GoogleSheetsClient()
    service, values = _mock_values_service(
        execute_return={
            "updates": {
                "updatedRange": "Sheet1!A5:B5",
                "updatedCells": 2,
            },
        },
    )
    with patch.object(client, "_build_service", return_value=service):
        result = client.append_values(
            "https://docs.google.com/spreadsheets/d/abcXYZ123/edit",
            "Sheet1!A:B",
            [["new", "row"]],
        )
    assert result == {"updated_range": "Sheet1!A5:B5", "updated_cells": 2}
    values.append.assert_called_once_with(
        spreadsheetId="abcXYZ123",
        range="Sheet1!A:B",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [["new", "row"]]},
    )


def test_append_values_api_error() -> None:
    client = GoogleSheetsClient()
    service, _values = _mock_values_service(
        execute_side_effect=RuntimeError("Sheets API 400: Unable to parse range"),
    )
    with patch.object(client, "_build_service", return_value=service):
        with pytest.raises(RuntimeError, match="Unable to parse range"):
            client.append_values("spreadsheet123", "Bad!Range", [["x"]])
