# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Read-only AWS data tools for the enclave runtime.

Credentials are loaded exclusively from the configured enclave secret. AWS
responses are bounded before they are returned, and only explicitly
configured log groups, PI resources, RDS instances, and S3 buckets are
accessible.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.i18n import t
from core.integrations._base import dispatch_by_table

logger = logging.getLogger(__name__)

_QUERY_TIMEOUT_S = 60.0
_QUERY_POLL_INTERVAL_S = 0.5
_MAX_LOG_LIMIT = 10_000
_MAX_PI_LIMIT = 25  # RDS Performance Insights MaxResults API maximum.
_MAX_S3_LIST_LIMIT = 1_000
_RELATIVE_TIME_RE = re.compile(r"^-(\d+)([smhd])$", re.IGNORECASE)
_SQL_START_RE = re.compile(
    r"^\s*(?:SELECT|WITH|INSERT|UPDATE|DELETE|MERGE|CALL|REPLACE|CREATE|ALTER|DROP|SHOW|DESCRIBE|EXPLAIN)\b",
    re.IGNORECASE,
)


class _AwsToolError(ValueError):
    """Base for safe, user-displayable AWS tool errors."""


class _EnclaveDisabledError(_AwsToolError):
    pass


class _SourceRequiredError(_AwsToolError):
    pass


class _SourceNotConfiguredError(_AwsToolError):
    pass


class _TargetNotAllowedError(_AwsToolError):
    pass


class _InvalidInputError(_AwsToolError):
    pass


class _QueryTimeoutError(_AwsToolError):
    pass


class _InvalidAwsSecretError(_AwsToolError):
    pass


class _AwsDependencyError(_AwsToolError):
    pass


def _source_context(source_name: str) -> tuple[Any, Any]:
    """Load an enabled enclave AWS source."""
    if not isinstance(source_name, str):
        raise _InvalidInputError
    if not source_name:
        raise _SourceRequiredError

    from core.config import load_config

    config = load_config()
    if config.enclave.enabled is not True:
        raise _EnclaveDisabledError
    source = config.enclave.aws_sources.get(source_name)
    if source is None:
        raise _SourceNotConfiguredError
    return config, source


