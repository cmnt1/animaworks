from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.memory.priming import PrimingEngine
from core.notification import notification_key_for
from core.time_utils import now_iso


def _write_activity(anima_dir: Path, entries: list[dict]) -> None:
    log_dir = anima_dir / "activity_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = entries[0]["ts"][:10] if entries else "2026-05-14"
    path = log_dir / f"{date_str}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _anima_dir(tmp_path: Path) -> Path:
    anima_dir = tmp_path / "data" / "animas" / "rin"
    (anima_dir / "activity_log").mkdir(parents=True)
    return anima_dir


@pytest.mark.asyncio
async def test_human_notify_is_surfaced(tmp_path: Path) -> None:
    """Human notifications are shown regardless of any (now-removed) notification_key."""
    anima_dir = _anima_dir(tmp_path)
    body = "Please check deployment."
    _write_activity(
        anima_dir,
        [
            {
                "ts": now_iso(),
                "type": "human_notify",
                "content": body,
                "via": "slack",
            }
        ],
    )

    result = await PrimingEngine(anima_dir)._collect_pending_human_notifications(channel="chat")

    assert "Please check deployment" in result


@pytest.mark.asyncio
async def test_human_notify_surfaces_with_subject_body_key_meta(tmp_path: Path) -> None:
    """Human notifications render subject when present."""
    anima_dir = _anima_dir(tmp_path)
    subject = "Deploy check"
    body = "Please check deployment."
    notification_key_for(subject, body)
    _write_activity(
        anima_dir,
        [
            {
                "ts": now_iso(),
                "type": "human_notify",
                "content": body,
                "via": "configured_channels",
                "meta": {"subject": subject},
            }
        ],
    )

    result = await PrimingEngine(anima_dir)._collect_pending_human_notifications(channel="chat")

    assert "Deploy check" in result


@pytest.mark.asyncio
async def test_human_notify_allows_new_body(tmp_path: Path) -> None:
    anima_dir = _anima_dir(tmp_path)
    _write_activity(
        anima_dir,
        [
            {
                "ts": now_iso(),
                "type": "human_notify",
                "content": "new body",
                "via": "slack",
            }
        ],
    )

    result = await PrimingEngine(anima_dir)._collect_pending_human_notifications(channel="chat")

    assert "new body" in result


@pytest.mark.asyncio
async def test_human_notify_surfaces_without_taskboard_db(tmp_path: Path) -> None:
    anima_dir = _anima_dir(tmp_path)
    _write_activity(
        anima_dir,
        [
            {
                "ts": now_iso(),
                "type": "human_notify",
                "content": "surface despite no taskboard db",
                "via": "slack",
            }
        ],
    )

    result = await PrimingEngine(anima_dir)._collect_pending_human_notifications(channel="chat")

    assert "surface despite no taskboard db" in result
