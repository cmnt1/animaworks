# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Read-only MySQL query tools for the enclave runtime.

``enclave_sql_query`` runs a validated read-only SELECT, optionally decrypts
configured Laravel-encrypted columns, and stores the complete result inside
the enclave before returning bounded rows. ``enclave_sql_schema`` reads table
and column metadata. Connections use the read-only sources declared in
``enclave.sql_sources``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from core.enclave.raw_store import try_save_raw
from core.i18n import t
from core.integrations._base import dispatch_by_table

logger = logging.getLogger(__name__)

_ALLOWED_START_KEYWORDS = ("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN")
_DISALLOWED_TOKENS = (
    "INTO OUTFILE",
    "INTO DUMPFILE",
    "INTO @",
    "FOR UPDATE",
    "LOCK IN SHARE MODE",
    "FOR SHARE",
    "SLEEP(",
    "BENCHMARK(",
    "GET_LOCK(",
)


class _EnclaveDisabledError(ValueError):
    """Raised when an SQL tool is called outside an enabled enclave."""


class _SourceNotConfiguredError(ValueError):
    """Raised when a source name is absent from enclave configuration."""


class _ValidationError(ValueError):
    """Raised when an SQL statement fails the read-only validity checks."""


def _source_context(source_name: str) -> tuple[Any, Any]:
    """Load the enabled enclave and return ``(config, source_config)``."""
    from core.config import load_config

    config = load_config()
    if config.enclave.enabled is not True:
        raise _EnclaveDisabledError
    source = config.enclave.sql_sources.get(source_name)
    if source is None:
        raise _SourceNotConfiguredError
    return config, source


def _strip_comments(sql: str) -> str:
    """Remove block (/* */), line (--), and hash (#) comments."""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"#[^\n]*", " ", sql)
    return sql


def _validate_sql(sql: str) -> str | None:
    """Return an error message for invalid SQL, or ``None`` when valid."""
    cleaned = _strip_comments(sql)
    if not cleaned.strip():
        return t("enclave.sql.sql_required")
    if ";" in cleaned.strip().rstrip(";"):
        return t("enclave.sql.multiple_statements")
    normalized = re.sub(r"\s+", " ", cleaned).strip()
    upper = normalized.upper()
    first_keyword = upper.split(" ", 1)[0] if " " in upper else upper
    if first_keyword not in _ALLOWED_START_KEYWORDS:
        return t("enclave.sql.sql_not_allowed")
    for token in _DISALLOWED_TOKENS:
        if token in upper:
            return t("enclave.sql.sql_not_allowed")
    return None


def _connect(source: Any, host: str, port: int, password: str) -> Any:
    """Open a read-only PyMySQL connection for *source*."""
    import pymysql

    kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        "database": source.database,
        "user": source.user,
        "password": password,
        "read_timeout": source.timeout_s,
        "connect_timeout": source.timeout_s,
        "charset": "utf8mb4",
        "autocommit": True,
        # One statement only: PyMySQL does not enable multi-statements for init_command.
        "init_command": (
            f"SET SESSION transaction_read_only = 1, SESSION max_execution_time = {source.timeout_s * 1000}"
        ),
    }
    if source.ssl:
        # An empty dict would leave TLS off in PyMySQL. Without a CA the channel is
        # still encrypted (the server may REQUIRE SSL) but the certificate is not verified.
        ssl_kwargs: dict[str, Any] = {"ca": source.ssl_ca} if source.ssl_ca else {"check_hostname": False}
        kwargs["ssl"] = ssl_kwargs
        kwargs["ssl_verify_identity"] = source.ssl_verify_identity
    return pymysql.connect(**kwargs)


def _run_query(source: Any, host: str, port: int, password: str, sql: str) -> tuple[list[str], list[tuple], bool]:
    connection = _connect(source, host, port, password)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            if cursor.description is None:
                return [], [], False
            columns = [description[0] for description in cursor.description]
            batch = cursor.fetchmany(source.max_rows + 1)
            truncated = len(batch) > source.max_rows
            rows = batch[: source.max_rows]
            return columns, rows, truncated
    finally:
        connection.close()


