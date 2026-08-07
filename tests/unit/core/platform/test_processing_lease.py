"""Unit tests for processing lease schema v1/v2."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.platform.processing_lease import (
    classify_processing_lease,
    is_processing_lease_live,
    processing_lease_path,
    read_processing_lease,
    write_processing_lease,
)


def test_v1_round_trip_and_live_with_runner_cmdline(tmp_path: Path) -> None:
    descriptor = tmp_path / "task.json"
    descriptor.write_text('{"task_id":"t1"}', encoding="utf-8")
    lease = write_processing_lease(
        descriptor,
        anima="sakura",
        task_id="t1",
        pid=os.getpid(),
    )
    payload = json.loads(lease.read_text(encoding="utf-8"))
    assert "schema_version" not in payload
    assert payload["pid"] == os.getpid()
    assert payload["anima"] == "sakura"
    assert payload["task_id"] == "t1"

    with patch(
        "core.platform.processing_lease._read_proc_cmdline",
        return_value="python -m core.supervisor.runner --anima-name sakura",
    ):
        assert is_processing_lease_live(descriptor, expected_anima="sakura")
        assert classify_processing_lease(descriptor, expected_anima="sakura") == "live"


def test_v2_round_trip_fields(tmp_path: Path) -> None:
    descriptor = tmp_path / "task.json"
    descriptor.write_text('{"task_id":"t2"}', encoding="utf-8")
    start = time.time()
    lease = write_processing_lease(
        descriptor,
        anima="sakura",
        task_id="t2",
        pid=os.getpid(),
        job_id="job-abc",
        task_pid=os.getpid(),
        pgid=os.getpid(),
        root_epoch="550e8400-e29b-41d4-a716-446655440000",
        attempt=1,
        process_start_time=start,
    )
    payload = json.loads(lease.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["job_id"] == "job-abc"
    assert payload["task_pid"] == os.getpid()
    assert payload["pgid"] == os.getpid()
    assert payload["root_epoch"] == "550e8400-e29b-41d4-a716-446655440000"
    assert payload["attempt"] == 1
    assert payload["process_start_time"] == start
    assert read_processing_lease(descriptor) == payload


def test_v2_live_with_task_runner_cmdline(tmp_path: Path) -> None:
    descriptor = tmp_path / "task.json"
    descriptor.write_text('{"task_id":"t3"}', encoding="utf-8")
    start = time.time()
    write_processing_lease(
        descriptor,
        anima="sakura",
        task_id="t3",
        pid=1,
        job_id="job-xyz",
        task_pid=os.getpid(),
        pgid=os.getpid(),
        root_epoch="epoch-1",
        attempt=2,
        process_start_time=start,
    )

    with (
        patch(
            "core.platform.processing_lease._process_create_time",
            return_value=start,
        ),
        patch(
            "core.platform.processing_lease._read_proc_cmdline",
            return_value="python -m core.supervisor.task_runner --anima sakura --job job-xyz",
        ),
    ):
        assert is_processing_lease_live(descriptor, expected_anima="sakura")


def test_v2_pid_reuse_fence_marks_dead(tmp_path: Path) -> None:
    descriptor = tmp_path / "task.json"
    descriptor.write_text('{"task_id":"t4"}', encoding="utf-8")
    write_processing_lease(
        descriptor,
        anima="sakura",
        task_id="t4",
        pid=1,
        job_id="job-reuse",
        task_pid=os.getpid(),
        pgid=os.getpid(),
        root_epoch="epoch-1",
        attempt=1,
        process_start_time=1.0,
    )

    with (
        patch(
            "core.platform.processing_lease._process_create_time",
            return_value=9999.0,  # different process start → PID reuse
        ),
        patch(
            "core.platform.processing_lease._read_proc_cmdline",
            return_value="python -m core.supervisor.task_runner --anima sakura --job job-reuse",
        ),
    ):
        assert classify_processing_lease(descriptor, expected_anima="sakura") == "dead"
        assert not is_processing_lease_live(descriptor, expected_anima="sakura")


@pytest.mark.skipif(os.name == "nt", reason="cmdline classification needs /proc; Windows stops at the PID check")
def test_v2_wrong_cmdline_is_dead(tmp_path: Path) -> None:
    descriptor = tmp_path / "task.json"
    descriptor.write_text('{"task_id":"t5"}', encoding="utf-8")
    start = time.time()
    write_processing_lease(
        descriptor,
        anima="sakura",
        task_id="t5",
        pid=1,
        job_id="job-bad",
        task_pid=os.getpid(),
        pgid=os.getpid(),
        root_epoch="epoch-1",
        attempt=1,
        process_start_time=start,
    )
    with (
        patch(
            "core.platform.processing_lease._process_create_time",
            return_value=start,
        ),
        patch(
            "core.platform.processing_lease._read_proc_cmdline",
            return_value="python unrelated --anima sakura",
        ),
    ):
        assert not is_processing_lease_live(descriptor, expected_anima="sakura")


def test_legacy_v1_still_readable_without_schema_version(tmp_path: Path) -> None:
    descriptor = tmp_path / "legacy.json"
    descriptor.write_text("{}", encoding="utf-8")
    lease_path = processing_lease_path(descriptor)
    lease_path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "anima": "sakura",
                "leased_at": time.time(),
                "task_id": "legacy",
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "core.platform.processing_lease._read_proc_cmdline",
        return_value="python -m core.supervisor.runner --anima-name sakura",
    ):
        assert is_processing_lease_live(descriptor, expected_anima="sakura")


@pytest.mark.skipif(os.name == "nt", reason="cmdline classification needs /proc; Windows stops at the PID check")
def test_unreadable_proc_is_unknown_treated_as_live(tmp_path: Path) -> None:
    descriptor = tmp_path / "unknown.json"
    descriptor.write_text("{}", encoding="utf-8")
    write_processing_lease(descriptor, anima="sakura", task_id="u1", pid=os.getpid())
    with patch(
        "core.platform.processing_lease._read_proc_cmdline",
        side_effect=PermissionError("denied"),
    ):
        assert classify_processing_lease(descriptor, expected_anima="sakura") == "unknown"
        assert is_processing_lease_live(descriptor, expected_anima="sakura")


def test_malformed_lease_is_dead(tmp_path: Path) -> None:
    descriptor = tmp_path / "bad.json"
    descriptor.write_text("{}", encoding="utf-8")
    processing_lease_path(descriptor).write_bytes(b"\xff\xfe")
    assert classify_processing_lease(descriptor) == "dead"
    assert not is_processing_lease_live(descriptor)
