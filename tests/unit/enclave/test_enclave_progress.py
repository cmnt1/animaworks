# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the enclave_progress interim-progress tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from core.config import invalidate_cache
from core.enclave.jobs import EnclaveJob, EnclaveJobStore
from core.integrations.enclave_progress import cli_main, enclave_progress
from core.tooling.policy.registry import TOOL_MODULES, get_tool_modules
from tests.helpers.filesystem import DEFAULT_TEST_CONFIG


def _write_config(data_dir: Path, *, enabled: bool = True) -> None:
    config: dict[str, Any] = dict(DEFAULT_TEST_CONFIG)
    config["enclave"] = {"enabled": enabled}
    (data_dir / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    invalidate_cache()


def _seed_running_job(data_dir: Path) -> str:
    store = EnclaveJobStore(data_dir)
    job = EnclaveJob(
        job_id="job123",
        case_id="case-1",
        from_anima="host",
        question="q",
        thread_id="enclave-case-1",
        status="running",
    )
    store.save(job)
    return job.job_id


def test_writes_progress_to_running_job(data_dir: Path) -> None:
    _write_config(data_dir)
    job_id = _seed_running_job(data_dir)

    result = enclave_progress(job_id, "対象を特定しました")

    assert result == {"written": True, "job_id": job_id}
    store = EnclaveJobStore(data_dir)
    entries = store.read_progress(job_id)
    assert len(entries) == 1
    assert entries[0]["text"] == "対象を特定しました"


def test_clips_long_text_to_500_chars(data_dir: Path) -> None:
    _write_config(data_dir)
    job_id = _seed_running_job(data_dir)

    enclave_progress(job_id, "あ" * 600)

    entries = EnclaveJobStore(data_dir).read_progress(job_id)
    assert len(entries[0]["text"]) == 500


def test_errors_when_job_not_running(data_dir: Path) -> None:
    _write_config(data_dir)
    store = EnclaveJobStore(data_dir)
    job = EnclaveJob(
        job_id="job-done",
        case_id="c",
        from_anima="h",
        question="q",
        thread_id="enclave-c",
        status="done",
    )
    store.save(job)

    result = enclave_progress("job-done", "late update")
    assert isinstance(result, str)
    assert "実行中" in result


def test_errors_when_job_missing(data_dir: Path) -> None:
    _write_config(data_dir)
    result = enclave_progress("nope", "msg")
    assert isinstance(result, str)
    assert "見つかりません" in result


def test_disabled_enclave_is_rejected(data_dir: Path) -> None:
    _write_config(data_dir, enabled=False)
    _seed_running_job(data_dir)
    result = enclave_progress("job123", "msg")
    assert isinstance(result, str)
    assert "enclave 内でだけ" in result


def test_progress_tool_registered_only_in_enclave_mode() -> None:
    assert "enclave_progress" not in TOOL_MODULES
    assert "enclave_progress" not in get_tool_modules(enclave_enabled=False)
    assert get_tool_modules(enclave_enabled=True)["enclave_progress"] == "core.integrations.enclave_progress"


def test_schema_cli_maps_dashed_option_to_dispatch(capsys: pytest.CaptureFixture[str]) -> None:
    with patch(
        "core.integrations.enclave_progress.dispatch",
        return_value={"written": True},
    ) as dispatch:
        cli_main(["enclave_progress", "--job-id", "job123", "--text", "proceeding"])
    dispatch.assert_called_once_with("enclave_progress", {"job_id": "job123", "text": "proceeding"})
    assert json.loads(capsys.readouterr().out) == {"written": True}
