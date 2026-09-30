"""E2E coverage for DM activity-log rotation."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from core.tasks.background import _rotate_dm_logs_sync
from core.time_utils import now_jst


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    shared = tmp_path / "shared"
    (shared / "dm_logs").mkdir(parents=True)
    return tmp_path


@pytest.mark.e2e
def test_dm_log_rotation_end_to_end(workspace: Path) -> None:
    """Archive old DM log entries while retaining recent ones."""
    shared_dir = workspace / "shared"
    dm_logs_dir = shared_dir / "dm_logs"
    base = now_jst()
    old_ts = (base - timedelta(days=10)).isoformat()
    recent_ts = (base - timedelta(days=2)).isoformat()

    filepath = dm_logs_dir / "alice-bob.jsonl"
    entries = [
        {"ts": old_ts, "from": "alice", "to": "bob", "text": "old message"},
        {"ts": recent_ts, "from": "bob", "to": "alice", "text": "recent message"},
    ]
    filepath.write_text("".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries), encoding="utf-8")

    result = _rotate_dm_logs_sync(shared_dir, max_age_days=7)

    assert result["alice-bob.jsonl"]["archived"] == 1
    assert result["alice-bob.jsonl"]["kept"] == 1
    archive_path = dm_logs_dir / f"alice-bob.{base.strftime('%Y%m%d')}.archive.jsonl"
    archived = [json.loads(line) for line in archive_path.read_text(encoding="utf-8").splitlines()]
    retained = [json.loads(line) for line in filepath.read_text(encoding="utf-8").splitlines()]
    assert [entry["text"] for entry in archived] == ["old message"]
    assert [entry["text"] for entry in retained] == ["recent message"]
