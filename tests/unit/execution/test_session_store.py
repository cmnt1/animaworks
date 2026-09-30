from __future__ import annotations

import json
from pathlib import Path

from core.execution.engines.claude._sdk_session import _save_session_id
from core.execution.session.session_ids import EngineSessionIds
from core.execution.session.session_store import SessionRecord, SessionStore


def test_engine_session_paths_keep_existing_layouts(tmp_path: Path) -> None:
    cases = [
        ("agent_sdk", "chat", "default", tmp_path / "state/current_session_chat.json"),
        ("agent_sdk", "inbox", "thread-a", tmp_path / "state/current_session_inbox_thread-a.json"),
        ("codex", "chat", "default", tmp_path / "shortterm/chat/codex_thread_id.txt"),
        ("codex", "inbox", "thread-a", tmp_path / "shortterm/inbox/thread-a/codex_thread_id.txt"),
        ("cursor", "chat", "default", tmp_path / "shortterm/chat/cursor_chat_id.txt"),
        ("cursor", "chat", "thread-a", tmp_path / "shortterm/chat/thread-a/cursor_chat_id.txt"),
        ("grok", "chat", "default", tmp_path / "shortterm/chat/default/grok_session_id.txt"),
        ("grok", "chat", "thread-a", tmp_path / "shortterm/chat/thread-a/grok_session_id.txt"),
    ]

    for engine, session_type, thread_id, expected in cases:
        assert EngineSessionIds(engine).path_for(tmp_path, session_type, thread_id) == expected
        assert SessionStore.path_for(engine, tmp_path, session_type, thread_id) == expected


def test_engine_session_ids_keep_established_file_formats(tmp_path: Path) -> None:
    sdk_ids = EngineSessionIds("agent_sdk")
    _save_session_id(tmp_path, "claude-session", "chat")
    sdk_path = sdk_ids.path_for(tmp_path, "chat")
    sdk_data = json.loads(sdk_path.read_text(encoding="utf-8"))
    assert sdk_data["session_id"] == "claude-session"
    assert sdk_path.read_bytes().endswith(b"\n")
    assert sdk_ids.load_state(tmp_path, "chat")["session_id"] == "claude-session"  # type: ignore[index]

    codex_ids = EngineSessionIds("codex")
    codex_ids.save(tmp_path, "codex-thread", "chat")
    codex_path = codex_ids.path_for(tmp_path, "chat")
    assert codex_path.read_text(encoding="utf-8") == "codex-thread"
    assert codex_ids.load(tmp_path, "chat") == SessionRecord("codex-thread")

    cursor_ids = EngineSessionIds("cursor")
    cursor_ids.save(tmp_path, "cursor-session", "chat", turn_count=3)
    cursor_path = cursor_ids.path_for(tmp_path, "chat")
    assert cursor_path.read_text(encoding="utf-8") == "cursor-session\n3"
    assert cursor_ids.load(tmp_path, "chat") == SessionRecord("cursor-session", 3)

    grok_ids = EngineSessionIds("grok")
    grok_ids.save(tmp_path, "grok-session", "chat", turn_count=4)
    grok_path = grok_ids.path_for(tmp_path, "chat")
    assert grok_path.read_text(encoding="utf-8") == "grok-session\n4"
    assert grok_ids.load(tmp_path, "chat") == SessionRecord("grok-session", 4)

    for ids, path in ((codex_ids, codex_path), (cursor_ids, cursor_path), (grok_ids, grok_path)):
        ids.clear(tmp_path, "chat")
        assert not path.exists()


def test_text_records_retain_legacy_turn_count_behavior(tmp_path: Path) -> None:
    path = tmp_path / "session.txt"
    store = SessionStore(path)

    store.write_text_record(SessionRecord("legacy-session"), with_turn_count=True)
    assert store.read_text_record(with_turn_count=True) == SessionRecord("legacy-session", 0)

    path.write_text("session\nnot-a-number", encoding="utf-8")
    assert store.read_text_record(with_turn_count=True) == SessionRecord("session", 0)


def test_rotation_conditions_preserve_engine_boundaries() -> None:
    assert SessionStore.turn_limit_reached(10, 10)
    assert not SessionStore.turn_limit_reached(9, 10)
    assert SessionStore.prompt_size_exceeded(50_001, 50_000)
    assert not SessionStore.prompt_size_exceeded(50_000, 50_000)