def _format_cell(value: Any, max_chars: int) -> tuple[str, bool]:
    if value is None:
        return "", False
    if isinstance(value, bytes):
        return f"<binary {len(value)} bytes>", False
    text = str(value)
    if len(text) > max_chars:
        return text[:max_chars], True
    return text, False


def _cell_to_string(value: Any, max_chars: int) -> str:
    return _format_cell(value, max_chars)[0]


def _decrypt_rows(
    columns: list[str],
    rows: list[tuple],
    patterns: list[str],
    keys: list[bytes],
) -> tuple[list[tuple], int, int]:
    from core.enclave.laravel_crypt import decrypt_string

    decrypt_indices: set[int] = set()
    for index, column in enumerate(columns):
        for pattern in patterns:
            try:
                if re.search(pattern, column):
                    decrypt_indices.add(index)
                    break
            except re.error:
                logger.debug("Skipping invalid decrypt_columns pattern")

    updated_rows: list[tuple] = []
    decrypted_cells = 0
    undecryptable_cells = 0
    for row in rows:
        updated = list(row)
        for index in decrypt_indices:
            if index >= len(updated) or not isinstance(updated[index], str):
                continue
            plaintext = decrypt_string(updated[index], keys)
            if plaintext is None:
                undecryptable_cells += 1
            else:
                updated[index] = plaintext
                decrypted_cells += 1
        updated_rows.append(tuple(updated))
    return updated_rows, decrypted_cells, undecryptable_cells


def _format_result(
    source_name: str,
    columns: list[str],
    rows: list[tuple],
    truncated: bool,
    max_chars: int,
) -> dict[str, Any]:
    formatted_rows: list[list[str]] = []
    cells_truncated = False
    for row in rows:
        formatted_row: list[str] = []
        for cell in row:
            formatted, cell_truncated = _format_cell(cell, max_chars)
            formatted_row.append(formatted)
            cells_truncated = cells_truncated or cell_truncated
        formatted_rows.append(formatted_row)

    result: dict[str, Any] = {
        "source": source_name,
        "columns": columns,
        "rows": formatted_rows,
        "row_count": len(rows),
        "truncated": truncated,
    }
    if cells_truncated:
        result["cells_truncated"] = True
    return result


def _tool_error(exc: Exception, source_name: str) -> str:
    if isinstance(exc, _EnclaveDisabledError):
        return t("enclave.sql.only")
    if isinstance(exc, _SourceNotConfiguredError):
        return t("enclave.sql.source_not_configured", source=source_name)
    if isinstance(exc, _ValidationError):
        return str(exc)
    logger.warning("Could not query enclave sql source %s (%s)", source_name, type(exc).__name__)
    return t("enclave.sql.unavailable")


def _write_endpoint(source_name: str, source: Any) -> tuple[str, int]:
    """Resolve ``(host, port)`` for a source, establishing a tunnel if needed."""
    if source.tunnel is None:
        return source.host, source.port
    from core.enclave.ssm_tunnel import ensure_tunnel

    local_port = ensure_tunnel(source_name, source.tunnel, source.host, source.port)
    return "127.0.0.1", local_port


