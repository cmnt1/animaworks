# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for enclave read-only AWS tools; all AWS clients are local fakes."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.config import invalidate_cache
from core.enclave.config import EnclaveAwsSourceConfig, EnclaveConfig
from core.integrations import enclave_aws
from tests.helpers.filesystem import DEFAULT_TEST_CONFIG


def _source(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "region": "example-region-1",
        "aws_secret": "aws-readonly",
        "log_groups": ["/example/application/*"],
        "pi_resource_id": "db-example-resource",
        "rds_instance_id": "db-example-instance",
        "s3_buckets": ["example-placeholder-bucket"],
    }
    result.update(overrides)
    return result


def _write_config(data_dir: Path, sources: dict[str, dict[str, Any]], *, enabled: bool = True) -> None:
    config = dict(DEFAULT_TEST_CONFIG)
    config["enclave"] = {
        "enabled": enabled,
        "secrets_dir": str(data_dir / "secrets"),
        "aws_sources": sources,
    }
    (data_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    invalidate_cache()


def _patch_clients(monkeypatch: pytest.MonkeyPatch, **clients: Any) -> None:
    monkeypatch.setattr(enclave_aws, "_client", lambda _source_config, service: clients[service])


class _LogsClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.start_request: dict[str, Any] | None = None
        self.query_requests: list[dict[str, Any]] = []

    def start_query(self, **kwargs: Any) -> dict[str, str]:
        self.start_request = kwargs
        return {"queryId": "query-id"}

    def get_query_results(self, **kwargs: Any) -> dict[str, Any]:
        self.query_requests.append(kwargs)
        return self.responses.pop(0)


class _S3Body(io.BytesIO):
    pass


def test_aws_source_config_defaults_and_validation() -> None:
    config = EnclaveConfig.model_validate({"aws_sources": {"logs": _source()}})
    source = config.aws_sources["logs"]

    assert source.max_bytes == 200_000
    assert source.ledger_register is True
    assert "timestamp" in source.ledger_exempt_keys
    assert source.log_groups == ["/example/application/*"]
    with pytest.raises(ValueError):
        EnclaveAwsSourceConfig(region="example-region-1", aws_secret="secret", max_bytes=0)


def test_aws_tools_are_registered_only_when_enclave_is_enabled(data_dir: Path) -> None:
    from core.tooling.policy.registry import TOOL_MODULES, get_tool_modules

    assert "enclave_aws" not in TOOL_MODULES
    assert "enclave_aws" not in get_tool_modules(enclave_enabled=False)
    assert get_tool_modules(enclave_enabled=True)["enclave_aws"] == "core.integrations.enclave_aws"

    _write_config(data_dir, {"logs": _source()})
    schemas = {item["name"] for item in enclave_aws.get_tool_schemas()}
    assert schemas == {
        "enclave_logs_query",
        "enclave_logs_filter",
        "enclave_pi_top_sql",
        "enclave_pi_sql_detail",
        "enclave_rds_logs",
        "enclave_s3_get",
        "enclave_s3_list",
    }


def test_aws_session_uses_secret_credentials_only(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    fake_session = object()

    def make_session(**kwargs: Any) -> object:
        seen.update(kwargs)
        return fake_session

    monkeypatch.setattr(
        "core.enclave.secrets.read_enclave_secret",
        lambda name: '{"aws_access_key_id":"AKIA_TEST","aws_secret_access_key":"secret-test"}',
    )
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(Session=make_session))
    source = EnclaveAwsSourceConfig(region="example-region-1", aws_secret="aws-readonly")

    assert enclave_aws._create_session(source) is fake_session
    assert seen == {
        "region_name": "example-region-1",
        "aws_access_key_id": "AKIA_TEST",
        "aws_secret_access_key": "secret-test",
    }


def test_logs_query_polls_and_records_structured_values(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    message = json.dumps(
        {"email": "person@example.invalid", "status": "ok", "message": "free-form text"}, ensure_ascii=False
    )
    logs = _LogsClient(
        [
            {"status": "Scheduled"},
            {"status": "Running"},
            {
                "status": "Complete",
                "results": [
                    [
                        {"field": "@timestamp", "value": "2026-10-09T00:00:00Z"},
                        {"field": "@message", "value": message},
                    ]
                ],
            },
        ]
    )
    _write_config(data_dir, {"logs": _source()})
    _patch_clients(monkeypatch, logs=logs)
    monkeypatch.setattr(enclave_aws.time, "sleep", lambda _seconds: None)

    result = enclave_aws.enclave_logs_query(
        "logs",
        "/example/application/worker",
        "fields @message",
        "2026-10-09T00:00:00Z",
        "2026-10-09T01:00:00+00:00",
        limit=5,
    )

    assert isinstance(result, dict)
    assert result["status"] == "Complete"
    assert result["truncated"] is False
    assert len(logs.query_requests) == 3
    assert logs.start_request is not None
    assert logs.start_request["startTime"] < logs.start_request["endTime"]
    ledger = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    values = {json.loads(line)["value"] for line in ledger.read_text(encoding="utf-8").splitlines()}
    assert values == {"person@example.invalid"}


def test_logs_query_rejects_source_command_that_could_escape_log_group_allowlist(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(data_dir, {"logs": _source()})
    monkeypatch.setattr(enclave_aws, "_client", lambda *_args: pytest.fail("AWS client must not be created"))

    result = enclave_aws.enclave_logs_query("logs", "/example/application/worker", "SOURCE logGroups()", "-1h", "-1m")

    assert isinstance(result, str)
    assert "許可" in result or "allowed" in result


def test_logs_query_rejects_unconfigured_log_group_before_aws_call(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_config(data_dir, {"logs": _source()})
    monkeypatch.setattr(enclave_aws, "_client", lambda *_args: pytest.fail("AWS client must not be created"))

    result = enclave_aws.enclave_logs_query("logs", "/unconfigured/group", "fields @message", "-1h", "-1m")

    assert isinstance(result, str)
    assert "許可" in result or "allowed" in result


def test_logs_filter_uses_milliseconds_and_only_ledgers_json_message(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_message = json.dumps(
        {"record_value": "structured-secret", "status": "ok", "message": "free text"}, ensure_ascii=False
    )

    class Logs:
        request: dict[str, Any] | None = None

        def filter_log_events(self, **kwargs: Any) -> dict[str, Any]:
            self.request = kwargs
            return {
                "events": [
                    {
                        "timestamp": 1_791_504_000_000,
                        "eventId": "event-id",
                        "logStreamName": "stream",
                        "message": event_message,
                    }
                ],
                "nextToken": "next-page",
            }

    logs = Logs()
    _write_config(data_dir, {"logs": _source()})
    _patch_clients(monkeypatch, logs=logs)

    result = enclave_aws.enclave_logs_filter("logs", "/example/application/worker", "", "-1h", "-1m", limit=20)

    assert isinstance(result, dict)
    assert result["truncated"] is True
    assert result["next_page_available"] is True
    assert logs.request is not None
    assert logs.request["endTime"] > logs.request["startTime"]
    assert "filterPattern" not in logs.request
    ledger = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    values = {json.loads(line)["value"] for line in ledger.read_text(encoding="utf-8").splitlines()}
    assert values == {"structured-secret"}


def test_performance_insights_top_sql_uses_configured_resource_and_caps_response(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = "SELECT * FROM records WHERE token = 'sql-literal'"

    class Pi:
        request: dict[str, Any] | None = None

        def describe_dimension_keys(self, **kwargs: Any) -> dict[str, Any]:
            self.request = kwargs
            return {"Keys": [{"Dimensions": [{"Value": sql}], "Total": 1}], "NextToken": "more"}

    pi = Pi()
    _write_config(data_dir, {"logs": _source(max_bytes=20)})
    _patch_clients(monkeypatch, pi=pi)

    result = enclave_aws.enclave_pi_top_sql("logs", "-1h", "-1m", limit=5)

    assert isinstance(result, dict)
    assert result["truncated"] is True
    assert len(result["text"].encode("utf-8")) <= 20
    assert pi.request is not None
    assert pi.request["ServiceType"] == "RDS"
    assert pi.request["Identifier"] == "db-example-resource"
    assert pi.request["Metric"] == "db.load.avg"
    assert pi.request["GroupBy"] == {"Group": "db.sql"}
    assert pi.request["MaxResults"] == 5
    ledger = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    assert {json.loads(line)["value"] for line in ledger.read_text(encoding="utf-8").splitlines()} == {"sql-literal"}


def test_performance_insights_rejects_limit_above_api_maximum(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(data_dir, {"logs": _source()})
    monkeypatch.setattr(enclave_aws, "_client", lambda *_args: pytest.fail("AWS client must not be created"))

    result = enclave_aws.enclave_pi_top_sql("logs", "-1h", "-1m", limit=26)

    assert isinstance(result, str)
    assert "invalid" in result.casefold() or "無効" in result


def test_performance_insights_detail_ledgers_only_sql_string_literals(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sql = "SELECT * FROM logs WHERE address = 'sample street' AND owner = 'O''Reilly' /* 'ignore me' */"

    class Pi:
        request: dict[str, Any] | None = None

        def get_dimension_key_details(self, **kwargs: Any) -> dict[str, Any]:
            self.request = kwargs
            return {"Dimensions": [{"Dimension": "db.sql.statement", "Value": sql}]}

    pi = Pi()
    _write_config(data_dir, {"logs": _source()})
    _patch_clients(monkeypatch, pi=pi)

    result = enclave_aws.enclave_pi_sql_detail("logs", "sql-group")

    assert isinstance(result, dict)
    assert "SELECT * FROM logs" in result["text"]
    assert pi.request == {
        "ServiceType": "RDS",
        "Identifier": "db-example-resource",
        "Group": "db.sql",
        "GroupIdentifier": "sql-group",
    }
    ledger = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    values = {json.loads(line)["value"] for line in ledger.read_text(encoding="utf-8").splitlines()}
    assert values == {"sample street", "O'Reilly"}


def test_rds_logs_returns_portion_and_ledgers_only_structured_json(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Rds:
        request: dict[str, Any] | None = None

        def download_db_log_file_portion(self, **kwargs: Any) -> dict[str, Any]:
            self.request = kwargs
            return {
                "LogFileData": '{"email":"person@example.invalid","status":"ok"}\nordinary free text\n',
                "Marker": "more",
                "AdditionalDataPending": True,
            }

    rds = Rds()
    _write_config(data_dir, {"logs": _source()})
    _patch_clients(monkeypatch, rds=rds)

    result = enclave_aws.enclave_rds_logs("logs", log_file_name="error.log", lines=12)

    assert isinstance(result, dict)
    assert result["truncated"] is True
    assert result["text"].startswith('{"email"')
    assert rds.request == {
        "DBInstanceIdentifier": "db-example-instance",
        "LogFileName": "error.log",
        "NumberOfLines": 12,
    }
    ledger = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    values = {json.loads(line)["value"] for line in ledger.read_text(encoding="utf-8").splitlines()}
    assert values == {"person@example.invalid"}


def test_rds_logs_can_list_configured_instance_files(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Rds:
        request: dict[str, Any] | None = None

        def describe_db_log_files(self, **kwargs: Any) -> dict[str, Any]:
            self.request = kwargs
            return {
                "DescribeDBLogFiles": [{"LogFileName": "error.log", "Size": 12}],
                "Marker": "more",
            }

    rds = Rds()
    _write_config(data_dir, {"logs": _source()})
    _patch_clients(monkeypatch, rds=rds)

    result = enclave_aws.enclave_rds_logs("logs", lines=5)

    assert isinstance(result, dict)
    assert result["next_page_available"] is True
    assert result["marker"] == "more"
    assert rds.request == {"DBInstanceIdentifier": "db-example-instance", "MaxRecords": 20}
    assert '"LogFileName":"error.log"' in result["text"]


def test_s3_small_text_is_returned_and_structured_value_registered(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _S3Body(b'{"name":"sample-value","status":"ok"}')

    class S3:
        def head_object(self, **kwargs: Any) -> dict[str, Any]:
            assert kwargs["Bucket"] == "example-placeholder-bucket"
            return {"ContentLength": len(body.getvalue()), "ContentType": "application/json; charset=utf-8"}

        def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Body": body}

    _write_config(data_dir, {"logs": _source()})
    _patch_clients(monkeypatch, s3=S3())

    result = enclave_aws.enclave_s3_get("logs", "example-placeholder-bucket", "records/data.json")

    assert isinstance(result, dict)
    assert result["content_type"] == "application/json"
    assert result["text"] == '{"name":"sample-value","status":"ok"}'
    assert result["truncated"] is False
    assert body.closed
    ledger = data_dir / "enclave" / "ledger" / "known_values.jsonl"
    values = {json.loads(line)["value"] for line in ledger.read_text(encoding="utf-8").splitlines()}
    assert values == {"sample-value"}


def test_s3_binary_is_saved_under_hashed_contained_mode_0600_path(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = "../../outside/voice.wav"
    payload = b"audio bytes"
    body = _S3Body(payload)

    class S3:
        def head_object(self, **_kwargs: Any) -> dict[str, Any]:
            return {"ContentLength": len(payload), "ContentType": "audio/wav"}

        def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Body": body}

    _write_config(data_dir, {"logs": _source()})
    _patch_clients(monkeypatch, s3=S3())

    result = enclave_aws.enclave_s3_get("logs", "example-placeholder-bucket", key)

    assert isinstance(result, dict)
    target = Path(result["saved_path"])
    expected = (
        data_dir
        / "enclave"
        / "downloads"
        / "example-placeholder-bucket"
        / hashlib.sha256(key.encode("utf-8")).hexdigest()
    )
    assert target == expected
    assert target.resolve().is_relative_to(data_dir.resolve())
    assert target.read_bytes() == payload
    assert target.stat().st_mode & 0o777 == 0o600
    assert result["text"] == ""
    assert body.closed


def test_s3_object_larger_than_max_bytes_is_saved_without_returning_body(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"too-large-text"
    body = _S3Body(payload)

    class S3:
        def head_object(self, **_kwargs: Any) -> dict[str, Any]:
            return {"ContentLength": len(payload), "ContentType": "text/plain"}

        def get_object(self, **_kwargs: Any) -> dict[str, Any]:
            return {"Body": body}

    source = _source(max_bytes=5)
    _write_config(data_dir, {"logs": source})
    _patch_clients(monkeypatch, s3=S3())

    result = enclave_aws.enclave_s3_get("logs", "example-placeholder-bucket", "large.txt")

    assert isinstance(result, dict)
    assert result["text"] == ""
    assert Path(result["saved_path"]).read_bytes() == payload
    assert result["truncated"] is False
    assert body.closed


def test_s3_list_uses_allowlisted_bucket_and_reports_more_pages(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class S3:
        request: dict[str, Any] | None = None

        def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
            self.request = kwargs
            return {
                "Contents": [{"Key": "prefix/item.txt", "Size": 3}],
                "IsTruncated": True,
            }

    s3 = S3()
    _write_config(data_dir, {"logs": _source()})
    _patch_clients(monkeypatch, s3=s3)

    result = enclave_aws.enclave_s3_list("logs", "example-placeholder-bucket", prefix="prefix/", limit=3)

    assert isinstance(result, dict)
    assert result["key_count"] == 1
    assert result["next_page_available"] is True
    assert result["truncated"] is True
    assert s3.request == {"Bucket": "example-placeholder-bucket", "Prefix": "prefix/", "MaxKeys": 3}


def test_aws_service_errors_never_return_exception_or_secret_text(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenLogs:
        def filter_log_events(self, **_kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("AWS_SECRET_KEY=do-not-leak")

    _write_config(data_dir, {"logs": _source()})
    _patch_clients(monkeypatch, logs=BrokenLogs())

    result = enclave_aws.enclave_logs_filter("logs", "/example/application/worker", "", "-1h", "-1m")

    assert isinstance(result, str)
    assert "do-not-leak" not in result
    assert "AWS_SECRET_KEY" not in result


def test_parse_time_accepts_now() -> None:
    import time

    from core.integrations.enclave_aws import _parse_time

    assert abs(_parse_time("now") - int(time.time())) <= 2
    assert _parse_time("NOW") >= _parse_time("-1h")


def test_numbers_and_timestamps_are_not_registered(monkeypatch) -> None:
    from types import SimpleNamespace

    import core.enclave.egress.ledger as ledger
    from core.integrations import enclave_aws

    captured: list[str] = []
    monkeypatch.setattr(ledger, "record_known_values", lambda _d, values, source: captured.extend(values))
    config = SimpleNamespace(ledger_register=True)
    enclave_aws._record_values("prod", config, ["12", "3.5", "2026-10-10T07:00:00Z", "true", "Taro Example"])
    assert captured == ["Taro Example"]
