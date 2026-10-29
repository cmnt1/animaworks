# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""The enclave-only tools are reachable through ``animaworks-tool``."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from core.integrations import enclave_sql


def test_schema_cli_maps_options_to_dispatch(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.object(enclave_sql, "dispatch", return_value={"row_count": 1}) as dispatch:
        enclave_sql.cli_main(["enclave_sql_query", "--source", "prod", "--sql", "SELECT 1"])
    dispatch.assert_called_once_with("enclave_sql_query", {"source": "prod", "sql": "SELECT 1"})
    assert json.loads(capsys.readouterr().out) == {"row_count": 1}


def test_cli_dispatch_lists_enclave_tools_only_in_enclave(capsys: pytest.CaptureFixture[str]) -> None:
    from cli import tool_dispatch

    with (
        patch.object(tool_dispatch, "get_tool_modules", return_value={"enclave_sql": "core.integrations.enclave_sql"}),
        patch("sys.argv", ["animaworks-tool", "--help"]),
        pytest.raises(SystemExit),
    ):
        tool_dispatch.cli_dispatch()
    assert "enclave_sql" in capsys.readouterr().out
