# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for enclave read-only SQL tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from core.config import invalidate_cache
from core.integrations import enclave_sql
from core.tooling.policy.registry import TOOL_MODULES, get_tool_modules
from tests.helpers.filesystem import DEFAULT_TEST_CONFIG

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, *, columns: list[str] | None = None, rows: list = None, error: Exception | None = None) -> None:
        self._cols = columns
        self._rows = list(rows or [])
        self._error = error
        self.executed: str | None = None
        self.description = None

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def execute(self, sql: str, args: tuple = ()) -> int:  # noqa: ARG002
        self.executed = sql
        if self._error is not None:
            raise self._error
        self.description = [(c, None) for c in (self._cols or [])] if self._cols is not None else None
        return 0

    def fetchmany(self, size: int) -> list:
        out, self._rows = self._rows[:size], self._rows[size:]
        return out

    def fetchall(self) -> list:
        out, self._rows = self._rows, []
        return out


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.closed = False
        self.connect_kwargs: dict[str, Any] = {}

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def close(self) -> None:
        self.closed = True


class _FakePyMySQL:
    def __init__(self) -> None:
        self.connection: _FakeConnection | None = None

    def connect(self, **kwargs: Any) -> _FakeConnection:
        if self.connection is None:
            self.connection = _FakeConnection(_FakeCursor())
        self.connection.connect_kwargs = kwargs
        return self.connection


def _write_config(
    data_dir: Path, *, enabled: bool = True, sources: dict | None = None, secrets_dir: str | None = None
) -> None:
    config: dict = dict(DEFAULT_TEST_CONFIG)
    config["enclave"] = {"enabled": enabled, "sql_sources": sources or {}, "secrets_dir": secrets_dir}
    (data_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    invalidate_cache()


def _write_secret(secrets_dir: Path, name: str, value: str) -> None:
    secrets_dir.mkdir(parents=True, exist_ok=True)
    (secrets_dir / name).write_text(value, encoding="utf-8")


def _install_fake_pymysql(monkeypatch: pytest.MonkeyPatch, fake: _FakePyMySQL) -> None:
    monkeypatch.setitem(sys.modules, "pymysql", fake)


def _direct_source(*, max_rows: int = 200, exempt: list[str] | None = None) -> dict:
    return {
        "driver": "mysql",
        "host": "db.example.internal",
        "port": 3306,
        "database": "example_db",
        "user": "enclave_reader",
        "password_secret": "db-password",
        "ssl": True,
        "max_rows": max_rows,
        "timeout_s": 30,
        "cell_max_chars": 2000,
        "ledger_exempt_columns": exempt or [],
    }


# ---------------------------------------------------------------------------
# SQL validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select * from t where x = 1",
        "WITH cte AS (SELECT 1) SELECT * FROM cte",
        "SHOW TABLES",
        "DESCRIBE t",
        "DESC t",
        "EXPLAIN SELECT 1",
        "SELECT * FROM t -- comment",
        "SELECT * FROM t /* block */",
        "SELECT 1;",
    ],
)
def test_valid_sql_passes(sql: str) -> None:
    assert enclave_sql._validate_sql(sql) is None


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "UPDATE t SET x = 1",
        "INSERT INTO t VALUES (1)",
        "DELETE FROM t",
        "DROP TABLE t",
        "SELECT * FROM t INTO OUTFILE '/tmp/x'",
        "SELECT * FROM t INTO DUMPFILE '/tmp/x'",
        "SELECT * FROM t INTO @var",
        "SELECT * FROM t FOR UPDATE",
        "SELECT * FROM t LOCK IN SHARE MODE",
        "SELECT * FROM t FOR SHARE",
        "SELECT SLEEP(5)",
        "SELECT BENCHMARK(1000000, SHA1('x'))",
        "SELECT GET_LOCK('lock', 10)",
        "SELECT 1; SELECT 2",
        "SELECT 1 WHERE a = 'FOR UPDATE'; SELECT 2",
    ],
)
def test_invalid_sql_rejected(sql: str) -> None:
    assert enclave_sql._validate_sql(sql) is not None


# ---------------------------------------------------------------------------
# Query tool: formatting, truncation, ledger registration
# ---------------------------------------------------------------------------