def _create_session(source_config: Any) -> Any:
    """Build a boto3 session using only credentials from the enclave secret."""
    from core.enclave.secrets import read_enclave_secret

    raw = read_enclave_secret(source_config.aws_secret)
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise _InvalidAwsSecretError from exc
    if not isinstance(payload, dict):
        raise _InvalidAwsSecretError

    access_key = payload.get("aws_access_key_id")
    secret_key = payload.get("aws_secret_access_key")
    if not isinstance(access_key, str) or not access_key or not isinstance(secret_key, str) or not secret_key:
        raise _InvalidAwsSecretError

    try:
        import boto3
    except ImportError as exc:
        raise _AwsDependencyError from exc

    return boto3.Session(
        region_name=source_config.region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def _client(source_config: Any, service: str) -> Any:
    return _create_session(source_config).client(service, region_name=source_config.region)


def _require_text(value: Any, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise _InvalidInputError
    result = value.strip()
    if not allow_empty and not result:
        raise _InvalidInputError
    return result


def _require_raw_text(value: Any, *, allow_empty: bool = False) -> str:
    """Validate a text field without changing significant leading/trailing spaces."""
    if not isinstance(value, str) or (not allow_empty and not value):
        raise _InvalidInputError
    return value


def _require_limit(value: Any, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise _InvalidInputError
    return value


def _parse_time(value: str) -> int:
    """Parse ``now``, an ISO8601 timestamp or a relative duration such as ``-1h``."""
    text = _require_text(value)
    if text.casefold() == "now":
        return int(datetime.now(UTC).timestamp())
    relative = _RELATIVE_TIME_RE.fullmatch(text)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()
        duration = {
            "s": timedelta(seconds=amount),
            "m": timedelta(minutes=amount),
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
        }[unit]
        return int((datetime.now(UTC) - duration).timestamp())

    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text)
    except ValueError as exc:
        raise _InvalidInputError from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def _bounded_text(text: str, max_bytes: int) -> tuple[str, bool]:
    """Limit UTF-8 text to ``max_bytes`` without returning a partial codepoint."""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


def _text_result(
    source_name: str,
    source_config: Any,
    text: str,
    *,
    extra: dict[str, Any] | None = None,
    truncated: bool = False,
) -> dict[str, Any]:
    bounded, text_truncated = _bounded_text(text, source_config.max_bytes)
    result: dict[str, Any] = {"source": source_name}
    if extra:
        result.update(extra)
    result["text"] = bounded
    result["truncated"] = truncated or text_truncated
    return result


def _ledger_exempt_keys(source_config: Any) -> set[str]:
    return {str(key).casefold() for key in source_config.ledger_exempt_keys}


def _parse_json_string(value: str) -> Any | None:
    stripped = value.lstrip()
    if not stripped.startswith(("{", "[")):
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _collect_json_values(value: Any, exempt_keys: set[str], out: list[str]) -> None:
    """Collect structured JSON string values, never free-form exempt fields."""
    if isinstance(value, dict):
        for key, child in value.items():
            exempt = str(key).casefold() in exempt_keys
            if isinstance(child, str):
                nested = _parse_json_string(child)
                if nested is not None:
                    _collect_json_values(nested, exempt_keys, out)
                elif not exempt and child:
                    out.append(child)
            elif not exempt and isinstance(child, (dict, list)):
                _collect_json_values(child, exempt_keys, out)
    elif isinstance(value, list):
        for child in value:
            _collect_json_values(child, exempt_keys, out)
    elif isinstance(value, str) and value:
        out.append(value)


def _json_line_values(text: str, source_config: Any) -> list[str]:
    """Extract ledger-safe values from JSON/JSONL object records only."""
    values: list[str] = []
    exempt_keys = _ledger_exempt_keys(source_config)
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(record, (dict, list)):
            _collect_json_values(record, exempt_keys, values)
    return values


def _record_values(source_name: str, source_config: Any, values: list[str]) -> None:
    if not source_config.ledger_register or not values:
        return
    from core.enclave.egress.ledger import record_known_values
    from core.paths import get_data_dir

    record_known_values(get_data_dir(), values, source=f"aws:{source_name}")


def _record_json_lines(source_name: str, source_config: Any, text: str) -> None:
    _record_values(source_name, source_config, _json_line_values(text, source_config))


def _json_text(value: Any) -> str:
    def _default(item: Any) -> str:
        if isinstance(item, datetime):
            return item.isoformat()
        return str(item)

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_default)


def _logs_group_allowed(source_config: Any, log_group: str) -> bool:
    for pattern in source_config.log_groups:
        if pattern.endswith("*"):
            if log_group.startswith(pattern[:-1]):
                return True
        elif log_group == pattern:
            return True
    return False


def _uses_logs_source_command(query: str) -> bool:
    without_comments = re.sub(r"(?m)^\s*#.*$", "", query)
    return bool(re.match(r"^\s*SOURCE\b", without_comments, re.IGNORECASE))


def _query_interval(start: str, end: str) -> tuple[int, int]:
    start_epoch = _parse_time(start)
    end_epoch = _parse_time(end)
    if start_epoch >= end_epoch:
        raise _InvalidInputError
    return start_epoch, end_epoch


def _log_query_rows(results: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in results:
        if not isinstance(row, list):
            continue
        record: dict[str, Any] = {}
        for item in row:
            if isinstance(item, dict) and isinstance(item.get("field"), str):
                record[item["field"]] = item.get("value", "")
        records.append(record)
    return records


def enclave_logs_query(
    source: str,
    log_group: str,
    query: str,
    start: str,
    end: str,
    limit: int = 100,
) -> dict[str, Any] | str:
    """Run a CloudWatch Logs Insights query against an allowed log group."""
    try:
        log_group = _require_text(log_group)
        query = _require_text(query)
        if _uses_logs_source_command(query):
            raise _TargetNotAllowedError
        limit = _require_limit(limit, minimum=1, maximum=_MAX_LOG_LIMIT)
        start_epoch, end_epoch = _query_interval(start, end)
        _, source_config = _source_context(source)
        if not _logs_group_allowed(source_config, log_group):
            raise _TargetNotAllowedError

        logs = _client(source_config, "logs")
        response = logs.start_query(
            logGroupName=log_group,
            startTime=start_epoch,
            endTime=end_epoch,
            queryString=query,
            limit=limit,
        )
        query_id = response.get("queryId") if isinstance(response, dict) else None
        if not isinstance(query_id, str) or not query_id:
            raise RuntimeError("missing query id")

        deadline = time.monotonic() + _QUERY_TIMEOUT_S
        while True:
            result = logs.get_query_results(queryId=query_id)
            if time.monotonic() >= deadline:
                raise _QueryTimeoutError
            status = result.get("status") if isinstance(result, dict) else None
            if status == "Complete":
                break
            if status in {"Failed", "Cancelled", "Timeout", "Unknown"}:
                raise RuntimeError("Logs Insights query did not complete")
            if status not in {"Scheduled", "Running"}:
                raise RuntimeError("Logs Insights returned an unknown status")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _QueryTimeoutError
            time.sleep(min(_QUERY_POLL_INTERVAL_S, remaining))

        rows = _log_query_rows(result.get("results", []))
        text = "\n".join(_json_text(row) for row in rows)
        values: list[str] = []
        exempt_keys = _ledger_exempt_keys(source_config)
        for row in rows:
            _collect_json_values(row, exempt_keys, values)
        _record_values(source, source_config, values)
        return _text_result(
            source,
            source_config,
            text,
            extra={"query_id": query_id, "status": "Complete"},
            truncated=len(rows) >= limit,
        )
    except Exception as exc:  # noqa: BLE001 - do not expose AWS responses or credentials
        return _tool_error(exc, source)


def enclave_logs_filter(
    source: str,
    log_group: str,
    filter_pattern: str,
    start: str,
    end: str,
    limit: int = 100,
) -> dict[str, Any] | str:
    """Fetch matching CloudWatch log events from an allowed log group."""
    try:
        log_group = _require_text(log_group)
        filter_pattern = _require_text(filter_pattern, allow_empty=True)
        limit = _require_limit(limit, minimum=1, maximum=_MAX_LOG_LIMIT)
        start_epoch, end_epoch = _query_interval(start, end)
        _, source_config = _source_context(source)
        if not _logs_group_allowed(source_config, log_group):
            raise _TargetNotAllowedError

        request = {
            "logGroupName": log_group,
            "startTime": start_epoch * 1000,
            "endTime": end_epoch * 1000,
            "limit": limit,
        }
        if filter_pattern:
            request["filterPattern"] = filter_pattern
        response = _client(source_config, "logs").filter_log_events(**request)
        events = response.get("events", []) if isinstance(response, dict) else []
        safe_events = [event for event in events if isinstance(event, dict)]
        text = "\n".join(_json_text(event) for event in safe_events)
        _record_json_lines(source, source_config, text)

        next_token = response.get("nextToken") if isinstance(response, dict) else None
        return _text_result(
            source,
            source_config,
            text,
            extra={"next_page_available": bool(next_token)},
            truncated=bool(next_token),
        )
    except Exception as exc:  # noqa: BLE001 - do not expose AWS responses or credentials
        return _tool_error(exc, source)


def enclave_pi_top_sql(
    source: str,
    start: str,
    end: str,
    metric: str = "db.load.avg",
    group_by: str = "db.sql",
    limit: int = 10,
) -> dict[str, Any] | str:
    """Return the most significant SQL dimensions from RDS Performance Insights."""
    try:
        start_epoch, end_epoch = _query_interval(start, end)
        metric = _require_text(metric)
        group_by = _require_text(group_by)
        limit = _require_limit(limit, minimum=1, maximum=_MAX_PI_LIMIT)
        _, source_config = _source_context(source)
        if not source_config.pi_resource_id:
            raise _TargetNotAllowedError

        response = _client(source_config, "pi").describe_dimension_keys(
            ServiceType="RDS",
            Identifier=source_config.pi_resource_id,
            StartTime=datetime.fromtimestamp(start_epoch, UTC),
            EndTime=datetime.fromtimestamp(end_epoch, UTC),
            Metric=metric,
            GroupBy={"Group": group_by},
            MaxResults=limit,
        )
        text = _json_text(response)
        _record_sql_values(source, source_config, response)
        next_token = response.get("NextToken") if isinstance(response, dict) else None
        return _text_result(
            source,
            source_config,
            text,
            extra={"next_page_available": bool(next_token)},
            truncated=bool(next_token),
        )
    except Exception as exc:  # noqa: BLE001 - do not expose AWS responses or credentials
        return _tool_error(exc, source)


def _looks_like_sql(value: str) -> bool:
    candidate = value.lstrip().lstrip("\ufeff")
    while True:
        if candidate.startswith("/*"):
            close = candidate.find("*/", 2)
            if close < 0:
                return False
            candidate = candidate[close + 2 :].lstrip()
            continue
        if candidate.startswith(("--", "#")):
            newline = candidate.find("\n")
            if newline < 0:
                return False
            candidate = candidate[newline + 1 :].lstrip()
            continue
        return bool(_SQL_START_RE.match(candidate))


def _iter_sql_texts(value: Any):
    if isinstance(value, str):
        if _looks_like_sql(value):
            yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _iter_sql_texts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_sql_texts(child)


def _sql_string_literals(sql: str) -> list[str]:
    """Extract single-quoted SQL literals while skipping comments/identifiers."""
    literals: list[str] = []
    index = 0
    length = len(sql)
    while index < length:
        if sql.startswith("--", index) or sql[index] == "#":
            newline = sql.find("\n", index)
            index = length if newline < 0 else newline + 1
            continue
        if sql.startswith("/*", index):
            close = sql.find("*/", index + 2)
            index = length if close < 0 else close + 2
            continue
        if sql[index] != "'":
            index += 1
            continue

        index += 1
        literal: list[str] = []
        closed = False
        while index < length:
            char = sql[index]
            if char == "\\" and index + 1 < length:
                literal.append(sql[index + 1])
                index += 2
            elif char == "'":
                if index + 1 < length and sql[index + 1] == "'":
                    literal.append("'")
                    index += 2
                else:
                    index += 1
                    closed = True
                    break
            else:
                literal.append(char)
                index += 1
        if closed:
            value = "".join(literal)
            if value:
                literals.append(value)
    return literals


def _record_sql_values(source_name: str, source_config: Any, response: Any) -> None:
    values = [literal for sql in _iter_sql_texts(response) for literal in _sql_string_literals(sql)]
    _record_values(source_name, source_config, values)


def enclave_pi_sql_detail(source: str, group_identifier: str) -> dict[str, Any] | str:
    """Fetch full SQL dimension details from Performance Insights."""
    try:
        group_identifier = _require_text(group_identifier)
        _, source_config = _source_context(source)
        if not source_config.pi_resource_id:
            raise _TargetNotAllowedError

        response = _client(source_config, "pi").get_dimension_key_details(
            ServiceType="RDS",
            Identifier=source_config.pi_resource_id,
            Group="db.sql",
            GroupIdentifier=group_identifier,
        )
        _record_sql_values(source, source_config, response)
        return _text_result(source, source_config, _json_text(response))
    except Exception as exc:  # noqa: BLE001 - do not expose AWS responses or credentials
        return _tool_error(exc, source)


def _rds_logs_client(source_config: Any) -> Any:
    if not source_config.rds_instance_id:
        raise _TargetNotAllowedError
    return _client(source_config, "rds")


def enclave_rds_logs(
    source: str,
    log_file_name: str | None = None,
    marker: str | None = None,
    lines: int = 500,
) -> dict[str, Any] | str:
    """List RDS log files or fetch a bounded portion of one file."""
    try:
        lines = _require_limit(lines, minimum=1, maximum=_MAX_LOG_LIMIT)
        if marker is not None:
            marker = _require_text(marker)
        if log_file_name is not None:
            log_file_name = _require_text(log_file_name)
        _, source_config = _source_context(source)
        client = _rds_logs_client(source_config)
        identifier = source_config.rds_instance_id
        assert identifier is not None

        if log_file_name is None:
            request: dict[str, Any] = {
                "DBInstanceIdentifier": identifier,
                "MaxRecords": min(max(lines, 20), 100),
            }
            if marker:
                request["Marker"] = marker
            response = client.describe_db_log_files(**request)
            files = response.get("DescribeDBLogFiles", []) if isinstance(response, dict) else []
            records = [record for record in files[:lines] if isinstance(record, dict)]
            text = "\n".join(_json_text(record) for record in records)
            next_marker = response.get("Marker") if isinstance(response, dict) else None
            more_files = len(files) > lines
            return _text_result(
                source,
                source_config,
                text,
                extra={"marker": next_marker, "next_page_available": bool(next_marker)},
                truncated=bool(next_marker) or more_files,
            )

        request = {
            "DBInstanceIdentifier": identifier,
            "LogFileName": log_file_name,
            "NumberOfLines": lines,
        }
        if marker:
            request["Marker"] = marker
        response = client.download_db_log_file_portion(**request)
        text = response.get("LogFileData", "") if isinstance(response, dict) else ""
        if not isinstance(text, str):
            text = ""
        _record_json_lines(source, source_config, text)
        next_marker = response.get("Marker") if isinstance(response, dict) else None
        pending = bool(response.get("AdditionalDataPending")) if isinstance(response, dict) else False
        return _text_result(
            source,
            source_config,
            text,
            extra={"marker": next_marker, "additional_data_pending": pending},
            truncated=pending,
        )
    except Exception as exc:  # noqa: BLE001 - do not expose AWS responses or credentials
        return _tool_error(exc, source)


def _validate_bucket(source_config: Any, bucket: str) -> str:
    bucket = _require_text(bucket)
    if bucket not in source_config.s3_buckets:
        raise _TargetNotAllowedError
    if bucket in {".", ".."} or "/" in bucket or "\\" in bucket or "\x00" in bucket:
        raise _InvalidInputError
    return bucket


def _download_path(data_dir: Path, bucket: str, key: str) -> tuple[Path, str]:
    """Return a contained, opaque local path for an S3 object."""
    root = data_dir.resolve()
    target_dir = data_dir / "enclave" / "downloads" / bucket
    if not target_dir.resolve(strict=False).is_relative_to(root):
        raise _InvalidInputError
    from core.enclave.egress.fs import ensure_dir_0700

    ensure_dir_0700(target_dir)
    resolved_dir = target_dir.resolve()
    if not resolved_dir.is_relative_to(root):
        raise _InvalidInputError
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    target = resolved_dir / digest
    if not target.resolve(strict=False).is_relative_to(root):
        raise _InvalidInputError
    return target, digest


def _save_s3_body(body: Any, target: Path, initial: bytes = b"") -> None:
    """Stream an S3 body to an atomically replaced mode-0600 file."""
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            if initial:
                stream.write(initial)
            while True:
                chunk = body.read(64 * 1024)
                if not chunk:
                    break
                stream.write(chunk)
        os.replace(temp_path, target)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()


def enclave_s3_get(source: str, bucket: str, key: str) -> dict[str, Any] | str:
    """Read a small text object or save a non-text/large object inside enclave data."""
    body = None
    try:
        key = _require_raw_text(key)
        _, source_config = _source_context(source)
        bucket = _validate_bucket(source_config, bucket)
        client = _client(source_config, "s3")
        head = client.head_object(Bucket=bucket, Key=key)
        size = head.get("ContentLength")
        content_type = head.get("ContentType")
        content_type = content_type.split(";", 1)[0].strip().casefold() if isinstance(content_type, str) else ""
        is_text = content_type.startswith("text/") or content_type == "application/json"

        if is_text and isinstance(size, int) and size <= source_config.max_bytes:
            obj = client.get_object(Bucket=bucket, Key=key)
            body = obj.get("Body")
            if body is None:
                raise RuntimeError("missing S3 object body")
            raw = body.read(source_config.max_bytes + 1)
            if not isinstance(raw, bytes):
                raise RuntimeError("invalid S3 response body")
            if len(raw) <= source_config.max_bytes:
                text = raw.decode("utf-8", errors="replace")
                _record_json_lines(source, source_config, text)
                close = getattr(body, "close", None)
                if callable(close):
                    close()
                body = None
                return _text_result(
                    source,
                    source_config,
                    text,
                    extra={"bucket": bucket, "key": key, "content_type": content_type, "content_length": size},
                )
            # The object changed after HEAD or exceeded its advertised size; preserve it locally.
            target, digest = _download_path(_get_data_dir(), bucket, key)
            _save_s3_body(body, target, raw)
            body = None
            return {
                "source": source,
                "bucket": bucket,
                "key": key,
                "content_type": content_type,
                "content_length": size,
                "key_sha256": digest,
                "saved_path": str(target),
                "text": "",
                "truncated": False,
            }

        obj = client.get_object(Bucket=bucket, Key=key)
        body = obj.get("Body")
        if body is None:
            raise RuntimeError("missing S3 object body")
        target, digest = _download_path(_get_data_dir(), bucket, key)
        _save_s3_body(body, target)
        body = None
        return {
            "source": source,
            "bucket": bucket,
            "key": key,
            "content_type": content_type,
            "content_length": size,
            "key_sha256": digest,
            "saved_path": str(target),
            "text": "",
            "truncated": False,
        }
    except Exception as exc:  # noqa: BLE001 - do not expose AWS responses or credentials
        if body is not None:
            close = getattr(body, "close", None)
            if callable(close):
                close()
        return _tool_error(exc, source)


def _get_data_dir() -> Path:
    from core.paths import get_data_dir

    return get_data_dir()


def enclave_s3_list(source: str, bucket: str, prefix: str = "", limit: int = 100) -> dict[str, Any] | str:
    """List keys below an allowed S3 bucket and prefix."""
    try:
        prefix = _require_raw_text(prefix, allow_empty=True)
        limit = _require_limit(limit, minimum=1, maximum=_MAX_S3_LIST_LIMIT)
        _, source_config = _source_context(source)
        bucket = _validate_bucket(source_config, bucket)
        response = _client(source_config, "s3").list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=limit)
        objects = response.get("Contents", []) if isinstance(response, dict) else []
        entries = [obj for obj in objects if isinstance(obj, dict)]
        text = "\n".join(_json_text(entry) for entry in entries)
        has_more = bool(response.get("IsTruncated")) if isinstance(response, dict) else False
        return _text_result(
            source,
            source_config,
            text,
            extra={"bucket": bucket, "key_count": len(entries), "next_page_available": has_more},
            truncated=has_more,
        )
    except Exception as exc:  # noqa: BLE001 - do not expose AWS responses or credentials
        return _tool_error(exc, source)


def _tool_error(exc: Exception, _source_name: str) -> str:
    if isinstance(exc, _EnclaveDisabledError):
        return t("enclave.aws.only")
    if isinstance(exc, _SourceRequiredError):
        return t("enclave.aws.source_required")
    if isinstance(exc, _SourceNotConfiguredError):
        return t("enclave.aws.source_not_configured")
    if isinstance(exc, _TargetNotAllowedError):
        return t("enclave.aws.target_not_allowed")
    if isinstance(exc, _InvalidInputError):
        return t("enclave.aws.invalid_input")
    if isinstance(exc, _QueryTimeoutError):
        return t("enclave.aws.query_timeout")
    if isinstance(exc, _InvalidAwsSecretError):
        return t("enclave.aws.invalid_secret")
    if isinstance(exc, _AwsDependencyError):
        return t("enclave.aws.dependencies_missing")
    logger.warning("Could not use enclave AWS source (%s)", type(exc).__name__)
    return t("enclave.aws.unavailable")


def _dispatch_logs_query(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_logs_query(
        source=args.get("source", ""),
        log_group=args.get("log_group", ""),
        query=args.get("query", ""),
        start=args.get("start", ""),
        end=args.get("end", ""),
        limit=args.get("limit", 100),
    )


def _dispatch_logs_filter(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_logs_filter(
        source=args.get("source", ""),
        log_group=args.get("log_group", ""),
        filter_pattern=args.get("filter_pattern", ""),
        start=args.get("start", ""),
        end=args.get("end", ""),
        limit=args.get("limit", 100),
    )


def _dispatch_pi_top(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_pi_top_sql(
        source=args.get("source", ""),
        start=args.get("start", ""),
        end=args.get("end", ""),
        metric=args.get("metric", "db.load.avg"),
        group_by=args.get("group_by", "db.sql"),
        limit=args.get("limit", 10),
    )


def _dispatch_pi_detail(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_pi_sql_detail(source=args.get("source", ""), group_identifier=args.get("group_identifier", ""))


def _dispatch_rds_logs(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_rds_logs(
        source=args.get("source", ""),
        log_file_name=args.get("log_file_name"),
        marker=args.get("marker"),
        lines=args.get("lines", 500),
    )


def _dispatch_s3_get(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_s3_get(source=args.get("source", ""), bucket=args.get("bucket", ""), key=args.get("key", ""))


def _dispatch_s3_list(args: dict[str, Any]) -> dict[str, Any] | str:
    return enclave_s3_list(
        source=args.get("source", ""),
        bucket=args.get("bucket", ""),
        prefix=args.get("prefix", ""),
        limit=args.get("limit", 100),
    )


_DISPATCH_HANDLERS = {
    "enclave_logs_query": _dispatch_logs_query,
    "enclave_logs_filter": _dispatch_logs_filter,
    "enclave_pi_top_sql": _dispatch_pi_top,
    "enclave_pi_sql_detail": _dispatch_pi_detail,
    "enclave_rds_logs": _dispatch_rds_logs,
    "enclave_s3_get": _dispatch_s3_get,
    "enclave_s3_list": _dispatch_s3_list,
}


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch an enclave AWS tool call by its schema name."""
    return dispatch_by_table(_DISPATCH_HANDLERS, name, args)


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return tool schemas for the read-only AWS operations."""
    source = {"type": "string", "description": t("enclave.aws.schema_source")}
    time_value = {"type": "string", "description": t("enclave.aws.schema_time")}
    limit_logs = {"type": "integer", "minimum": 1, "maximum": _MAX_LOG_LIMIT, "default": 100}
    return [
        {
            "name": "enclave_logs_query",
            "description": t("enclave.aws.schema_logs_query"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": source,
                    "log_group": {"type": "string", "description": t("enclave.aws.schema_log_group")},
                    "query": {"type": "string", "description": t("enclave.aws.schema_query")},
                    "start": time_value,
                    "end": time_value,
                    "limit": limit_logs,
                },
                "required": ["source", "log_group", "query", "start", "end"],
            },
        },
        {
            "name": "enclave_logs_filter",
            "description": t("enclave.aws.schema_logs_filter"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": source,
                    "log_group": {"type": "string", "description": t("enclave.aws.schema_log_group")},
                    "filter_pattern": {"type": "string", "description": t("enclave.aws.schema_filter_pattern")},
                    "start": time_value,
                    "end": time_value,
                    "limit": limit_logs,
                },
                "required": ["source", "log_group", "filter_pattern", "start", "end"],
            },
        },
        {
            "name": "enclave_pi_top_sql",
            "description": t("enclave.aws.schema_pi_top_sql"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": source,
                    "start": time_value,
                    "end": time_value,
                    "metric": {"type": "string", "default": "db.load.avg"},
                    "group_by": {"type": "string", "default": "db.sql"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_PI_LIMIT, "default": 10},
                },
                "required": ["source", "start", "end"],
            },
        },
        {
            "name": "enclave_pi_sql_detail",
            "description": t("enclave.aws.schema_pi_sql_detail"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": source,
                    "group_identifier": {
                        "type": "string",
                        "description": t("enclave.aws.schema_group_identifier"),
                    },
                },
                "required": ["source", "group_identifier"],
            },
        },
        {
            "name": "enclave_rds_logs",
            "description": t("enclave.aws.schema_rds_logs"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": source,
                    "log_file_name": {"type": "string", "description": t("enclave.aws.schema_log_file_name")},
                    "marker": {"type": "string", "description": t("enclave.aws.schema_marker")},
                    "lines": {"type": "integer", "minimum": 1, "maximum": _MAX_LOG_LIMIT, "default": 500},
                },
                "required": ["source"],
            },
        },
        {
            "name": "enclave_s3_get",
            "description": t("enclave.aws.schema_s3_get"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": source,
                    "bucket": {"type": "string", "description": t("enclave.aws.schema_bucket")},
                    "key": {"type": "string", "description": t("enclave.aws.schema_key")},
                },
                "required": ["source", "bucket", "key"],
            },
        },
        {
            "name": "enclave_s3_list",
            "description": t("enclave.aws.schema_s3_list"),
            "input_schema": {
                "type": "object",
                "properties": {
                    "source": source,
                    "bucket": {"type": "string", "description": t("enclave.aws.schema_bucket")},
                    "prefix": {"type": "string", "default": ""},
                    "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_S3_LIST_LIMIT, "default": 100},
                },
                "required": ["source", "bucket"],
            },
        },
    ]


__all__ = [
    "dispatch",
    "enclave_logs_filter",
    "enclave_logs_query",
    "enclave_pi_sql_detail",
    "enclave_pi_top_sql",
    "enclave_rds_logs",
    "enclave_s3_get",
    "enclave_s3_list",
    "get_tool_schemas",
]