def enclave_sql_query(source: str, sql: str) -> dict[str, Any] | str:
    """Run a validated read-only query, optionally decrypting configured columns."""
    if not isinstance(source, str) or not source:
        return t("enclave.sql.source_required")
    if not isinstance(sql, str) or not sql.strip():
        return t("enclave.sql.sql_required")

    try:
        validation_error = _validate_sql(sql)
        if validation_error is not None:
            return validation_error

        _, source_config = _source_context(source)
        password = _read_source_password(source_config)
        host, port = _write_endpoint(source, source_config)
        columns, rows, truncated = _run_query(source_config, host, port, password, sql)

        decrypt_configured = bool(source_config.app_key_secret and source_config.decrypt_columns)
        decrypted_cells = 0
        undecryptable_cells = 0
        if decrypt_configured:
            from core.enclave.laravel_crypt import parse_app_keys
            from core.enclave.secrets import read_enclave_secret

            app_keys = parse_app_keys(read_enclave_secret(source_config.app_key_secret))
            rows, decrypted_cells, undecryptable_cells = _decrypt_rows(
                columns,
                rows,
                source_config.decrypt_columns,
                app_keys,
            )

        result = _format_result(source, columns, rows, truncated, source_config.cell_max_chars)
        if decrypt_configured:
            result["decrypted_cells"] = decrypted_cells
            result["undecryptable_cells"] = undecryptable_cells

        raw_path = try_save_raw(
            "enclave_sql_query",
            {"source": source, "sql": sql, "columns": columns, "rows": rows},
        )
        if raw_path is not None:
            result["raw_path"] = str(raw_path)
            result["note"] = t("enclave.sql.raw_note")
        return result
    except Exception as exc:  # noqa: BLE001 - map to a short, secret-free message
        return _tool_error(exc, source)


def enclave_sql_schema(source: str, table: str | None = None) -> dict[str, Any] | str:
    """Return the schema (tables or a table's columns) for a source."""
    if not isinstance(source, str) or not source:
        return t("enclave.sql.source_required")

    try:
        config, source_config = _source_context(source)
        password = _read_source_password(source_config)
        host, port = _write_endpoint(source, source_config)
        rows = _run_schema(source_config, host, port, password, table)
    except Exception as exc:  # noqa: BLE001 - map to a short, secret-free message
        return _tool_error(exc, source)

    if table is not None:
        columns = [{"name": row[0], "type": row[1]} for row in rows]
        return {"source": source, "table": table, "columns": columns}
    return {"source": source, "tables": [row[0] for row in rows]}


def _read_source_password(source_config: Any) -> str:
    from core.enclave.secrets import read_enclave_secret

    return read_enclave_secret(source_config.password_secret)


def _run_schema(
    source: Any,
    host: str,
    port: int,
    password: str,
    table: str | None,
) -> list[tuple]:
    connection = _connect(source, host, port, password)
    try:
        with connection.cursor() as cursor:
            if table is None:
                cursor.execute(
                    "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME",
                    (source.database,),
                )
            else:
                cursor.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                    "ORDER BY ORDINAL_POSITION",
                    (source.database, table),
                )
            return list(cursor.fetchall())
    finally:
        connection.close()


def _dispatch_query(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_sql_query(source=args.get("source", ""), sql=args.get("sql", ""))


def _dispatch_schema(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_sql_schema(source=args.get("source", ""), table=args.get("table"))


_DISPATCH_HANDLERS = {
    "enclave_sql_query": _dispatch_query,
    "enclave_sql_schema": _dispatch_schema,
}


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch an enclave SQL tool call by its schema name."""
    return dispatch_by_table(_DISPATCH_HANDLERS, name, args)


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return tool schemas for querying and inspecting enclave SQL sources."""
    return [
        {
            "name": "enclave_sql_query",
            "description": t("enclave.sql.schema_query"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": t("enclave.sql.schema_source")},
                    "sql": {"type": "string", "description": t("enclave.sql.schema_sql")},
                },
                "required": ["source", "sql"],
            },
        },
        {
            "name": "enclave_sql_schema",
            "description": t("enclave.sql.schema_schema"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": t("enclave.sql.schema_source")},
                    "table": {"type": "string", "description": t("enclave.sql.schema_table")},
                },
                "required": ["source"],
            },
        },
    ]


__all__ = ["dispatch", "enclave_sql_query", "enclave_sql_schema", "get_tool_schemas"]