def test_query_returns_formatted_result_and_registers_ledger(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePyMySQL()
    _install_fake_pymysql(monkeypatch, fake)
    secrets_dir = data_dir / "secretstore"
    _write_secret(secrets_dir, "db-password", "pw")
    _write_config(
        data_dir,
        sources={"main": _direct_source(exempt=[".*_id", "active"])},
        secrets_dir=str(secrets_dir),
    )
    fake.connection = _FakeConnection(
        _FakeCursor(
            columns=["name", "amount", "created", "active", "customer_id"],
            rows=[("青葉 葵", 100, "2024-01-02", True, "C000001")],
        )
    )

    result = enclave_sql.enclave_sql_query("main", "SELECT name, amount, created, active, customer_id FROM customers")

    assert isinstance(result, dict)
    assert result["source"] == "main"
    assert result["columns"] == ["name", "amount", "created", "active", "customer_id"]
    assert result["rows"] == [["青葉 葵", "100", "2024-01-02", "True", "C000001"]]
    assert result["row_count"] == 1
    assert result["truncated"] is False

    # Non-trivial string cells (excluding exempt/numeric/datetime/boolean) are ledgered.
    ledger_path = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert {item["value"] for item in ledger} == {"青葉 葵"}
    assert {item["source"] for item in ledger} == {"sql:main"}


def test_query_truncates_and_marks_truncated(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePyMySQL()
    _install_fake_pymysql(monkeypatch, fake)
    secrets_dir = data_dir / "secretstore"
    _write_secret(secrets_dir, "db-password", "pw")
    _write_config(data_dir, sources={"main": _direct_source(max_rows=3)}, secrets_dir=str(secrets_dir))
    fake.connection = _FakeConnection(
        _FakeCursor(
            columns=["name"],
            rows=[(f"row-{i}",) for i in range(5)],
        )
    )

    result = enclave_sql.enclave_sql_query("main", "SELECT name FROM t")

    assert result["row_count"] == 3
    assert result["truncated"] is True


def test_query_truncates_long_cells(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePyMySQL()
    _install_fake_pymysql(monkeypatch, fake)
    secrets_dir = data_dir / "secretstore"
    _write_secret(secrets_dir, "db-password", "pw")
    source = _direct_source()
    source["cell_max_chars"] = 5
    _write_config(data_dir, sources={"main": source}, secrets_dir=str(secrets_dir))
    fake.connection = _FakeConnection(_FakeCursor(columns=["body"], rows=[("a" * 20,)]))

    result = enclave_sql.enclave_sql_query("main", "SELECT body FROM t")

    assert result["rows"] == [["aaaaa"]]


def test_query_renders_binary_cells(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePyMySQL()
    _install_fake_pymysql(monkeypatch, fake)
    secrets_dir = data_dir / "secretstore"
    _write_secret(secrets_dir, "db-password", "pw")
    _write_config(data_dir, sources={"main": _direct_source()}, secrets_dir=str(secrets_dir))
    fake.connection = _FakeConnection(_FakeCursor(columns=["blob"], rows=[(b"\x00\x01\x02",)]))

    result = enclave_sql.enclave_sql_query("main", "SELECT blob FROM t")

    assert result["rows"] == [["<binary 3 bytes>"]]


def test_query_uses_ssl_and_read_only_init_command(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePyMySQL()
    _install_fake_pymysql(monkeypatch, fake)
    secrets_dir = data_dir / "secretstore"
    _write_secret(secrets_dir, "db-password", "pw")
    _write_config(data_dir, sources={"main": _direct_source()}, secrets_dir=str(secrets_dir))
    fake.connection = _FakeConnection(_FakeCursor(columns=["a"], rows=[(1,)]))

    enclave_sql.enclave_sql_query("main", "SELECT a FROM t")

    kwargs = fake.connection.connect_kwargs
    assert kwargs["ssl"] == {"check_hostname": False}
    assert kwargs["ssl_verify_identity"] is False
    assert "transaction_read_only = 1" in kwargs["init_command"]
    assert "max_execution_time = 30000" in kwargs["init_command"]
    assert ";" not in kwargs["init_command"]
    assert kwargs["user"] == "enclave_reader"
    assert kwargs["password"] == "pw"


def test_query_disabled_enclave(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_pymysql(monkeypatch, _FakePyMySQL())
    _write_config(data_dir, enabled=False)
    result = enclave_sql.enclave_sql_query("main", "SELECT 1")
    assert isinstance(result, str)
    assert "enclave 内でだけ" in result


def test_schema_returns_tables(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakePyMySQL()
    _install_fake_pymysql(monkeypatch, fake)
    secrets_dir = data_dir / "secretstore"
    _write_secret(secrets_dir, "db-password", "pw")
    _write_config(data_dir, sources={"main": _direct_source()}, secrets_dir=str(secrets_dir))
    fake.connection = _FakeConnection(_FakeCursor(columns=["TABLE_NAME"], rows=[("customers",), ("tickets",)]))

    result = enclave_sql.enclave_sql_schema("main")

    assert isinstance(result, dict)
    assert result["tables"] == ["customers", "tickets"]


# ---------------------------------------------------------------------------
# Registry: only registered in enclave mode
# ---------------------------------------------------------------------------


def test_sql_tool_registered_only_in_enclave_mode(data_dir: Path) -> None:
    from core.config.models import PermissionsConfig
    from core.tooling.permissions import get_permitted_tools
    from core.tooling.policy.schemas.loader import load_external_schemas

    _write_config(data_dir, enabled=False)
    assert "enclave_sql" not in TOOL_MODULES
    assert "enclave_sql" not in get_tool_modules()
    assert "enclave_sql" not in get_permitted_tools(PermissionsConfig())
    assert load_external_schemas(["enclave_sql"]) == []

    _write_config(data_dir, enabled=True)
    assert get_tool_modules()["enclave_sql"] == "core.integrations.enclave_sql"
    assert "enclave_sql" in get_permitted_tools(PermissionsConfig())
    schema_names = {schema["name"] for schema in load_external_schemas(["enclave_sql"])}
    assert schema_names == {"enclave_sql_query", "enclave_sql_schema"}
