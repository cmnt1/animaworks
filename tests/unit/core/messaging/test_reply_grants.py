from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.messaging import reply_grants
from core.messaging.reply_grants import has_reply_grant, record_reply_grant


def _store_path(anima_dir: Path) -> Path:
    return anima_dir / "state" / "external_reply_grants.json"


def test_record_and_match_exact_platform_channel_and_thread(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"

    assert record_reply_grant(anima_dir, "slack", "C123", "1791155828.085789") is True

    assert has_reply_grant(anima_dir, "slack", "C123", "1791155828.085789") is True
    assert has_reply_grant(anima_dir, "slack", "C123", "9999.0001") is False
    assert has_reply_grant(anima_dir, "slack", "C456", "1791155828.085789") is False
    assert has_reply_grant(anima_dir, "chatwork", "C123", "1791155828.085789") is False

    payload = json.loads(_store_path(anima_dir).read_text(encoding="utf-8"))
    assert payload["grants"] == [
        {
            "platform": "slack",
            "channel_id": "C123",
            "thread_ts": "1791155828.085789",
            "granted_at": payload["grants"][0]["granted_at"],
            "expires_at": payload["grants"][0]["expires_at"],
        }
    ]


def test_expired_entries_are_pruned_when_read(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    path = _store_path(anima_dir)
    path.parent.mkdir(parents=True)
    expired_at = datetime.now(UTC) - timedelta(hours=1)
    granted_at = expired_at - timedelta(hours=24)
    path.write_text(
        json.dumps(
            {
                "grants": [
                    {
                        "platform": "slack",
                        "channel_id": "C123",
                        "thread_ts": "old-thread",
                        "granted_at": granted_at.isoformat(),
                        "expires_at": expired_at.isoformat(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert has_reply_grant(anima_dir, "slack", "C123", "old-thread") is False
    assert json.loads(path.read_text(encoding="utf-8")) == {"grants": []}


def test_expired_entries_are_pruned_when_recording(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    path = _store_path(anima_dir)
    path.parent.mkdir(parents=True)
    expired_at = datetime.now(UTC) - timedelta(hours=1)
    granted_at = expired_at - timedelta(hours=24)
    path.write_text(
        json.dumps(
            {
                "grants": [
                    {
                        "platform": "slack",
                        "channel_id": "C123",
                        "thread_ts": "old-thread",
                        "granted_at": granted_at.isoformat(),
                        "expires_at": expired_at.isoformat(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert record_reply_grant(anima_dir, "slack", "C123", "new-thread") is True

    entries = json.loads(path.read_text(encoding="utf-8"))["grants"]
    assert [entry["thread_ts"] for entry in entries] == ["new-thread"]


def test_oldest_entries_are_dropped_at_limit(tmp_path: Path, monkeypatch) -> None:
    anima_dir = tmp_path / "alice"
    monkeypatch.setattr(reply_grants, "MAX_REPLY_GRANTS", 2)

    for thread_ts in ("thread-1", "thread-2", "thread-3"):
        assert record_reply_grant(anima_dir, "slack", "C123", thread_ts) is True

    entries = json.loads(_store_path(anima_dir).read_text(encoding="utf-8"))["grants"]
    assert [entry["thread_ts"] for entry in entries] == ["thread-2", "thread-3"]
    assert has_reply_grant(anima_dir, "slack", "C123", "thread-1") is False
    assert has_reply_grant(anima_dir, "slack", "C123", "thread-2") is True
    assert has_reply_grant(anima_dir, "slack", "C123", "thread-3") is True


def test_corrupt_json_is_treated_as_empty_and_warned(tmp_path: Path, caplog) -> None:
    anima_dir = tmp_path / "alice"
    path = _store_path(anima_dir)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="core.messaging.reply_grants"):
        assert has_reply_grant(anima_dir, "slack", "C123", "thread-1") is False

    assert any("Corrupt reply grant JSON" in record.message for record in caplog.records)
    assert json.loads(path.read_text(encoding="utf-8")) == {"grants": []}

    assert record_reply_grant(anima_dir, "slack", "C123", "thread-1") is True
    assert has_reply_grant(anima_dir, "slack", "C123", "thread-1") is True
