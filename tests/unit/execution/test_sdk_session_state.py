"""Tests for durable SDK session context metadata."""

from __future__ import annotations

import json
from pathlib import Path

from core.execution._sdk_session import (
    _load_session_id,
    _save_session_id,
    load_session_state,
    record_session_measurement,
)


def test_loads_legacy_session_file(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "current_session_chat.json").write_text(
        json.dumps({"session_id": "legacy", "timestamp": "2026-09-23T11:12:50+00:00"}),
        encoding="utf-8",
    )

    state = load_session_state(tmp_path, "chat")

    assert state is not None
    assert state.session_id == "legacy"
    assert state.created_at == "2026-09-23T11:12:50+00:00"
    assert state.baseline_tokens == 0
    assert _load_session_id(tmp_path, "chat") == "legacy"


def test_record_measurement_only_seeds_baseline_once(tmp_path: Path) -> None:
    first = record_session_measurement(
        tmp_path,
        tokens=30_000,
        ratio=0.15,
        model="claude-fable-5",
        session_id="session-1",
        baseline_tokens=30_000,
    )
    second = record_session_measurement(
        tmp_path,
        tokens=150_000,
        ratio=0.75,
        model="claude-fable-5",
        session_id="session-1",
        baseline_tokens=150_000,
    )

    assert first.baseline_tokens == 30_000
    assert second.baseline_tokens == 30_000
    assert second.last_tokens == 150_000
    assert second.last_ratio == 0.75
    assert load_session_state(tmp_path, "chat").baseline_tokens == 30_000  # type: ignore[union-attr]


def test_measurement_write_is_atomic_and_corrupt_read_is_safe(tmp_path: Path) -> None:
    record_session_measurement(tmp_path, tokens=10, ratio=0.01, session_id="s")
    state_file = tmp_path / "state" / "current_session_chat.json"
    assert state_file.exists()
    assert not list(state_file.parent.glob(".*.tmp"))

    state_file.write_text("{not json", encoding="utf-8")
    assert load_session_state(tmp_path, "chat") is None
    assert _load_session_id(tmp_path, "chat") is None


def test_save_session_id_preserves_measurements(tmp_path: Path) -> None:
    record_session_measurement(tmp_path, tokens=30_000, ratio=0.15, session_id="old")
    before = load_session_state(tmp_path, "chat")
    _save_session_id(tmp_path, "new", "chat")

    state = load_session_state(tmp_path, "chat")
    assert state is not None
    assert state.session_id == "new"
    assert state.baseline_tokens == 30_000
    assert before is not None
    assert state.created_at == before.created_at
