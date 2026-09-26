from __future__ import annotations

import json
from pathlib import Path

from core.execution.engines.claude._sdk_session import _save_session_id, _session_state_path
from core.execution.engines.codex.codex_sdk import _save_thread_id, _thread_id_path
from core.execution.engines.cursor.cursor_agent import _chat_id_path, _save_chat_id
from core.execution.engines.grok.grok_cli import _save_session_id as _save_grok_session_id
from core.execution.engines.grok.grok_cli import _session_id_path as _grok_session_id_path
from core.execution.session_store import SessionRecord, SessionStore


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
        assert SessionStore.path_for(engine, tmp_path, session_type, thread_id) == expected

    assert _session_state_path(tmp_path, "chat", "default") == cases[0][3]
    assert _session_state_path(tmp_path, "inbox", "thread-a") == cases[1][3]
    assert _thread_id_path(tmp_path, "chat", "default") == cases[2][3]
    assert _thread_id_path(tmp_path, "inbox", "thread-a") == cases[3][3]
    assert _chat_id_path(tmp_path, "chat", "default") == cases[4][3]
    assert _chat_id_path(tmp_path, "chat", "thread-a") == cases[5][3]
    assert _grok_session_id_path(tmp_path, "chat", "default") == cases[6][3]
    assert _grok_session_id_path(tmp_path, "chat", "thread-a") == cases[7][3]


def test_existing_engine_helpers_keep_session_file_formats(tmp_path: Path) -> None:
    _save_session_id(tmp_path, "claude-session", "chat")
    claude_path = tmp_path / "state/current_session_chat.json"
    claude_data = json.loads(claude_path.read_text(encoding="utf-8"))
    assert claude_data["session_id"] == "claude-session"
    assert claude_path.read_bytes().endswith(b"\n")

    _save_thread_id(tmp_path, "codex-thread", "chat")
    assert (tmp_path / "shortterm/chat/codex_thread_id.txt").read_text(encoding="utf-8") == "codex-thread"

    _save_chat_id(tmp_path, "cursor-session", "chat", turn_count=3)
    assert (tmp_path / "shortterm/chat/cursor_chat_id.txt").read_text(encoding="utf-8") == "cursor-session\n3"

    _save_grok_session_id(tmp_path, "grok-session", "chat", turn_count=4)
    assert (tmp_path / "shortterm/chat/default/grok_session_id.txt").read_text(encoding="utf-8") == "grok-session\n4"


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
