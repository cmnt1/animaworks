"""Tests for the disk-backed idle compaction sweep."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.session_compactor import SessionCompactor


def _write_session(anima_dir: Path, thread_id: str, *, session_id: str = "session") -> None:
    filename = "current_session_chat.json" if thread_id == "default" else f"current_session_chat_{thread_id}.json"
    old = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
    state_dir = anima_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / filename).write_text(
        json.dumps(
            {
                "session_id": session_id,
                "timestamp": old,
                "created_at": old,
                "updated_at": old,
                "baseline_tokens": 10,
                "last_tokens": 20,
                "last_ratio": 0.1,
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_sweep_compacts_old_threads_only(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    _write_session(anima_dir, "default")
    _write_session(anima_dir, "old-thread")
    anima = SimpleNamespace(anima_dir=anima_dir, name="test")
    compactor = SessionCompactor(idle_minutes=10)

    with patch("core.session_compactor.run_idle_compaction", new_callable=AsyncMock) as compact:
        await compactor._sweep_once(anima)

    assert {call.args[1] for call in compact.await_args_list} == {"default", "old-thread"}


@pytest.mark.asyncio
async def test_sweep_skips_threads_without_a_session_id(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    _write_session(anima_dir, "default", session_id="")
    anima = SimpleNamespace(anima_dir=anima_dir, name="test")
    compactor = SessionCompactor(idle_minutes=10)

    with patch("core.session_compactor.run_idle_compaction", new_callable=AsyncMock) as compact:
        await compactor._sweep_once(anima)

    compact.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_continues_after_one_thread_fails(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    _write_session(anima_dir, "first")
    _write_session(anima_dir, "second")
    anima = SimpleNamespace(anima_dir=anima_dir, name="test")
    compactor = SessionCompactor(idle_minutes=10)
    compact = AsyncMock(side_effect=[RuntimeError("boom"), True])

    with patch("core.session_compactor.run_idle_compaction", compact):
        await compactor._sweep_once(anima)

    assert compact.await_count == 2


@pytest.mark.asyncio
async def test_sweep_does_not_recompact_the_same_measurement(tmp_path: Path) -> None:
    """Modes other than S keep the state file, so the sweep must mark it.

    Without the ``swept_at`` marker a stale Mode C/A session would be
    compacted again on every 60-second tick, burning an LLM call each time.
    """
    anima_dir = tmp_path / "anima"
    _write_session(anima_dir, "default")
    anima = SimpleNamespace(anima_dir=anima_dir, name="test")
    compactor = SessionCompactor(idle_minutes=10)
    compact = AsyncMock(return_value=True)

    with patch("core.session_compactor.run_idle_compaction", compact):
        await compactor._sweep_once(anima)
        await compactor._sweep_once(anima)
        await compactor._sweep_once(anima)

    assert compact.await_count == 1

    state_file = anima_dir / "state" / "current_session_chat.json"
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["swept_at"] == saved["updated_at"]


@pytest.mark.asyncio
async def test_sweep_fires_again_after_fresh_activity(tmp_path: Path) -> None:
    """A new measurement moves ``updated_at`` past the marker."""
    from core.execution._sdk_session import record_session_measurement

    anima_dir = tmp_path / "anima"
    _write_session(anima_dir, "default")
    anima = SimpleNamespace(anima_dir=anima_dir, name="test")
    compactor = SessionCompactor(idle_minutes=10)
    compact = AsyncMock(return_value=True)

    with patch("core.session_compactor.run_idle_compaction", compact):
        await compactor._sweep_once(anima)

        # Fresh activity, then let it go stale again.
        record_session_measurement(anima_dir, "chat", "default", tokens=500, ratio=0.2)
        state_file = anima_dir / "state" / "current_session_chat.json"
        saved = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved["swept_at"] < saved["updated_at"]
        saved["updated_at"] = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
        state_file.write_text(json.dumps(saved), encoding="utf-8")

        await compactor._sweep_once(anima)

    assert compact.await_count == 2
