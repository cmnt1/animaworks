from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import json
import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from core.messaging.recipient_status import read_recipient_inbox_busy
from core.time_utils import now_local


def _layout(tmp_path: Path) -> Path:
    shared = tmp_path / "shared"
    (shared / "inbox" / "aoi").mkdir(parents=True)
    (tmp_path / "run" / "animas").mkdir(parents=True)
    return shared


def _write_sidecar(tmp_path: Path, payload: dict) -> None:
    (tmp_path / "run" / "animas" / "aoi.busy.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_unread(shared: Path, name: str, minutes_ago: float) -> None:
    f = shared / "inbox" / "aoi" / f"{name}.json"
    f.write_text("{}", encoding="utf-8")
    ts = (now_local() - timedelta(minutes=minutes_ago)).timestamp()
    os.utime(f, (ts, ts))


def test_long_inbox_run_reports_since_and_unread(tmp_path):
    shared = _layout(tmp_path)
    since = now_local() - timedelta(hours=3)
    _write_sidecar(
        tmp_path,
        {
            "lanes": ["background-worker:2:x", "inbox"],
            "busy_since": (now_local() - timedelta(minutes=1)).isoformat(),
            "lane_started_at": {"inbox": since.isoformat()},
        },
    )
    _write_unread(shared, "m1", 170)
    _write_unread(shared, "m2", 5)

    busy = read_recipient_inbox_busy(shared, "aoi")

    assert busy is not None
    assert busy.since == since
    assert busy.unread_count == 2
    assert busy.oldest_unread_at is not None
    assert now_local() - busy.oldest_unread_at > timedelta(minutes=160)


def test_short_inbox_run_is_silent(tmp_path):
    shared = _layout(tmp_path)
    _write_sidecar(
        tmp_path,
        {"lanes": ["inbox"], "lane_started_at": {"inbox": (now_local() - timedelta(minutes=2)).isoformat()}},
    )
    assert read_recipient_inbox_busy(shared, "aoi") is None


def test_other_lanes_busy_is_silent(tmp_path):
    shared = _layout(tmp_path)
    _write_sidecar(
        tmp_path,
        {"lanes": ["background"], "busy_since": (now_local() - timedelta(hours=2)).isoformat()},
    )
    assert read_recipient_inbox_busy(shared, "aoi") is None


def test_missing_sidecar_is_silent(tmp_path):
    shared = _layout(tmp_path)
    assert read_recipient_inbox_busy(shared, "aoi") is None


def test_falls_back_to_busy_since(tmp_path):
    shared = _layout(tmp_path)
    _write_sidecar(tmp_path, {"lanes": ["inbox"], "busy_since": (now_local() - timedelta(minutes=30)).isoformat()})
    busy = read_recipient_inbox_busy(shared, "aoi")
    assert busy is not None
    assert busy.unread_count == 0
    assert busy.oldest_unread_at is None


def test_handler_notice_text(tmp_path):
    from core.tooling.handler_comms import CommsToolsMixin

    shared = _layout(tmp_path)
    _write_sidecar(
        tmp_path,
        {"lanes": ["inbox"], "lane_started_at": {"inbox": (now_local() - timedelta(minutes=190)).isoformat()}},
    )
    _write_unread(shared, "m1", 60)

    mixin = CommsToolsMixin.__new__(CommsToolsMixin)
    mixin._messenger = SimpleNamespace(shared_dir=shared)

    notice = mixin._build_recipient_busy_notice("aoi")

    assert "aoi" in notice
    assert "3h10m" in notice
    assert "1" in notice


def test_handler_notice_empty_when_idle(tmp_path):
    from core.tooling.handler_comms import CommsToolsMixin

    shared = _layout(tmp_path)
    mixin = CommsToolsMixin.__new__(CommsToolsMixin)
    mixin._messenger = SimpleNamespace(shared_dir=shared)

    assert mixin._build_recipient_busy_notice("aoi") == ""
