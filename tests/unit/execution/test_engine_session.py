from __future__ import annotations

from pathlib import Path

import pytest

from core.execution.engine_session import (
    MAX_RESUME_TURNS,
    ResumeDecision,
    clear_all_engine_sessions,
    clear_engine_session,
    load_turn_limited_session,
    next_turn_count,
)
from core.execution.session_store import SessionEngine, SessionRecord, SessionStore
from core.execution.session_types import (
    RESUMABLE_SESSION_TYPES,
    is_resumable_trigger,
    resolve_runtime_session_type,
)


@pytest.mark.parametrize(
    ("trigger", "expected"),
    [
        ("", "chat"),
        ("chat", "chat"),
        ("chat:web", "chat"),
        ("message", "chat"),
        ("message:foo", "chat"),
        ("manual", "chat"),
        ("greet:user", "chat"),
        ("heartbeat", "heartbeat"),
        ("heartbeat:x", "heartbeat"),
        ("consolidation:nightly", "heartbeat"),
        ("cron:daily", "cron"),
        ("task:work", "task"),
        ("inbox", "inbox"),
        ("inbox:foo", "inbox"),
        ("unknown", "task"),
    ],
)
def test_resolve_runtime_session_type(trigger: str, expected: str) -> None:
    assert resolve_runtime_session_type(trigger) == expected


def test_resumable_triggers() -> None:
    assert frozenset({"chat"}) == RESUMABLE_SESSION_TYPES
    for trigger in ("message:foo", "chat", ""):
        assert is_resumable_trigger(trigger) is True
    for trigger in ("heartbeat", "cron:x", "task:x", "inbox:x"):
        assert is_resumable_trigger(trigger) is False


@pytest.mark.parametrize("engine", ["agent_sdk", "codex", "cursor", "grok"])
def test_clear_engine_session_uses_engine_store(tmp_path: Path, engine: SessionEngine) -> None:
    path = SessionStore.path_for(engine, tmp_path, "chat", "thread-a")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("session-id", encoding="utf-8")

    clear_engine_session(tmp_path, engine, "chat", "thread-a")

    assert not path.exists()


def test_clear_all_engine_sessions_clears_all_engines(tmp_path: Path) -> None:
    paths = [
        SessionStore.path_for(engine, tmp_path, "task", "thread-a")
        for engine in ("agent_sdk", "codex", "cursor", "grok")
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("session-id", encoding="utf-8")

    clear_all_engine_sessions(tmp_path, "task", "thread-a")

    assert all(not path.exists() for path in paths)


@pytest.mark.parametrize("engine", ["cursor", "grok"])
def test_load_turn_limited_session_rotates_at_limit(tmp_path: Path, engine: SessionEngine) -> None:
    path = SessionStore.path_for(engine, tmp_path, "chat", "thread-a")
    SessionStore(path).write_text_record(SessionRecord("session-id", MAX_RESUME_TURNS), with_turn_count=True)

    decision = load_turn_limited_session(tmp_path, engine, "chat", "thread-a")

    assert decision.session_id is None
    assert decision.turn_count == 0
    assert decision.resumable is True
    assert decision.rotated is True
    assert not path.exists()


def test_load_turn_limited_session_ignores_non_resumable_trigger(tmp_path: Path) -> None:
    path = SessionStore.path_for("grok", tmp_path, "heartbeat", "thread-a")
    SessionStore(path).write_text_record(SessionRecord("heartbeat-session", 2), with_turn_count=True)

    decision = load_turn_limited_session(tmp_path, "grok", "heartbeat", "thread-a")

    assert decision.session_id is None
    assert decision.turn_count == 0
    assert decision.resumable is False
    assert decision.rotated is False
    assert path.exists()


@pytest.mark.parametrize(
    ("decision", "resumed", "rotated_during_run", "expected"),
    [
        (ResumeDecision("session", 8, True, False), True, False, (9, False)),
        (ResumeDecision("session", 9, True, False), True, False, (10, True)),
        (ResumeDecision(None, 0, True, True), False, False, (1, False)),
        (ResumeDecision("session", 4, True, False), True, True, (1, False)),
        (ResumeDecision(None, 0, False, False), False, False, (1, False)),
    ],
)
def test_next_turn_count(
    decision: ResumeDecision,
    resumed: bool,
    rotated_during_run: bool,
    expected: tuple[int, bool],
) -> None:
    assert next_turn_count(decision, resumed=resumed, rotated_during_run=rotated_during_run) == expected
