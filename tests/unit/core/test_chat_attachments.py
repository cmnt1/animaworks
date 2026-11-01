# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.anima import chat_attachments
from core.anima.chat_attachments import (
    MAX_OUTBOUND_FILE_COUNT,
    MAX_OUTBOUND_FILE_SIZE,
    collect_outbound_files,
    guess_media_type,
    stage_outbound_file,
)
from core.execution.session.session_context import RuntimeSessionContext
from core.tooling.handler import ToolHandler


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    path = tmp_path / "animas" / "test-anima"
    path.mkdir(parents=True)
    (path / "permissions.md").write_text("", encoding="utf-8")
    return path


def _new_handler(anima_dir: Path) -> ToolHandler:
    memory = MagicMock()
    memory.read_permissions.return_value = ""
    memory.search_memory_text.return_value = []
    return ToolHandler(anima_dir=anima_dir, memory=memory, messenger=None, tool_registry=[])


def _session(trigger: str = "message:human") -> RuntimeSessionContext:
    return RuntimeSessionContext(
        request_id="req-1",
        session_type="chat",
        thread_id="default",
        trigger=trigger,
        tool_session_id="tool-1",
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("report.md", "text/markdown"),
        ("data.csv", "text/csv"),
        ("data.json", "application/json"),
        ("sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("voice.m4a", "audio/mp4"),
        ("clip.mov", "video/quicktime"),
        ("unknown.bin", "application/octet-stream"),
    ],
)
def test_guess_media_type(path: str, expected: str) -> None:
    assert guess_media_type(path) == expected


def test_stage_and_collect_outbound_file(anima_dir: Path) -> None:
    source = anima_dir / "workspace" / "report.md"
    source.parent.mkdir()
    source.write_text("# report\n", encoding="utf-8")

    record = stage_outbound_file(
        anima_dir,
        source,
        display_name="final report.md",
        request_id="req-1",
        thread_id="default",
    )

    assert record["name"] == "final report.md"
    assert record["path"].startswith("attachments/")
    assert record["size"] == source.stat().st_size
    assert record["media_type"] == "text/markdown"
    assert (anima_dir / record["path"]).read_text(encoding="utf-8") == "# report\n"

    files = collect_outbound_files(anima_dir, "req-1")

    assert files == [
        {
            "name": "final report.md",
            "path": record["path"],
            "size": source.stat().st_size,
            "media_type": "text/markdown",
        }
    ]
    assert collect_outbound_files(anima_dir, "req-1") == []


def test_collect_does_not_mix_request_ids(anima_dir: Path) -> None:
    source = anima_dir / "note.txt"
    source.write_text("note", encoding="utf-8")
    stage_outbound_file(anima_dir, source, display_name=None, request_id="req-1", thread_id="default")

    assert collect_outbound_files(anima_dir, "req-2") == []
    assert [file["name"] for file in collect_outbound_files(anima_dir, "req-1")] == ["note.txt"]


def test_collect_takes_same_thread_files_staged_under_another_request_id(anima_dir: Path) -> None:
    source = anima_dir / "note.txt"
    source.write_text("note", encoding="utf-8")
    stage_outbound_file(anima_dir, source, display_name="old.txt", request_id="stale", thread_id="default")
    since = "9999-01-01T00:00:00+09:00"
    # Staged before this reply started: left alone.
    assert collect_outbound_files(anima_dir, "reply", thread_id="default", since=since) == []

    stage_outbound_file(anima_dir, source, display_name="mine.txt", request_id="stale", thread_id="default")
    stage_outbound_file(anima_dir, source, display_name="other.txt", request_id="stale", thread_id="t2")
    files = collect_outbound_files(anima_dir, "reply", thread_id="default", since="2000-01-01T00:00:00+09:00")
    assert sorted(file["name"] for file in files) == ["mine.txt", "old.txt"]
    # The other thread's file stays for its own reply.
    assert [file["name"] for file in collect_outbound_files(anima_dir, "stale")] == ["other.txt"]


def test_stage_rejects_file_over_100mb(anima_dir: Path) -> None:
    large = anima_dir / "large.bin"
    large.write_bytes(b"")
    os.truncate(large, MAX_OUTBOUND_FILE_SIZE + 1)

    with pytest.raises(ValueError):
        stage_outbound_file(anima_dir, large, display_name=None, request_id="req-1", thread_id="default")


