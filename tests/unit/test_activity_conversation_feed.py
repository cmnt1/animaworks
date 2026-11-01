"""Tests for the compact user-centered conversation feed."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.activity.conversation import clear_conversation_feed_cache
from core.activity.logger import ActivityLogger
from core.time_utils import now_local
from server.routes.sessions import create_sessions_router


def _write_entries(anima_dir: Path, entries: list[dict]) -> Path:
    log_dir = anima_dir / "activity_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    day = entries[0]["ts"][:10]
    path = log_dir / f"{day}.jsonl"
    with path.open("a", encoding="utf-8") as file:
        for entry in entries:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def _event(ts: str, event_type: str, content: str = "", **fields: object) -> dict:
    return {"ts": ts, "type": event_type, "content": content, **fields}


def _test_activity(tmp_path: Path, name: str = "mei") -> tuple[Path, ActivityLogger]:
    anima_dir = tmp_path / "animas" / name
    (anima_dir / "activity_log").mkdir(parents=True)
    return anima_dir, ActivityLogger(anima_dir)


@pytest.fixture(autouse=True)
def clear_feed_cache() -> None:
    clear_conversation_feed_cache()
    yield
    clear_conversation_feed_cache()


def test_feed_finds_minimum_user_items_across_many_background_entries(tmp_path: Path) -> None:
    anima_dir, activity = _test_activity(tmp_path)
    now = now_local().replace(microsecond=0)
    entries: list[dict] = []
    for turn in range(14):
        start = now - timedelta(minutes=(14 - turn) * 3)
        for work in range(8):
            ts = (start + timedelta(seconds=work * 10)).isoformat()
            entries.append(
                _event(ts, "cron_executed", f"private cron body {turn}-{work}", meta={"task_name": "nightly"})
            )
        user_ts = (start + timedelta(seconds=90)).isoformat()
        entries.append(
            _event(
                user_ts,
                "message_received",
                f"question {turn}",
                from_person="human",
                channel="chat",
                meta={"from_type": "human", "thread_id": "default"},
            )
        )
    _write_entries(anima_dir, entries)

    feed = activity.get_conversation_feed(min_user_items=10, _schedule_prefetch=False)

    user_messages = [item["message"] for item in feed["items"] if item["kind"] == "message"]
    assert len(user_messages) >= 10
    assert all(message["role"] == "human" for message in user_messages)
    groups = [item for item in feed["items"] if item["kind"] == "bg_group"]
    assert groups
    assert all("content" not in group and "tool_calls" not in group for group in groups)
    assert feed["next_before"]


def test_file_metadata_is_exposed_by_feed_and_conversation_history(tmp_path: Path) -> None:
    anima_dir, activity = _test_activity(tmp_path)
    now = now_local().replace(microsecond=0)
    files = [
        {
            "name": "estimate.pdf",
            "path": "attachments/20261029_101500_0_estimate.pdf",
            "size": 42,
            "media_type": "application/pdf",
        }
    ]
    _write_entries(
        anima_dir,
        [
            _event(
                now.isoformat(),
                "message_received",
                "Please review",
                from_person="human",
                channel="chat",
                meta={"from_type": "human", "thread_id": "default", "files": files},
            )
        ],
    )

    history = activity.get_conversation_view(thread_id="default")
    history_messages = [message for session in history["sessions"] for message in session["messages"]]
    feed = activity.get_conversation_feed(min_user_items=1, _schedule_prefetch=False)
    feed_messages = [item["message"] for item in feed["items"] if item["kind"] == "message"]

    assert history_messages[0]["files"] == files
    assert feed_messages[0]["files"] == files


def test_assistant_file_metadata_is_exposed_by_feed_and_conversation_history(tmp_path: Path) -> None:
    anima_dir, activity = _test_activity(tmp_path)
    now = now_local().replace(microsecond=0)
    files = [
        {
            "name": "summary.md",
            "path": "attachments/20261029_101500_a1_summary.md",
            "size": 128,
            "media_type": "text/markdown",
        }
    ]
    _write_entries(
        anima_dir,
        [
            _event(
                now.isoformat(),
                "response_sent",
                "Here is the summary",
                to_person="human",
                channel="chat",
                meta={"thread_id": "default", "files": files},
            )
        ],
    )

    history = activity.get_conversation_view(thread_id="default")
    history_messages = [message for session in history["sessions"] for message in session["messages"]]
    feed = activity.get_conversation_feed(min_user_items=1, _schedule_prefetch=False)
    feed_messages = [item["message"] for item in feed["items"] if item["kind"] == "message"]

    assert history_messages[-1]["role"] == "assistant"
    assert history_messages[-1]["files"] == files
    assert feed_messages[-1]["files"] == files


def test_feed_coalesces_cron_dm_and_self_notice_without_leaking_bodies(tmp_path: Path) -> None:
    anima_dir, activity = _test_activity(tmp_path)
    (anima_dir.parent / "rin").mkdir()
    base = now_local().replace(microsecond=0) - timedelta(minutes=8)
    entries = [
        _event((base + timedelta(seconds=1)).isoformat(), "cron_executed", "cron secret"),
        _event((base + timedelta(seconds=2)).isoformat(), "cron_executed", "cron secret 2"),
        _event(
            (base + timedelta(seconds=3)).isoformat(),
            "message_sent",
            "dm secret",
            from_person="mei",
            to_person="rin",
            channel="chat",
        ),
        _event(
            (base + timedelta(seconds=4)).isoformat(),
            "message_received",
            "dm secret 2",
            from_person="rin",
            to_person="mei",
            channel="chat",
            meta={"from_type": "anima"},
        ),
        _event(
            (base + timedelta(seconds=5)).isoformat(),
            "message_sent",
            "self notice secret",
            from_person="mei",
            to_person="mei",
            channel="chat",
        ),
        _event(
            (base + timedelta(seconds=6)).isoformat(),
            "message_received",
            "visible human message",
            from_person="human",
            to_person="mei",
            channel="chat",
            meta={"from_type": "human"},
        ),
    ]
    _write_entries(anima_dir, entries)

    feed = activity.get_conversation_feed(min_user_items=10, _schedule_prefetch=False)

    assert len(feed["items"]) == 2
    first, last = feed["items"]
    assert first["kind"] == "bg_group"
    assert first["count"] == 5
    assert first["kinds"] == {"cron": 2, "dm": 2, "notice": 1}
    assert first["participants"] == ["rin"]
    assert "cron secret" not in json.dumps(first)
    assert "dm secret" not in json.dumps(first)
    assert last["kind"] == "message"


def test_user_item_rules_cover_external_humans_notifications_calls_and_direct_replies(tmp_path: Path) -> None:
    anima_dir, activity = _test_activity(tmp_path)
    (anima_dir.parent / "rin").mkdir()
    base = now_local().replace(microsecond=0) - timedelta(minutes=7)
    entries = [
        _event(
            (base + timedelta(seconds=1)).isoformat(),
            "message_received",
            "Slack from a person",
            from_person="slack-user",
            channel="slack",
            meta={"from_type": "slack"},
        ),
        _event(
            (base + timedelta(seconds=2)).isoformat(),
            "response_sent",
            "A direct reply",
            to_person="human",
            channel="chat",
        ),
        _event(
            (base + timedelta(seconds=3)).isoformat(),
            "response_sent",
            "Anima DM",
            to_person="rin",
            channel="chat",
        ),
        _event((base + timedelta(seconds=4)).isoformat(), "human_notify", "Approval needed"),
        _event(
            (base + timedelta(seconds=5)).isoformat(),
            "human_notify",
            "Private self notice",
            from_person="mei",
            to_person="mei",
        ),
        _event((base + timedelta(seconds=6)).isoformat(), "human_reply", "Approved", from_person="human"),
        _event(
            (base + timedelta(seconds=7)).isoformat(),
            "voice_call",
            "Call summary",
            summary="Call summary",
        ),
        _event(
            (base + timedelta(seconds=8)).isoformat(),
            "message_sent",
            "Self notice",
            from_person="mei",
            to_person="mei",
            channel="chat",
        ),
    ]
    _write_entries(anima_dir, entries)

    feed = activity.get_conversation_feed(min_user_items=10, _schedule_prefetch=False)
    user_texts = [item["message"].get("content") for item in feed["items"] if item["kind"] == "message"]

    assert user_texts == ["Slack from a person", "A direct reply", "Approval needed", "Approved", "Call summary"]
    bg_groups = [item for item in feed["items"] if item["kind"] == "bg_group"]
    assert bg_groups[0]["kinds"]["dm"] == 1
    assert bg_groups[0]["participants"] == ["rin"]
    assert bg_groups[-1]["kinds"]["notice"] == 1


def test_background_endpoint_returns_only_in_range_background_messages(tmp_path: Path) -> None:
    anima_dir, activity = _test_activity(tmp_path)
    base = now_local().replace(microsecond=0) - timedelta(minutes=5)
    cron_ts = (base + timedelta(seconds=2)).isoformat()
    user_ts = (base + timedelta(seconds=3)).isoformat()
    entries = [
        _event((base + timedelta(seconds=1)).isoformat(), "cron_executed", "before range"),
        _event(cron_ts, "cron_executed", "in range background"),
        _event(
            user_ts,
            "message_received",
            "in range human",
            from_person="human",
            channel="chat",
            meta={"from_type": "human"},
        ),
        _event((base + timedelta(seconds=4)).isoformat(), "cron_executed", "after range"),
    ]
    _write_entries(anima_dir, entries)

    result = activity.get_conversation_background(
        from_ts=cron_ts,
        to_ts=cron_ts,
    )

    messages = [message for session in result["sessions"] for message in session["messages"]]
    assert [message["content"] for message in messages] == ["in range background"]
    assert result["truncated"] is False


def test_feed_uses_scan_bound_as_a_cursor_when_recent_range_has_no_messages(tmp_path: Path) -> None:
    anima_dir, activity = _test_activity(tmp_path)
    old = now_local().replace(microsecond=0) - timedelta(days=15)
    _write_entries(
        anima_dir,
        [
            _event(
                old.isoformat(),
                "message_received",
                "older page",
                from_person="human",
                channel="chat",
                meta={"from_type": "human", "thread_id": "default"},
            )
        ],
    )

    recent = activity.get_conversation_feed(min_user_items=1, _schedule_prefetch=False)
    older = activity.get_conversation_feed(
        min_user_items=1,
        before=recent["next_before"],
        _schedule_prefetch=False,
    )

    assert recent["items"] == []
    assert recent["has_more"] is True
    assert recent["next_before"]
    assert older["items"][0]["message"]["content"] == "older page"


def test_background_endpoint_limits_results_to_newest_200_items(tmp_path: Path) -> None:
    anima_dir, activity = _test_activity(tmp_path)
    start = now_local().replace(microsecond=0) - timedelta(minutes=10)
    entries = [
        _event((start + timedelta(seconds=index)).isoformat(), "cron_executed", f"cron {index}") for index in range(205)
    ]
    _write_entries(anima_dir, entries)

    result = activity.get_conversation_background(
        from_ts=entries[0]["ts"],
        to_ts=entries[-1]["ts"],
    )

    messages = [message for session in result["sessions"] for message in session["messages"]]
    assert len(messages) == 200
    assert messages[0]["content"] == "cron 5"
    assert messages[-1]["content"] == "cron 204"
    assert result["truncated"] is True


def test_background_range_keeps_preceding_tool_events_for_lazy_summary(tmp_path: Path) -> None:
    anima_dir, activity = _test_activity(tmp_path)
    (anima_dir.parent / "rin").mkdir()
    start = now_local().replace(microsecond=0) - timedelta(minutes=10)
    tool_ts = (start + timedelta(seconds=1)).isoformat()
    result_ts = (start + timedelta(seconds=2)).isoformat()
    response_ts = (start + timedelta(seconds=3)).isoformat()
    _write_entries(
        anima_dir,
        [
            _event(
                tool_ts,
                "tool_use",
                "",
                tool="Read",
                channel="chat",
                meta={"args": {"file_path": "notes.md"}, "tool_use_id": "tool-1"},
            ),
            _event(
                result_ts,
                "tool_result",
                "read result",
                channel="chat",
                meta={"tool_use_id": "tool-1"},
            ),
            _event(
                response_ts,
                "response_sent",
                "DM answer",
                to_person="rin",
                channel="chat",
            ),
        ],
    )

    result = activity.get_conversation_background(from_ts=response_ts, to_ts=response_ts)

    message = result["sessions"][0]["messages"][0]
    assert message["content"] == "DM answer"
    assert message["tool_calls"] == [
        {"tool_name": "Read", "tool_use_id": "tool-1", "is_error": False, "target": "notes.md"}
    ]


def test_feed_cache_skips_reads_and_invalidates_when_latest_log_changes(tmp_path: Path) -> None:
    anima_dir, activity = _test_activity(tmp_path)
    now = now_local().replace(microsecond=0)
    path = _write_entries(
        anima_dir,
        [
            _event(
                now.isoformat(),
                "message_received",
                "first",
                from_person="human",
                channel="chat",
                meta={"from_type": "human", "thread_id": "default"},
            )
        ],
    )
    with patch.object(activity, "_load_feed_entries", wraps=activity._load_feed_entries) as load:
        first = activity.get_conversation_feed(min_user_items=1, _schedule_prefetch=False)
        second = activity.get_conversation_feed(min_user_items=1, _schedule_prefetch=False)
        assert load.call_count == 1
        assert first == second

        with path.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    _event(
                        (now + timedelta(seconds=1)).isoformat(),
                        "message_received",
                        "newest",
                        from_person="human",
                        channel="chat",
                        meta={"from_type": "human", "thread_id": "default"},
                    )
                )
                + "\n"
            )
        refreshed = activity.get_conversation_feed(min_user_items=1, _schedule_prefetch=False)
        assert load.call_count == 2
        assert refreshed["items"][-1]["message"]["content"] == "newest"


async def test_feed_and_background_routes_keep_history_api_shape_untouched(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    now = now_local().replace(microsecond=0)
    bg_ts = (now - timedelta(seconds=1)).isoformat()
    user_ts = now.isoformat()
    _write_entries(
        anima_dir,
        [
            _event(bg_ts, "cron_executed", "cron"),
            _event(
                user_ts,
                "message_received",
                "hello",
                from_person="human",
                channel="chat",
                meta={"from_type": "human", "thread_id": "default"},
            ),
        ],
    )
    app = FastAPI()
    app.state.animas_dir = tmp_path
    app.state.anima_names = ["alice"]
    app.include_router(create_sessions_router(), prefix="/api")
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        feed = await client.get("/api/animas/alice/conversation/feed?min_user_items=1")
        bg = await client.get(
            "/api/animas/alice/conversation/bg",
            params={"from_ts": bg_ts, "to_ts": bg_ts},
        )
        history = await client.get("/api/animas/alice/conversation/history?limit=10")

    assert feed.status_code == 200
    assert feed.json()["items"][-1]["message"]["content"] == "hello"
    assert bg.status_code == 200
    assert bg.json()["sessions"][0]["messages"][0]["content"] == "cron"
    assert set(history.json()) == {"sessions", "has_more", "next_before"}
