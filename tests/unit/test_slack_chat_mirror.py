"""Tests for mirroring Slack conversations into the Web chat view."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.activity.conversation import _is_user_item_entry, clear_conversation_feed_cache
from core.activity.logger import ActivityLogger
from core.activity.models import ActivityEntry
from core.activity.slack_mirror import (
    aliased_slack_users,
    display_text_for_slack,
    parse_slack_send_command,
    slack_reply_recipient,
    strip_thread_context,
)
from core.config.schemas import AnimaWorksConfig, UserAliasConfig
from core.time_utils import now_local
from server.gateways.slack_socket import _record_inbound_slack_mirror


@pytest.fixture(autouse=True)
def clear_feed_cache() -> None:
    clear_conversation_feed_cache()
    yield
    clear_conversation_feed_cache()


@pytest.fixture
def alias_config(monkeypatch: pytest.MonkeyPatch) -> AnimaWorksConfig:
    config = AnimaWorksConfig()
    config.external_messaging.user_aliases["owner"] = UserAliasConfig(slack_user_id="U123")
    monkeypatch.setattr("core.activity.slack_mirror.load_config", lambda: config)
    return config


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


def _activity(tmp_path: Path, name: str = "mei") -> tuple[Path, ActivityLogger]:
    anima_dir = tmp_path / "animas" / name
    (anima_dir / "activity_log").mkdir(parents=True)
    return anima_dir, ActivityLogger(anima_dir)


def _read_log(anima_dir: Path) -> list[dict]:
    entries: list[dict] = []
    for path in sorted((anima_dir / "activity_log").glob("*.jsonl")):
        entries.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line)
    return entries


def _history_messages(activity: ActivityLogger) -> list[dict]:
    history = activity.get_conversation_view(thread_id="default")
    return [message for session in history["sessions"] for message in session["messages"]]


def _feed_messages(activity: ActivityLogger) -> list[dict]:
    feed = activity.get_conversation_feed(min_user_items=1, _schedule_prefetch=False)
    return [item["message"] for item in feed["items"] if item["kind"] == "message"]


def test_aliased_users_only_returns_slack_ids(alias_config: AnimaWorksConfig) -> None:
    alias_config.external_messaging.user_aliases["chatwork_only"] = UserAliasConfig(chatwork_room_id="room-1")
    assert aliased_slack_users() == {"U123": "owner"}


def _slack_tool_use(command: str) -> ActivityEntry:
    return ActivityEntry(
        ts="2026-10-29T12:00:00+09:00",
        type="tool_use",
        content="Bash",
        tool="Bash",
        meta={"args": {"command": command}},
    )


def test_user_item_requires_a_slack_send_addressed_to_an_alias(alias_config: AnimaWorksConfig) -> None:
    assert _is_user_item_entry(_slack_tool_use("animaworks-tool slack send C0X '<@U123> hi'"), [], "mei")
    assert not _is_user_item_entry(_slack_tool_use("animaworks-tool slack send C0X '<@U999> hi'"), [], "mei")
    assert not _is_user_item_entry(_slack_tool_use("animaworks-tool slack send C0X 'hello'"), [], "mei")


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"text": "<@U123> hello", "channel": "C0X", "thread_ts": "", "trigger": ""}, "owner"),
        ({"text": "hello", "channel": "U123", "thread_ts": "", "trigger": ""}, "owner"),
        ({"text": "hello", "channel": "@owner", "thread_ts": "", "trigger": ""}, "owner"),
        ({"text": "hello", "channel": "C0X", "thread_ts": "", "trigger": "inbox:slack:U123"}, "owner"),
    ],
)
def test_slack_reply_recipient_addressability(
    alias_config: AnimaWorksConfig,
    kwargs: dict[str, str],
    expected: str,
) -> None:
    assert slack_reply_recipient(**kwargs, anima_name="mei") == expected


def test_slack_reply_recipient_notification_thread(alias_config: AnimaWorksConfig) -> None:
    owned = {"text": "hello", "channel": "C0X", "thread_ts": "1.2", "trigger": "", "notification_thread_owner": "mei"}
    assert slack_reply_recipient(**owned, anima_name="mei") == "owner"
    assert slack_reply_recipient(**owned, anima_name="other") is None
    assert slack_reply_recipient(text="hello", channel="C0X", thread_ts="1.2", trigger="", anima_name="mei") is None


def test_slack_reply_recipient_ignores_other_people_and_channels(alias_config: AnimaWorksConfig) -> None:
    assert (
        slack_reply_recipient(text="<@U999> hello", channel="C0X", thread_ts="", trigger="", anima_name="mei") is None
    )
    assert (
        slack_reply_recipient(text="hello", channel="C0X", thread_ts="", trigger="inbox:slack:U999", anima_name="mei")
        is None
    )
    assert (
        slack_reply_recipient(
            text="hello", channel="C0X", thread_ts="", trigger="inbox:chatwork:room-1", anima_name="mei"
        )
        is None
    )


def test_display_text_for_slack(alias_config: AnimaWorksConfig) -> None:
    text = "<@U123> hi <@U999>, see <#C0X|general> at <https://example.com|here> <https://example.com> **bold**"
    assert display_text_for_slack(text, {"U999": "Bob"}) == (
        "hi @Bob, see #general at [here](https://example.com) https://example.com **bold**"
    )


def test_display_text_converts_slack_emphasis_to_markdown(alias_config: AnimaWorksConfig) -> None:
    text = "*患者情報*：目録に書かない\n* 箇条書き\n**すでに太字** と ~取り消し~ と _斜体_ と 2*3*4"
    assert display_text_for_slack(text) == (
        "**患者情報**：目録に書かない\n* 箇条書き\n**すでに太字** と ~~取り消し~~ と _斜体_ と 2*3*4"
    )


def test_strip_thread_context_supports_slack_and_discord() -> None:
    slack = "[Thread context — this message is a reply in a Slack thread]\n  @Bob: parent\n[/Thread context]\n\nhello"
    discord = "[Thread context — Discord reply]\n  parent\n[/Thread context]\n\nhello"
    assert strip_thread_context(slack) == "hello"
    assert strip_thread_context(discord) == "hello"
    assert strip_thread_context("plain") == "plain"


def test_parse_slack_send_command_multiline_and_escaped(alias_config: AnimaWorksConfig) -> None:
    command = 'animaworks-tool slack send C0X "<@U123> line1\nline2 \\"quoted\\"" --thread 1.2'
    assert parse_slack_send_command(command) == ("C0X", '<@U123> line1\nline2 "quoted"', "1.2")
    command = "cd /tmp && animaworks-tool slack send C0X '<@U123> one\ntwo' --thread-ts=3.4"
    assert parse_slack_send_command(command) == ("C0X", "<@U123> one\ntwo", "3.4")


def _mock_slack(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    client.resolve_channel.return_value = "C0X"
    client.post_message.return_value = {"ts": "1.2", "channel": "C0X"}
    monkeypatch.setattr("core.integrations.slack.SlackClient", lambda token=None: client)
    monkeypatch.setattr("core.integrations.slack._resolve_slack_token", lambda args: "token")
    monkeypatch.setattr("core.integrations.slack._resolve_slack_identity", lambda args: ("bot", ""))
    return client


def test_dispatch_slack_send_records_user_addressed_reply(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.integrations.slack import _dispatch_slack_send

    anima_dir = tmp_path / "animas" / "mei"
    client = _mock_slack(monkeypatch)
    response = _dispatch_slack_send(
        {
            "anima_dir": str(anima_dir),
            "channel": "C0X",
            "message": "<@U123> こんにちは",
        }
    )

    assert response == client.post_message.return_value
    entries = _read_log(anima_dir)
    assert [entry["type"] for entry in entries] == ["external_reply_sent"]
    assert entries[0]["content"] == "こんにちは"
    assert entries[0]["to"] == "owner"
    assert entries[0]["via"] == "slack"
    assert entries[0]["meta"]["external_channel_id"] == "C0X"
    assert entries[0]["meta"]["external_ts"] == "1.2"


def test_dispatch_slack_channel_post_records_user_addressed_reply(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.integrations.slack import _dispatch_slack_channel_post

    anima_dir = tmp_path / "animas" / "mei"
    client = _mock_slack(monkeypatch)
    result = _dispatch_slack_channel_post(
        {
            "anima_dir": str(anima_dir),
            "channel_id": "C0X",
            "text": "<@U123> こんにちは",
            "thread_ts": "9.9",
        }
    )

    assert result == {"status": "ok", "channel": "C0X", "ts": "1.2"}
    assert client.post_message.return_value == {"ts": "1.2", "channel": "C0X"}
    entries = _read_log(anima_dir)
    assert [entry["type"] for entry in entries] == ["external_reply_sent"]
    assert entries[0]["content"] == "こんにちは"
    assert entries[0]["meta"]["external_thread_ts"] == "9.9"


def test_dispatch_slack_send_ignores_non_user_channel(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.integrations.slack import _dispatch_slack_send

    anima_dir = tmp_path / "animas" / "mei"
    _mock_slack(monkeypatch)
    _dispatch_slack_send({"anima_dir": str(anima_dir), "channel": "C0X", "message": "hello"})
    assert _read_log(anima_dir) == []


def test_dispatch_slack_send_survives_recording_failure(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.integrations.slack import _dispatch_slack_send

    client = _mock_slack(monkeypatch)
    monkeypatch.setattr(
        "core.activity.logger.ActivityLogger.log",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")),
    )
    response = _dispatch_slack_send(
        {"anima_dir": str(tmp_path / "animas" / "mei"), "channel": "C0X", "message": "<@U123> hi"}
    )
    assert response == client.post_message.return_value


async def test_gateway_records_alias_user_message(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.paths.get_animas_dir", lambda: tmp_path / "animas")
    await _record_inbound_slack_mirror(
        "mei",
        text="[Thread context — reply]\n  @Bob: parent\n[/Thread context]\n\nこんにちは",
        slack_user_id="U123",
        channel_id="C0X",
        thread_ts="1.2",
        source_message_id="2.3",
    )
    entries = _read_log(tmp_path / "animas" / "mei")
    assert [entry["type"] for entry in entries] == ["human_reply"]
    assert entries[0]["content"] == "こんにちは"
    assert entries[0]["from"] == "U123"
    assert entries[0]["via"] == "slack"
    assert entries[0]["meta"]["thread_ts"] == "1.2"
    assert entries[0]["meta"]["mirror"] == "slack_inbound"


async def test_gateway_ignores_non_alias_user(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.paths.get_animas_dir", lambda: tmp_path / "animas")
    await _record_inbound_slack_mirror(
        "mei",
        text="hello",
        slack_user_id="U999",
        channel_id="C0X",
        thread_ts="",
        source_message_id="2.3",
    )
    assert _read_log(tmp_path / "animas" / "mei") == []


def test_external_reply_sent_appears_in_history_and_feed(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
) -> None:
    anima_dir, activity = _activity(tmp_path)
    now = now_local().replace(microsecond=0)
    _write_entries(
        anima_dir,
        [
            _event(
                now.isoformat(),
                "external_reply_sent",
                "こんにちは",
                to_person="owner",
                via="slack",
                channel="slack",
                meta={
                    "thread_id": "default",
                    "external_channel_id": "C0X",
                    "external_thread_ts": "",
                    "external_ts": "1.2",
                },
            )
        ],
    )

    for messages in (_history_messages(activity), _feed_messages(activity)):
        assert len(messages) == 1
        message = messages[0]
        assert message["role"] == "assistant"
        assert message["type"] == "external_reply"
        assert message["content"] == "こんにちは"
        assert message["to_person"] == "owner"
        assert message["via"] == "slack"


def _derived_entries(
    command: str,
    *,
    trigger: str = "inbox:slack:U123",
    is_error: bool = False,
    ctx: str = "inbox",
) -> list[dict]:
    now = now_local().replace(microsecond=0) - timedelta(minutes=5)
    timestamps = [now + timedelta(seconds=offset) for offset in range(5)]
    return [
        _event(timestamps[0].isoformat(), "inbox_processing_start", meta={"session_type": "inbox"}),
        _event(
            timestamps[1].isoformat(),
            "message_received",
            "hello",
            from_person="slack:U123",
            channel="inbox",
            meta={"from_type": "slack", "trigger": trigger, "thread_id": "inbox"},
        ),
        _event(
            timestamps[2].isoformat(),
            "tool_use",
            "Bash",
            tool="Bash",
            from_person="mei",
            ctx=ctx,
            meta={"args": {"command": command}, "tool_use_id": "t1", "thread_id": "inbox"},
        ),
        _event(
            timestamps[3].isoformat(),
            "tool_result",
            "",
            tool="Bash",
            ctx=ctx,
            meta={"tool_use_id": "t1", "is_error": is_error},
        ),
        _event(timestamps[4].isoformat(), "inbox_processing_end", meta={"session_type": "inbox"}),
    ]


def test_historical_slack_send_is_derived_for_history_and_feed(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
) -> None:
    anima_dir, activity = _activity(tmp_path)
    command = "animaworks-tool slack send C0X '<@U123> こんにちは' --thread 1.2"
    _write_entries(anima_dir, _derived_entries(command))

    for messages in (_history_messages(activity), _feed_messages(activity)):
        replies = [m for m in messages if m.get("type") == "external_reply"]
        assert len(replies) == 1
        assert replies[0]["content"] == "こんにちは"
        assert replies[0]["to_person"] == "owner"
        assert replies[0]["derived"] is True


def test_historical_send_is_not_duplicated_by_explicit_record(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
) -> None:
    anima_dir, activity = _activity(tmp_path)
    command = "animaworks-tool slack send C0X '<@U123> こんにちは' --thread 1.2"
    entries = _derived_entries(command, ctx="chat")
    explicit_ts = (now_local().replace(microsecond=0) - timedelta(minutes=5, seconds=-70)).isoformat()
    entries.append(
        _event(
            explicit_ts,
            "external_reply_sent",
            "こんにちは",
            to_person="owner",
            via="slack",
            channel="slack",
            meta={"thread_id": "default", "external_ts": "9.9"},
        )
    )
    _write_entries(anima_dir, entries)

    for messages in (_history_messages(activity), _feed_messages(activity)):
        assert len([m for m in messages if m.get("type") == "external_reply"]) == 1


def test_historical_send_error_is_not_shown(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
) -> None:
    anima_dir, activity = _activity(tmp_path)
    command = "animaworks-tool slack send C0X '<@U123> こんにちは' --thread 1.2"
    _write_entries(anima_dir, _derived_entries(command, is_error=True))

    for messages in (_history_messages(activity), _feed_messages(activity)):
        assert [m for m in messages if m.get("type") == "external_reply"] == []


def test_historical_send_to_other_recipient_is_not_shown(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
) -> None:
    anima_dir, activity = _activity(tmp_path)
    command = "animaworks-tool slack send C0X 'hello'"
    _write_entries(anima_dir, _derived_entries(command, trigger="inbox:slack:U999"))

    for messages in (_history_messages(activity), _feed_messages(activity)):
        assert [m for m in messages if m.get("type") == "external_reply"] == []


def test_inbound_slack_message_is_shown_as_human_reply(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
) -> None:
    anima_dir, activity = _activity(tmp_path)
    now = now_local().replace(microsecond=0) - timedelta(minutes=5)
    content = (
        "[slack:channel #general — you are mentioned]\n"
        "[Thread context — reply]\n  @Bob: parent\n[/Thread context]\n\nこんにちは"
    )
    _write_entries(
        anima_dir,
        [
            _event(now.isoformat(), "inbox_processing_start", meta={"session_type": "inbox"}),
            _event(
                (now + timedelta(seconds=1)).isoformat(),
                "message_received",
                content,
                from_person="slack:U123",
                channel="inbox",
                meta={"from_type": "slack", "trigger": "inbox:slack:U123", "thread_id": "inbox"},
            ),
            _event((now + timedelta(seconds=2)).isoformat(), "inbox_processing_end", meta={"session_type": "inbox"}),
        ],
    )

    for messages in (_history_messages(activity), _feed_messages(activity)):
        humans = [m for m in messages if m.get("type") == "human_reply"]
        assert len(humans) == 1
        assert humans[0]["content"] == "こんにちは"
        assert humans[0]["from_person"] == "owner"
        assert humans[0]["via"] == "slack"
        assert humans[0]["derived"] is True


def test_inbound_slack_message_paired_with_human_reply_is_not_duplicated(
    tmp_path: Path,
    alias_config: AnimaWorksConfig,
) -> None:
    anima_dir, activity = _activity(tmp_path)
    now = now_local().replace(microsecond=0) - timedelta(minutes=5)
    _write_entries(
        anima_dir,
        [
            _event(
                now.isoformat(),
                "human_reply",
                "こんにちは",
                from_person="U123",
                via="slack",
                channel="slack",
                ctx="chat",
                meta={"thread_ts": "1.2"},
            ),
            _event(
                (now + timedelta(seconds=10)).isoformat(),
                "message_received",
                "[Thread context — reply]\n  @Bob: parent\n[/Thread context]\n\nこんにちは",
                from_person="slack:U123",
                channel="inbox",
                meta={"from_type": "slack", "trigger": "inbox:slack:U123", "thread_id": "inbox"},
            ),
        ],
    )

    for messages in (_history_messages(activity), _feed_messages(activity)):
        humans = [m for m in messages if m.get("type") == "human_reply"]
        assert len(humans) == 1
        assert humans[0]["content"] == "こんにちは"