def test_stage_rejects_empty_and_oversized_file(anima_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = anima_dir / "empty.txt"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        stage_outbound_file(anima_dir, empty, display_name=None, request_id="req-1", thread_id="default")

    large = anima_dir / "large.txt"
    large.write_text("too large", encoding="utf-8")
    monkeypatch.setattr(chat_attachments, "MAX_OUTBOUND_FILE_SIZE", 4)
    with pytest.raises(ValueError):
        stage_outbound_file(anima_dir, large, display_name=None, request_id="req-1", thread_id="default")


def test_stage_enforces_per_reply_file_count(anima_dir: Path) -> None:
    source = anima_dir / "note.txt"
    source.write_text("note", encoding="utf-8")

    for index in range(MAX_OUTBOUND_FILE_COUNT):
        stage_outbound_file(
            anima_dir,
            source,
            display_name=f"note-{index}.txt",
            request_id="req-1",
            thread_id="default",
        )

    with pytest.raises(ValueError, match=str(MAX_OUTBOUND_FILE_COUNT)):
        stage_outbound_file(anima_dir, source, display_name=None, request_id="req-1", thread_id="default")


def test_collect_removes_stale_records(anima_dir: Path) -> None:
    source = anima_dir / "note.txt"
    source.write_text("note", encoding="utf-8")
    stage_outbound_file(anima_dir, source, display_name=None, request_id="old-request", thread_id="default")
    record_path = chat_attachments._record_path(anima_dir, "old-request")
    old = chat_attachments.time.time() - chat_attachments._OUTBOUND_RECORD_RETENTION_SECONDS - 60
    os.utime(record_path, (old, old))

    assert collect_outbound_files(anima_dir, "new-request") == []
    assert not record_path.exists()


def test_attach_file_handler_stages_file_for_message_reply(anima_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _new_handler(anima_dir)
    monkeypatch.setattr(handler, "_check_file_permission", lambda _path: None)
    handler._runtime_session_context = _session()
    source = anima_dir / "workspace" / "report.md"
    source.parent.mkdir()
    source.write_text("# report\n", encoding="utf-8")

    raw = handler._handle_attach_file({"path": str(source), "name": "summary.md"})
    payload = json.loads(raw)

    assert payload["status"] == "ok"
    assert payload["attached"]["name"] == "summary.md"
    assert collect_outbound_files(anima_dir, "req-1")[0]["name"] == "summary.md"


def test_attach_file_handler_resolves_relative_path(anima_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _new_handler(anima_dir)
    monkeypatch.setattr(handler, "_check_file_permission", lambda _path: None)
    handler._runtime_session_context = _session()
    source = anima_dir / "workspace" / "report.md"
    source.parent.mkdir()
    source.write_text("# report\n", encoding="utf-8")

    payload = json.loads(handler._handle_attach_file({"path": "workspace/report.md"}))

    assert payload["status"] == "ok"
    assert payload["attached"]["path"].endswith("_a1_report.md")


def test_attach_file_handler_returns_permission_error(anima_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _new_handler(anima_dir)
    monkeypatch.setattr(handler, "_check_file_permission", lambda _path: "permission denied")
    handler._runtime_session_context = _session()
    source = anima_dir / "report.md"
    source.write_text("# report\n", encoding="utf-8")

    assert handler._handle_attach_file({"path": str(source)}) == "permission denied"


def test_attach_file_handler_rejects_directory(anima_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _new_handler(anima_dir)
    monkeypatch.setattr(handler, "_check_file_permission", lambda _path: None)
    handler._runtime_session_context = _session()
    directory = anima_dir / "workspace"
    directory.mkdir()

    payload = json.loads(handler._handle_attach_file({"path": str(directory)}))

    assert payload["status"] == "error"
    assert payload["error_type"] == "FileNotFound"


def test_attach_file_handler_rejects_non_chat_trigger(anima_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _new_handler(anima_dir)
    monkeypatch.setattr(handler, "_check_file_permission", lambda _path: None)
    handler._runtime_session_context = _session("heartbeat")
    source = anima_dir / "report.md"
    source.write_text("# report\n", encoding="utf-8")

    payload = json.loads(handler._handle_attach_file({"path": str(source)}))

    assert payload["status"] == "error"
    assert payload["error_type"] == "ToolBlocked"


def test_attach_file_handler_requires_path_and_existing_file(anima_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _new_handler(anima_dir)
    monkeypatch.setattr(handler, "_check_file_permission", lambda _path: None)
    handler._runtime_session_context = _session()

    missing_arg = json.loads(handler._handle_attach_file({}))
    assert missing_arg["error_type"] == "InvalidArguments"

    missing_file = json.loads(handler._handle_attach_file({"path": str(anima_dir / "nope.txt")}))
    assert missing_file["error_type"] == "FileNotFound"


def test_attach_file_handler_requires_runtime_session(anima_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.tooling import handler_chat_files

    handler = _new_handler(anima_dir)
    monkeypatch.setattr(handler, "_check_file_permission", lambda _path: None)
    monkeypatch.setattr(handler_chat_files, "current_runtime_session", lambda: None)
    handler._runtime_session_context = None
    source = anima_dir / "report.md"
    source.write_text("# report\n", encoding="utf-8")

    payload = json.loads(handler._handle_attach_file({"path": str(source)}))

    assert payload["status"] == "error"
    assert payload["error_type"] == "ToolBlocked"
