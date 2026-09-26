"""Unit + golden tests for core/memory/activity_format shared helpers."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.memory.activity.format import (
    EVENT_SETS,
    EntryRole,
    clip,
    entry_role,
    entry_text,
    iter_entries,
    pair_tool_events,
)
from core.memory.activity.models import ActivityEntry
from core.time_utils import now_local


def _entry(
    etype: str,
    content: str = "",
    summary: str = "",
    ts: str = "2026-01-01T00:00:00+09:00",
    **kw: object,
) -> ActivityEntry:
    return ActivityEntry(
        ts=ts,
        type=etype,
        content=content,
        summary=summary,
        **kw,
    )


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "t-anima"
    (d / "activity_log").mkdir(parents=True)
    return d


def _write_entries(log_dir: Path, rows: list[dict]) -> None:
    path = log_dir / "activity_log" / f"{now_local().date().isoformat()}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ── entry_text ───────────────────────────────────────────────


def test_entry_text_prefers_content():
    e = _entry("message_received", content="body", summary="summary")
    assert entry_text(e) == "body"


def test_entry_text_falls_back_to_summary():
    e = _entry("message_received", content="", summary="summary")
    assert entry_text(e) == "summary"


def test_entry_text_empty():
    e = _entry("message_received")
    assert entry_text(e) == ""


# ── entry_role ──────────────────────────────────────────────


def test_entry_role_human_received_is_user():
    assert entry_role(_entry("message_received", from_person="human")) == EntryRole.USER


def test_entry_role_anima_received_is_assistant():
    e = _entry("message_received", meta={"from_type": "anima"})
    assert entry_role(e) == EntryRole.ASSISTANT


def test_entry_role_response_is_assistant():
    assert entry_role(_entry("response_sent")) == EntryRole.ASSISTANT


def test_entry_role_system_types():
    for t in ("heartbeat_start", "heartbeat_end", "cron_executed", "error", "human_notify"):
        assert entry_role(_entry(t)) == EntryRole.SYSTEM, t


def test_entry_role_tool():
    assert entry_role(_entry("tool_use")) == EntryRole.TOOL


def test_entry_role_unknown_returns_none():
    assert entry_role(_entry("mystery")) is None


# ── clip ────────────────────────────────────────────────────


def test_clip_short_passthrough():
    assert clip("abc", 10) == "abc"


def test_clip_truncates():
    assert clip("abcdef", 3) == "abc"


def test_clip_nonpositive():
    assert clip("abc", 0) == ""


# ── EVENT_SETS ──────────────────────────────────────────────


def test_event_sets_are_frozen():
    assert all(isinstance(v, frozenset) for v in EVENT_SETS.values())


def test_audit_set_excludes_raw_tool_result():
    assert "tool_use" in EVENT_SETS["audit"]
    assert "tool_result" not in EVENT_SETS["audit"]


# ── pair_tool_events ───────────────────────────────────────


def test_pair_matches_by_tool_use_id():
    use = _entry("tool_use", tool="read", meta={"tool_use_id": "t1", "args": {}})
    result = _entry("tool_result", tool="read", meta={"tool_use_id": "t1"})
    pairs = pair_tool_events([use, result])
    assert len(pairs) == 1
    assert pairs[0].tool_use is use
    assert pairs[0].result is result


def test_pair_uses_fallback_for_unmatched():
    use = _entry("tool_use", tool="search", meta={"args": {}}, ts="2026-01-01T10:00:00+09:00")
    result = _entry("tool_result", tool="search", ts="2026-01-01T10:00:10+09:00")
    exchanges = pair_tool_events([use, result])
    assert len(exchanges) == 1
    # timestamp proximity + tool name fallback matches within 300s
    assert exchanges[0].result is result


def test_pair_returns_none_result_when_no_match():
    use = _entry("tool_use", tool="read", meta={"tool_use_id": "z"})
    other = _entry("tool_result", tool="write", meta={"tool_use_id": "q"})
    exchanges = pair_tool_events([use, other])
    assert exchanges[0].result is None


# ── iter_entries (golden through ActivityLogger) ───────────


def _default_row(etype: str, ts: str = "2026-01-01T09:00:00+09:00", **kw: object) -> dict:
    return {"ts": ts, "type": etype, "content": "", "summary": "", **kw}


def test_iter_entries_reads_and_filters(log_dir: Path):
    _write_entries(
        log_dir,
        [
            _default_row("message_received", content="hi", meta={"thread_id": "default", "from_type": "human"}),
            _default_row("response_sent", content="hello"),
            _default_row("tool_use", tool="read", meta={"tool_use_id": "x", "args": {}}),
            _default_row("heartbeat_start"),
        ],
    )
    got = list(iter_entries(log_dir, days=2, types=["message_received", "response_sent"]))
    assert [e.type for e in got] == ["message_received", "response_sent"]
    assert got[0].content == "hi"


# ── Golden: session_compactor extraction through iter_entries ─


def test_compaction_extraction_golden(log_dir: Path):
    """The migrated compaction path must yield identical structure."""
    from core.agent.session_compactor import _extract_recent_chat_context

    _write_entries(
        log_dir,
        [
            _default_row(
                "message_received",
                ts="2026-01-01T09:00:00+09:00",
                content="user q1",
                meta={"thread_id": "default", "from_type": "human"},
            ),
            _default_row(
                "response_sent",
                ts="2026-01-01T09:00:05+09:00",
                content="anima a1",
            ),
            _default_row(
                "tool_use",
                ts="2026-01-01T09:00:10+09:00",
                tool="read",
                meta={"tool_use_id": "t1", "args": {"path": "/x"}, "thread_id": "default"},
            ),
            _default_row(
                "tool_result",
                ts="2026-01-01T09:00:20+09:00",
                content="file body",
                meta={"tool_use_id": "t1", "thread_id": "default"},
            ),
            _default_row(
                "message_received",
                ts="2026-01-01T09:30:00+09:00",
                content="user q2",
                meta={"thread_id": "default", "from_type": "human"},
            ),
            # A different thread must be ignored.
            _default_row(
                "message_received",
                ts="2026-01-01T09:40:00+09:00",
                content="other thread",
                meta={"thread_id": "other", "from_type": "human"},
            ),
            # inbox entry must be ignored.
            _default_row(
                "message_received",
                ts="2026-01-01T09:50:00+09:00",
                content="inbox msg",
                meta={"session_type": "inbox", "thread_id": "default", "from_type": "human"},
            ),
        ],
    )
    ctx = _extract_recent_chat_context(log_dir, thread_id="default")

    assert "user: user q2" in ctx["accumulated_response"]
    assert "user: user q1" in ctx["accumulated_response"]
    assert "assistant: anima a1" in ctx["accumulated_response"]
    assert ctx["original_prompt"] == "user q1"
    assert len(ctx["tool_uses"]) == 1
    tool = ctx["tool_uses"][0]
    assert tool["name"] == "read"
    assert tool["result"] == "file body"
    assert "tool_use_id" not in tool
    assert "other thread" not in ctx["accumulated_response"]
    assert "inbox msg" not in ctx["accumulated_response"]


# ── entry_text prefer / dict support ───────────────────────


def test_entry_text_prefer_summary():
    e = _entry("message_received", content="body", summary="s")
    assert entry_text(e, prefer="summary") == "s"
    assert entry_text(e, prefer="content") == "body"


def test_entry_text_prefer_summary_falls_back_to_content():
    e = _entry("message_received", content="body")
    assert entry_text(e, prefer="summary") == "body"


def test_entry_text_accepts_dict():
    assert entry_text({"type": "response_sent", "content": "body", "summary": "s"}) == "body"
    assert entry_text({"type": "response_sent", "summary": "s"}, prefer="summary") == "s"
    assert entry_text({"type": "response_sent"}) == ""


# ── Golden: audit._extract_content (pre/post identical) ────


def test_audit_extract_content_golden():
    from core.memory.activity.audit import AuditAggregator

    fx = AuditAggregator._extract_content
    long = "x" * 400

    assert fx(_entry("heartbeat_end", summary="sum")) == "sum"
    assert fx(_entry("response_sent", content=long)) == "x" * 300
    assert fx(_entry("cron_executed", content=long)) == "x" * 400  # trunc 500
    assert fx(_entry("tool_use", tool="read", content="detail")) == "read: detail"
    assert fx(_entry("tool_use", tool="read")) == "read"
    assert fx(_entry("error", summary="boom", meta={"phase": "load"})) == "(phase: load) boom"
    assert fx(_entry("error", content=long, meta={"phase": "run"})) == "(phase: run) " + "x" * 100
    assert fx(_entry("message_received", summary="sum")) == "sum"
    assert fx(_entry("mystery", content=long)) == "x" * 300


# ── Golden: conversation_finalize context extraction ───────


def test_gather_activity_context_golden(log_dir: Path):
    from core.memory.conversation.finalize import _gather_activity_context
    from core.memory.conversation.models import ConversationTurn

    _write_entries(
        log_dir,
        [
            _default_row("message_sent", ts="2026-01-01T10:00:00+09:00", summary="hello anima"),
            _default_row("cron_executed", ts="2026-01-01T10:01:00+09:00", content="x" * 150),
            _default_row("response_sent", ts="2026-01-01T10:02:00+09:00", content="not in types"),
            _default_row("message_received", ts="2026-01-01T10:03:00+09:00", summary="from human"),
            _default_row("message_sent", ts="2026-01-01T13:00:00+09:00", summary="outside window"),
        ],
    )
    turns = [
        ConversationTurn(role="human", content="q", timestamp="2026-01-01T09:00:00+09:00"),
        ConversationTurn(role="assistant", content="a", timestamp="2026-01-01T12:00:00+09:00"),
    ]
    out = _gather_activity_context(log_dir, turns)
    assert out == (
        "## セッション中のその他の活動\n"
        "- [message_sent] hello anima\n"
        "- [cron_executed] " + "x" * 100 + "\n"
        "- [message_received] from human"
    )


# ── Golden: distillation cluster prompt formatting ─────────


def test_distillation_format_clusters_golden():
    from core.memory.maintenance.distillation import ProceduralDistiller

    clusters = [
        [
            {"ts": "2026-01-01T10:00:00+09:00", "type": "tool_use", "tool": "read", "summary": "did read file"},
            {"ts": "2026-01-01T10:01:00+09:00", "type": "message_sent", "content": "plain act"},
        ]
    ]
    out = ProceduralDistiller._format_clusters_for_prompt(clusters)
    assert "### パターン 1 (2回繰り返し)" in out
    assert "- 2026-01-01T10:00 tool_use [tool: read]: did read file" in out
    assert "- 2026-01-01T10:01 message_sent: plain act" in out
