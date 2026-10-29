from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.integrations import (
    aws_collector,
    chatwork,
    discord,
    github,
    gmail,
    google_calendar,
    google_sheets,
    google_tasks,
    image_gen,
    local_llm,
    notion,
    slack,
    transcribe,
    web_search,
    x_search,
)


def _marker(name: str) -> dict[str, str]:
    return {"tool": name}


def test_dispatch_handler_tables_cover_every_tool_name() -> None:
    expected = {
        aws_collector: {"aws_ecs_status", "aws_error_logs", "aws_metrics"},
        chatwork: {
            "chatwork_send",
            "chatwork_upload",
            "chatwork_messages",
            "chatwork_search",
            "chatwork_unreplied",
            "chatwork_delete",
            "chatwork_rooms",
            "chatwork_sync",
            "chatwork_mentions",
        },
        discord: {
            "discord_send",
            "discord_messages",
            "discord_search",
            "discord_guilds",
            "discord_channels",
            "discord_react",
            "discord_channel_post",
            "discord_unreplied",
        },
        github: {"github_list_issues", "github_create_issue", "github_list_prs", "github_create_pr"},
        gmail: {
            "gmail_unread",
            "gmail_inbox",
            "gmail_sent",
            "gmail_search",
            "gmail_read_body",
            "gmail_download",
            "gmail_draft",
            "gmail_drafts",
            "gmail_draft_get",
            "gmail_draft_update",
            "gmail_send",
        },
        google_calendar: {
            "google_calendar_list",
            "google_calendar_add",
            "google_calendar_get",
            "google_calendar_update",
            "google_calendar_delete",
        },
        google_sheets: {
            "google_sheets_tabs",
            "google_sheets_read",
            "google_sheets_write_values",
            "google_sheets_append_values",
        },
        google_tasks: {
            "google_tasks_list_tasklists",
            "google_tasks_list_tasks",
            "google_tasks_insert_task",
            "google_tasks_insert_tasklist",
            "google_tasks_update_task",
            "google_tasks_update_tasklist",
        },
        image_gen: {
            "generate_character_assets",
            "generate_fullbody",
            "generate_bustup",
            "generate_icon",
            "generate_chibi",
            "generate_3d_model",
            "generate_rigged_model",
            "generate_animations",
        },
        local_llm: {"local_llm_generate", "local_llm_chat", "local_llm_models", "local_llm_status"},
        notion: {
            "notion_search",
            "notion_get_page",
            "notion_get_page_content",
            "notion_get_database",
            "notion_query",
            "notion_create_page",
            "notion_update_page",
            "notion_create_database",
        },
        slack: {
            "slack_send",
            "slack_messages",
            "slack_search",
            "slack_unreplied",
            "slack_channels",
            "slack_react",
            "slack_channel_post",
            "slack_channel_update",
        },
        transcribe: {"transcribe_audio"},
        web_search: {"web_search"},
        x_search: {"x_search", "x_user_tweets"},
    }
    assert sum(len(names) for names in expected.values()) == 82
    for module, names in expected.items():
        assert set(module._DISPATCH_HANDLERS) == names, module.__name__


_CHATWORK_CASES = [
    pytest.param("chatwork_send", {"room": "room", "message": "hello", "as": "owner"}, id="send"),
    pytest.param(
        "chatwork_upload",
        {"room": "room", "message": "caption", "file": "~/report.pdf"},
        id="upload",
    ),
    pytest.param("chatwork_messages", {"room": "room", "limit": 7}, id="messages"),
    pytest.param("chatwork_search", {"room": "room", "keyword": "needle", "limit": 8}, id="search"),
    pytest.param("chatwork_unreplied", {"include_toall": True}, id="unreplied"),
    pytest.param("chatwork_delete", {"room": "room", "message_id": "m1", "as": "owner"}, id="delete"),
    pytest.param("chatwork_rooms", {}, id="rooms"),
    pytest.param("chatwork_sync", {"limit": 9}, id="sync"),
    pytest.param("chatwork_mentions", {"include_toall": False, "limit": 6}, id="mentions"),
]


@pytest.mark.parametrize(("name", "args"), _CHATWORK_CASES)
def test_chatwork_dispatch_golden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, args: dict) -> None:
    client = MagicMock()
    client.resolve_room_id.return_value = "room-42"
    client.me.return_value = {"account_id": 42}
    client.get_message.return_value = {"account": {"account_id": "42", "name": "Bot"}}
    client.get_messages.return_value = [{"message_id": "m1"}]
    marker = _marker(name)
    client.post_message.return_value = marker
    client.upload_file.return_value = marker
    client.rooms.return_value = marker

    cache = MagicMock()
    cache.get_recent.return_value = marker
    cache.search.return_value = marker
    cache.find_unreplied.return_value = marker
    cache.find_mentions.return_value = marker

    identity = SimpleNamespace(token="chatwork-token")
    resolve_identity = MagicMock(return_value=identity)
    client_class = MagicMock(return_value=client)
    cache_class = MagicMock(return_value=cache)
    check_write_allowed = MagicMock()
    sync_rooms = MagicMock(return_value=marker)
    monkeypatch.setattr(chatwork, "resolve_identity", resolve_identity)
    monkeypatch.setattr(chatwork, "ChatworkClient", client_class)
    monkeypatch.setattr(chatwork, "MessageCache", cache_class)
    monkeypatch.setattr(chatwork, "resolve_cache_db_path", lambda _client: tmp_path / "cache.db")
    monkeypatch.setattr(chatwork, "check_write_allowed", check_write_allowed)
    monkeypatch.setattr(chatwork, "md_to_chatwork", lambda text: f"chatwork:{text}")
    monkeypatch.setattr(chatwork, "_load_chatwork_tool_config", lambda: {"unreplied": {"include": True}})
    monkeypatch.setattr(chatwork, "_sync_rooms", sync_rooms)

    result = chatwork.dispatch(name, args)

    resolve_identity.assert_called_once_with(args.get("as"), anima_dir=args.get("anima_dir"))
    client_class.assert_called_once_with(api_token="chatwork-token")
    if name in {"chatwork_send", "chatwork_upload", "chatwork_delete"}:
        check_write_allowed.assert_called_once_with(args.get("as"), anima_dir=args.get("anima_dir"))
    else:
        check_write_allowed.assert_not_called()

    if name == "chatwork_send":
        assert result == marker
        client.resolve_room_id.assert_called_once_with("room")
        client.post_message.assert_called_once_with("room-42", "chatwork:hello")
    elif name == "chatwork_upload":
        assert result == marker
        client.resolve_room_id.assert_called_once_with("room")
        client.upload_file.assert_called_once_with("room-42", Path("~/report.pdf").expanduser(), "chatwork:caption")
    elif name == "chatwork_messages":
        assert result == marker
        client.resolve_room_id.assert_called_once_with("room")
        client.get_messages.assert_called_once_with("room-42", force=True)
        cache.upsert_messages.assert_called_once_with("room-42", [{"message_id": "m1"}])
        cache.update_sync_state.assert_called_once_with("room-42")
        cache.get_recent.assert_called_once_with("room-42", limit=7)
    elif name == "chatwork_search":
        assert result == marker
        client.resolve_room_id.assert_called_once_with("room")
        cache.search.assert_called_once_with("needle", room_id="room-42", limit=8)
    elif name == "chatwork_unreplied":
        assert result == marker
        client.me.assert_called_once_with()
        cache.find_unreplied.assert_called_once_with("42", exclude_toall=False, config={"unreplied": {"include": True}})
    elif name == "chatwork_delete":
        assert result == {"deleted": True, "message_id": "m1", "room_id": "room-42"}
        client.me.assert_called_once_with()
        client.get_message.assert_called_once_with("room-42", "m1")
        client.delete_message.assert_called_once_with("room-42", "m1")
    elif name == "chatwork_rooms":
        assert result == marker
        client.rooms.assert_called_once_with()
    elif name == "chatwork_sync":
        assert result == marker
        sync_rooms.assert_called_once_with(client, cache, sync_limit=9)
    else:
        assert result == marker
        client.me.assert_called_once_with()
        cache.find_mentions.assert_called_once_with(
            "42",
            exclude_toall=True,
            limit=6,
            config={"unreplied": {"include": True}},
        )

    if name in {"chatwork_messages", "chatwork_search", "chatwork_unreplied", "chatwork_sync", "chatwork_mentions"}:
        cache_class.assert_called_once_with(db_path=tmp_path / "cache.db")
        cache.close.assert_called_once_with()
    else:
        cache_class.assert_not_called()


def test_chatwork_dispatch_unknown_name_preserves_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chatwork, "resolve_identity", lambda *_args, **_kwargs: SimpleNamespace(token="token"))
    monkeypatch.setattr(chatwork, "ChatworkClient", MagicMock())
    with pytest.raises(ValueError, match="Unknown tool: chatwork_missing"):
        chatwork.dispatch("chatwork_missing", {})


def test_chatwork_table_driven_search_keeps_like_and_join_semantics(tmp_path: Path) -> None:
    from core.integrations._chatwork_cache import MessageCache

    cache = MessageCache(tmp_path / "chatwork.db")
    try:
        cache.upsert_room({"room_id": "r1", "name": "Research"})
        cache.upsert_messages("r1", [{"message_id": "m1", "send_time": 2, "body": "fooXbar"}])

        results = cache.search("foo_bar", room_id="r1")

        assert [(row["message_id"], row["room_name"]) for row in results] == [("m1", "Research")]
        assert cache.get_recent("r1", limit=1)[0]["room_name"] == "Research"
    finally:
        cache.close()


def test_slack_table_driven_search_keeps_like_and_join_semantics(tmp_path: Path) -> None:
    from core.integrations._slack_cache import MessageCache

    cache = MessageCache(db_path=tmp_path / "slack.db")
    try:
        cache.upsert_channel({"id": "C1", "name": "research"})
        cache.upsert_messages("C1", [{"ts": "2.0", "text": "fooXbar"}])

        results = cache.search("foo_bar", channel_id="C1")

        assert [(row["ts"], row["channel_name"]) for row in results] == [("2.0", "research")]
        assert cache.get_recent("C1", limit=1)[0]["channel_name"] == "research"
    finally:
        cache.close()


def test_discord_table_driven_search_keeps_like_semantics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from core.integrations import _discord_cache

    monkeypatch.setattr(_discord_cache, "get_data_dir", lambda: tmp_path)
    cache = _discord_cache.MessageCache()
    try:
        cache.upsert_messages("C1", [{"id": "m1", "content": "fooXbar", "timestamp": "2"}])

        results = cache.search("foo_bar", channel_id="C1")

        assert [row["id"] for row in results] == ["m1"]
        assert cache.get_recent("C1", limit=1)[0]["id"] == "m1"
    finally:
        cache.close()


_DISCORD_CASES = [
    pytest.param("discord_send", {"channel_id": "C1", "message": "hello", "reply_to": "M0"}, id="send"),
    pytest.param("discord_messages", {"channel_id": "C1", "limit": "7"}, id="messages"),
    pytest.param("discord_search", {"keyword": "needle", "channel_id": "C1", "limit": "8"}, id="search"),
    pytest.param("discord_channels", {"guild_id": "G1"}, id="channels"),
    pytest.param("discord_react", {"channel_id": "C1", "message_id": "M1", "emoji": "✅"}, id="react"),
    pytest.param(
        "discord_unreplied", {"anima_dir": "/srv/animas/mei", "channel_id": "C1", "limit": "4"}, id="unreplied"
    ),
]


@pytest.mark.parametrize(("name", "args"), _DISCORD_CASES)
def test_discord_dispatch_golden(monkeypatch: pytest.MonkeyPatch, name: str, args: dict) -> None:
    client = MagicMock()
    client.my_user_id = "U-ME"
    message = {"id": "M1", "author": {"id": "U1", "global_name": "Alice"}}
    client.channel_history.return_value = [message]
    marker = _marker(name)
    for method in ("send_message", "channels", "add_reaction"):
        getattr(client, method).return_value = marker

    cache = MagicMock()
    cache.get_recent.return_value = marker
    cache.search.return_value = marker
    cache.find_unreplied.return_value = marker
    client_class = MagicMock(return_value=client)
    cache_class = MagicMock(return_value=cache)
    monkeypatch.setattr(discord, "DiscordClient", client_class)
    monkeypatch.setattr(discord, "_resolve_discord_token", lambda _args: "discord-token")
    monkeypatch.setattr(discord, "MessageCache", cache_class)

    result = discord.dispatch(name, args)

    if name == "discord_send":
        assert result == marker
        client_class.assert_called_once_with(token="discord-token")
        client.send_message.assert_called_once_with("C1", "hello", reply_to="M0")
        client.close.assert_called_once_with()
        cache_class.assert_not_called()
    elif name == "discord_messages":
        assert result == marker
        client.channel_history.assert_called_once_with("C1", limit=7)
        cache.upsert_messages.assert_called_once_with(
            "C1",
            [{"id": "M1", "author": {"id": "U1", "global_name": "Alice"}, "user_id": "U1", "user_name": "Alice"}],
        )
        cache.update_sync_state.assert_called_once_with("C1")
        cache.get_recent.assert_called_once_with("C1", limit=7)
        client.close.assert_called_once_with()
    elif name == "discord_search":
        assert result == marker
        client_class.assert_not_called()
        cache.search.assert_called_once_with("needle", channel_id="C1", limit=8)
    elif name == "discord_channels":
        assert result == marker
        client.channels.assert_called_once_with("G1")
        client.close.assert_called_once_with()
        cache_class.assert_not_called()
    elif name == "discord_react":
        assert result == marker
        client.add_reaction.assert_called_once_with("C1", "M1", "✅")
        client.close.assert_called_once_with()
        cache_class.assert_not_called()
    else:
        assert result == marker
        client_class.assert_not_called()
        cache.find_unreplied.assert_called_once_with("mei", channel_id="C1", limit=4)

    if name in {"discord_messages", "discord_search", "discord_unreplied"}:
        cache_class.assert_called_once_with()
        cache.close.assert_called_once_with()


_SLACK_CASES = [
    pytest.param("slack_messages", {"channel": "general", "limit": 7}, id="messages"),
    pytest.param("slack_search", {"keyword": "needle", "channel": "general", "limit": 8}, id="search"),
    pytest.param("slack_unreplied", {}, id="unreplied"),
    pytest.param("slack_channels", {}, id="channels"),
    pytest.param("slack_react", {"channel": "general", "emoji": ":wave:", "message_ts": "2.0"}, id="react"),
]


@pytest.mark.parametrize(("name", "args"), _SLACK_CASES)
def test_slack_dispatch_golden(monkeypatch: pytest.MonkeyPatch, name: str, args: dict) -> None:
    client = MagicMock()
    client.resolve_channel.return_value = "C1"
    client.channel_history.return_value = [{"ts": "1.0", "user": "U1"}]
    client.resolve_user_name.return_value = "Alice"
    client.my_user_id = "U-ME"
    marker = _marker(name)
    client.channels.return_value = marker
    client.add_reaction.return_value = marker
    client.update_message.return_value = marker

    cache = MagicMock()
    cache.get_recent.return_value = marker
    cache.search.return_value = marker
    cache.find_unreplied.return_value = marker
    client_class = MagicMock(return_value=client)
    cache_class = MagicMock(return_value=cache)
    monkeypatch.setattr(slack, "SlackClient", client_class)
    monkeypatch.setattr(slack, "_resolve_slack_token", lambda _args: "slack-token")
    monkeypatch.setattr("core.integrations._slack_cache.MessageCache", cache_class)

    result = slack.dispatch(name, args)

    if name == "slack_messages":
        assert result == marker
        client.resolve_channel.assert_called_once_with("general")
        client.channel_history.assert_called_once_with("C1", limit=7)
        client.resolve_user_name.assert_called_once_with("U1")
        cache.upsert_messages.assert_called_once_with("C1", [{"ts": "1.0", "user": "U1", "user_name": "Alice"}])
        cache.update_sync_state.assert_called_once_with("C1")
        cache.get_recent.assert_called_once_with("C1", limit=7)
    elif name == "slack_search":
        assert result == marker
        client.resolve_channel.assert_called_once_with("general")
        cache.search.assert_called_once_with("needle", channel_id="C1", limit=8)
    elif name == "slack_unreplied":
        assert result == marker
        client.auth_test.assert_called_once_with()
        cache.find_unreplied.assert_called_once_with("U-ME")
    elif name == "slack_channels":
        assert result == marker
        client.channels.assert_called_once_with()
        cache_class.assert_not_called()
    elif name == "slack_react":
        assert result == marker
        client.resolve_channel.assert_called_once_with("general")
        client.add_reaction.assert_called_once_with("C1", ":wave:", "2.0")
        cache_class.assert_not_called()
    if name in {"slack_messages", "slack_search", "slack_unreplied"}:
        cache_class.assert_called_once_with()
        cache.close.assert_called_once_with()


def _assert_client_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    module,
    client_name: str,
    tool_name: str,
    args: dict,
    method: str,
    constructor_kwargs: dict,
    call_args: tuple = (),
    call_kwargs: dict | None = None,
) -> None:
    client = MagicMock()
    marker = _marker(tool_name)
    getattr(client, method).return_value = marker
    client_class = MagicMock(return_value=client)
    monkeypatch.setattr(module, client_name, client_class)

    assert module.dispatch(tool_name, args) == marker
    client_class.assert_called_once_with(**constructor_kwargs)
    getattr(client, method).assert_called_once_with(*call_args, **(call_kwargs or {}))


_GITHUB_CASES = [
    pytest.param(
        "github_list_issues",
        {"repo": "o/r", "state": "closed", "labels": ["bug"], "limit": 3},
        "list_issues",
        {"repo": "o/r"},
        (),
        {"state": "closed", "labels": ["bug"], "limit": 3},
        id="list-issues",
    ),
    pytest.param(
        "github_create_issue",
        {"title": "T", "body": "B", "labels": ["bug"]},
        "create_issue",
        {"repo": None},
        (),
        {"title": "T", "body": "B", "labels": ["bug"]},
        id="create-issue",
    ),
    pytest.param(
        "github_list_prs",
        {"state": "all", "limit": 4},
        "list_prs",
        {"repo": None},
        (),
        {"state": "all", "limit": 4},
        id="list-prs",
    ),
    pytest.param(
        "github_create_pr",
        {"title": "T", "head": "feature", "draft": True},
        "create_pr",
        {"repo": None},
        (),
        {"title": "T", "body": "", "head": "feature", "base": "main", "draft": True},
        id="create-pr",
    ),
]


@pytest.mark.parametrize(("tool_name", "args", "method", "constructor", "call_args", "call_kwargs"), _GITHUB_CASES)
def test_github_dispatch_golden(monkeypatch, tool_name, args, method, constructor, call_args, call_kwargs) -> None:
    _assert_client_dispatch(
        monkeypatch, github, "GitHubClient", tool_name, args, method, constructor, call_args, call_kwargs
    )


_AWS_CASES = [
    pytest.param(
        "aws_ecs_status",
        {"region": "ap-southeast-1", "cluster": "c", "service": "s"},
        "get_ecs_status",
        {"region": "ap-southeast-1"},
        ("c", "s"),
        {},
        id="ecs-status",
    ),
    pytest.param(
        "aws_error_logs",
        {"log_group": "g", "hours": 2, "patterns": ["ERROR"]},
        "get_error_logs",
        {"region": None},
        (),
        {"log_group": "g", "hours": 2, "patterns": ["ERROR"]},
        id="error-logs",
    ),
    pytest.param(
        "aws_metrics",
        {"cluster": "c", "service": "s", "metric": "Memory", "hours": 4},
        "get_metrics",
        {"region": None},
        (),
        {"cluster": "c", "service": "s", "metric": "Memory", "hours": 4},
        id="metrics",
    ),
]


@pytest.mark.parametrize(("tool_name", "args", "method", "constructor", "call_args", "call_kwargs"), _AWS_CASES)
def test_aws_dispatch_golden(monkeypatch, tool_name, args, method, constructor, call_args, call_kwargs) -> None:
    _assert_client_dispatch(
        monkeypatch, aws_collector, "AWSCollector", tool_name, args, method, constructor, call_args, call_kwargs
    )


_LOCAL_LLM_CASES = [
    pytest.param(
        "local_llm_generate",
        {"prompt": "hello", "server": "gpu", "temperature": 0.2},
        "generate",
        {"server": "gpu", "model": None, "hint": None},
        (),
        {"prompt": "hello", "system": "", "temperature": 0.2, "max_tokens": 4096, "think": "off"},
        id="generate",
    ),
    pytest.param(
        "local_llm_chat",
        {"messages": [{"role": "user", "content": "hi"}], "model": "m"},
        "chat",
        {"server": "auto", "model": "m", "hint": None},
        (),
        {
            "messages": [{"role": "user", "content": "hi"}],
            "system": "",
            "temperature": 0.7,
            "max_tokens": 4096,
            "think": "off",
        },
        id="chat",
    ),
    pytest.param("local_llm_models", {"server": "gpu"}, "list_models", {"server": "gpu"}, (), {}, id="models"),
    pytest.param("local_llm_status", {}, "server_status", {}, (), {}, id="status"),
]


@pytest.mark.parametrize(("tool_name", "args", "method", "constructor", "call_args", "call_kwargs"), _LOCAL_LLM_CASES)
def test_local_llm_dispatch_golden(monkeypatch, tool_name, args, method, constructor, call_args, call_kwargs) -> None:
    _assert_client_dispatch(
        monkeypatch, local_llm, "OllamaClient", tool_name, args, method, constructor, call_args, call_kwargs
    )


_GOOGLE_CALENDAR_CASES = [
    pytest.param(
        "google_calendar_list",
        {"max_results": 5, "days": 2, "calendar_id": "work"},
        "list_events",
        (),
        {"max_results": 5, "days": 2, "calendar_id": "work"},
        id="list",
    ),
    pytest.param(
        "google_calendar_add",
        {"summary": "Meeting", "start": "s", "end": "e", "attendees": "a@example.test"},
        "add_event",
        (),
        {
            "summary": "Meeting",
            "start": "s",
            "end": "e",
            "description": "",
            "location": "",
            "calendar_id": "primary",
            "attendees": ["a@example.test"],
        },
        id="add",
    ),
    pytest.param(
        "google_calendar_get",
        {"event_id": "e1", "calendar_id": "work"},
        "get_event",
        (),
        {"event_id": "e1", "calendar_id": "work"},
        id="get",
    ),
    pytest.param(
        "google_calendar_update",
        {"event_id": "e1", "summary": "New", "send_updates": "all"},
        "update_event",
        (),
        {
            "event_id": "e1",
            "calendar_id": "primary",
            "summary": "New",
            "start": None,
            "end": None,
            "description": None,
            "location": None,
            "send_updates": "all",
        },
        id="update",
    ),
    pytest.param(
        "google_calendar_delete",
        {"event_id": "e1", "confirm": True},
        "delete_event",
        (),
        {"event_id": "e1", "calendar_id": "primary", "send_updates": "none"},
        id="delete",
    ),
]


@pytest.mark.parametrize(("tool_name", "args", "method", "call_args", "call_kwargs"), _GOOGLE_CALENDAR_CASES)
def test_google_calendar_dispatch_golden(monkeypatch, tool_name, args, method, call_args, call_kwargs) -> None:
    args = {**args, "anima_dir": "/srv/animas/mei"}
    _assert_client_dispatch(
        monkeypatch,
        google_calendar,
        "GoogleCalendarClient",
        tool_name,
        args,
        method,
        {},
        call_args,
        call_kwargs,
    )


_GOOGLE_TASKS_CASES = [
    pytest.param(
        "google_tasks_list_tasklists",
        {"max_results": "7"},
        "list_tasklists",
        (),
        {"max_results": 7},
        id="list-tasklists",
    ),
    pytest.param(
        "google_tasks_list_tasks",
        {"tasklist_id": "l1", "max_results": "4", "show_completed": False},
        "list_tasks",
        (),
        {"tasklist_id": "l1", "max_results": 4, "show_completed": False},
        id="list-tasks",
    ),
    pytest.param(
        "google_tasks_insert_task",
        {"tasklist_id": "l1", "title": "T", "notes": "N", "due": ""},
        "insert_task",
        (),
        {"tasklist_id": "l1", "title": "T", "notes": "N", "due": None},
        id="insert-task",
    ),
    pytest.param(
        "google_tasks_insert_tasklist",
        {"title": "New list"},
        "insert_tasklist",
        (),
        {"title": "New list"},
        id="insert-tasklist",
    ),
    pytest.param(
        "google_tasks_update_task",
        {"tasklist_id": "l1", "task_id": "t1", "title": "T", "notes": "", "due": None, "status": "completed"},
        "update_task",
        (),
        {"tasklist_id": "l1", "task_id": "t1", "title": "T", "notes": "", "due": None, "status": "completed"},
        id="update-task",
    ),
    pytest.param(
        "google_tasks_update_tasklist",
        {"tasklist_id": "l1", "title": "Renamed"},
        "update_tasklist",
        (),
        {"tasklist_id": "l1", "title": "Renamed"},
        id="update-tasklist",
    ),
]


@pytest.mark.parametrize(("tool_name", "args", "method", "call_args", "call_kwargs"), _GOOGLE_TASKS_CASES)
def test_google_tasks_dispatch_golden(monkeypatch, tool_name, args, method, call_args, call_kwargs) -> None:
    args = {**args, "anima_dir": "/srv/animas/mei"}
    _assert_client_dispatch(
        monkeypatch,
        google_tasks,
        "GoogleTasksClient",
        tool_name,
        args,
        method,
        {},
        call_args,
        call_kwargs,
    )


_GOOGLE_SHEETS_CASES = [
    pytest.param(
        "google_sheets_read",
        {"spreadsheet_id": "S1", "range": "A1:B2"},
        "read_values",
        ("S1",),
        {"range_": "A1:B2"},
        id="read",
    ),
    pytest.param("google_sheets_tabs", {"spreadsheet_id": "S1"}, "list_tabs", ("S1",), {}, id="tabs"),
    pytest.param(
        "google_sheets_write_values",
        {"spreadsheet_id": "S1", "range": "A1", "values": [[1]], "value_input_option": "RAW"},
        "write_values",
        ("S1", "A1", [[1]]),
        {"value_input_option": "RAW"},
        id="write",
    ),
    pytest.param(
        "google_sheets_append_values",
        {"spreadsheet_id": "S1", "range": "A:A", "values": [[2]]},
        "append_values",
        ("S1", "A:A", [[2]]),
        {"value_input_option": "USER_ENTERED"},
        id="append",
    ),
]


@pytest.mark.parametrize(("tool_name", "args", "method", "call_args", "call_kwargs"), _GOOGLE_SHEETS_CASES)
def test_google_sheets_dispatch_golden(monkeypatch, tool_name, args, method, call_args, call_kwargs) -> None:
    args = {**args, "anima_dir": "/srv/animas/mei"}
    _assert_client_dispatch(
        monkeypatch,
        google_sheets,
        "GoogleSheetsClient",
        tool_name,
        args,
        method,
        {},
        call_args,
        call_kwargs,
    )


@pytest.mark.parametrize(
    ("module", "name"),
    [
        pytest.param(google_calendar, "google_calendar_missing", id="calendar"),
        pytest.param(google_tasks, "google_tasks_missing", id="tasks"),
        pytest.param(google_sheets, "google_sheets_missing", id="sheets"),
    ],
)
def test_google_dispatch_unknown_action_returns_existing_error(monkeypatch, module, name: str) -> None:
    assert module.dispatch(name, {"anima_dir": "/tmp/anima"}) == {"error": f"Unknown action: {name}"}


def test_gmail_download_dispatch_golden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = MagicMock()
    client.get_attachments.return_value = [("a.pdf", tmp_path / "a.pdf"), ("b.txt", tmp_path / "b.txt")]
    client_class = MagicMock(return_value=client)
    monkeypatch.setattr(gmail, "GmailClient", client_class)

    result = gmail.dispatch("gmail_download", {"message_id": "m1", "save_dir": str(tmp_path)})

    client_class.assert_called_once_with()
    client.get_attachments.assert_called_once_with("m1", tmp_path)
    assert result == {
        "count": 2,
        "attachments": [
            {"filename": "a.pdf", "path": str(tmp_path / "a.pdf")},
            {"filename": "b.txt", "path": str(tmp_path / "b.txt")},
        ],
    }


_X_SEARCH_CASES = [
    pytest.param(
        "x_search",
        {"query": "from:alice", "max_results": 15, "days": 2},
        "search_recent",
        {"query": "from:alice", "max_results": 15, "days": 2},
        id="search",
    ),
    pytest.param(
        "x_user_tweets",
        {"username": "alice", "max_results": 4, "days": 1},
        "get_user_tweets",
        {"username": "alice", "max_results": 4, "days": 1},
        id="user-tweets",
    ),
]


@pytest.mark.parametrize(("tool_name", "args", "method", "call_kwargs"), _X_SEARCH_CASES)
def test_x_search_dispatch_golden(monkeypatch, tool_name, args, method, call_kwargs) -> None:
    _assert_client_dispatch(monkeypatch, x_search, "XSearchClient", tool_name, args, method, {}, (), call_kwargs)


def test_transcribe_dispatch_golden(monkeypatch: pytest.MonkeyPatch) -> None:
    process_audio = MagicMock(return_value={"text": "spoken"})
    monkeypatch.setattr(transcribe, "process_audio", process_audio)
    result = transcribe.dispatch(
        "transcribe_audio",
        {"audio_path": "/tmp/a.wav", "language": "en", "model": "llm", "raw_only": True, "custom_prompt": "clean"},
    )
    assert result == {"text": "spoken"}
    process_audio.assert_called_once_with(
        audio_path="/tmp/a.wav",
        language="en",
        model="llm",
        raw_only=True,
        custom_prompt="clean",
    )


def test_web_search_dispatch_golden(monkeypatch: pytest.MonkeyPatch) -> None:
    search = MagicMock(return_value=[{"title": "result"}])
    monkeypatch.setattr(web_search, "search", search)
    args = {"anima_dir": "/srv/animas/mei", "query": "query", "limit": 3, "lang": "en"}

    result = web_search.dispatch("web_search", args)

    assert result == [{"title": "result"}]
    search.assert_called_once_with(query="query", lang="en", count=3)
    assert args == {"query": "query", "lang": "en", "count": 3}


_IMAGE_CONFIG = SimpleNamespace(image_style="anime", style_prefix="", style_suffix="")


def _mock_image_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.config.models.load_config",
        lambda: SimpleNamespace(image_gen=_IMAGE_CONFIG),
    )


def test_image_dispatch_character_assets_golden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    anima_dir = tmp_path / "mei"
    anima_dir.mkdir()
    _mock_image_config(monkeypatch)
    pipeline = MagicMock()
    pipeline.generate_all.return_value.to_dict.return_value = {"generated": True}
    pipeline_class = MagicMock(return_value=pipeline)
    monkeypatch.setattr(image_gen, "ImageGenPipeline", pipeline_class)

    args = {"anima_dir": str(anima_dir), "prompt": "character", "skip_existing": False, "steps": ["icon"]}
    result = image_gen.dispatch("generate_character_assets", args)

    assert result == {"generated": True}
    pipeline_class.assert_called_once_with(anima_dir, config=_IMAGE_CONFIG)
    pipeline.generate_all.assert_called_once_with(
        prompt="character", negative_prompt="", skip_existing=False, steps=["icon"], animations=None
    )
    assert "anima_dir" not in args


def test_image_dispatch_fullbody_golden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_image_config(monkeypatch)
    client = MagicMock()
    client.generate_fullbody.return_value = b"fullbody"
    client_class = MagicMock(return_value=client)
    monkeypatch.setattr(image_gen, "_build_fullbody_client", client_class)
    anima_dir = tmp_path / "mei"

    result = image_gen.dispatch("generate_fullbody", {"anima_dir": str(anima_dir), "prompt": "prompt", "seed": 9})

    expected_path = anima_dir / "assets" / "avatar_fullbody.png"
    client_class.assert_called_once_with(_IMAGE_CONFIG)
    client.generate_fullbody.assert_called_once_with(
        prompt="prompt", negative_prompt="", width=1024, height=1536, seed=9
    )
    assert result == {"path": str(expected_path), "size": len(b"fullbody")}
    assert expected_path.read_bytes() == b"fullbody"


def test_image_dispatch_bustup_golden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_image_config(monkeypatch)
    anima_dir = tmp_path / "mei"
    assets_dir = anima_dir / "assets"
    assets_dir.mkdir(parents=True)
    reference = assets_dir / "avatar_fullbody.png"
    reference.write_bytes(b"reference")
    client = MagicMock()
    client.generate_from_reference.return_value = b"bustup"
    client_class = MagicMock(return_value=client)
    monkeypatch.setattr(image_gen, "_build_reference_client", client_class)

    result = image_gen.dispatch("generate_bustup", {"anima_dir": str(anima_dir), "prompt": "pose"})

    client_class.assert_called_once_with(_IMAGE_CONFIG)
    client.generate_from_reference.assert_called_once_with(
        reference_image=b"reference", prompt="pose", aspect_ratio="3:4"
    )
    assert result == {"path": str(assets_dir / "avatar_bustup.png"), "size": len(b"bustup")}


def test_image_dispatch_chibi_golden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_image_config(monkeypatch)
    anima_dir = tmp_path / "mei"
    assets_dir = anima_dir / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "avatar_fullbody.png").write_bytes(b"fullbody-ref")
    client = MagicMock()
    client.generate_from_reference.return_value = b"chibi"
    client_class = MagicMock(return_value=client)
    monkeypatch.setattr(image_gen, "_build_reference_client", client_class)

    result = image_gen.dispatch("generate_chibi", {"anima_dir": str(anima_dir), "prompt": "cute"})

    client_class.assert_called_once_with(_IMAGE_CONFIG)
    client.generate_from_reference.assert_called_once_with(
        reference_image=b"fullbody-ref", prompt="cute", aspect_ratio="1:1"
    )
    assert result == {"path": str(assets_dir / "avatar_chibi.png"), "size": len(b"chibi")}


def test_image_dispatch_3d_model_golden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    anima_dir = tmp_path / "mei"
    assets_dir = anima_dir / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "avatar_chibi.png").write_bytes(b"chibi")
    client = MagicMock()
    client.create_task.return_value = "task-1"
    client.poll_task.return_value = {"status": "done"}
    client.download_model.return_value = b"glb"
    client_class = MagicMock(return_value=client)
    monkeypatch.setattr(image_gen, "MeshyClient", client_class)

    result = image_gen.dispatch(
        "generate_3d_model",
        {"anima_dir": str(anima_dir), "ai_model": "meshy-5", "target_polycount": 1234},
    )

    client.create_task.assert_called_once_with(b"chibi", ai_model="meshy-5", target_polycount=1234)
    client.poll_task.assert_called_once_with("task-1")
    client.download_model.assert_called_once_with({"status": "done"}, fmt="glb")
    assert result == {"path": str(assets_dir / "avatar_chibi.glb"), "size": 3, "task_id": "task-1"}


def test_image_dispatch_rigged_model_golden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    anima_dir = tmp_path / "mei"
    assets_dir = anima_dir / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "avatar_chibi.glb").write_bytes(b"model")
    client = MagicMock()
    client._headers.return_value = {"Authorization": "Bearer test"}
    client.poll_rigging_task.return_value = {"id": "rig-task"}
    client.download_rigged_model.return_value = b"rigged"
    client.download_rigging_animations.return_value = {"walk": b"walk"}
    monkeypatch.setattr(image_gen, "MeshyClient", MagicMock(return_value=client))
    monkeypatch.setattr(image_gen, "_image_to_data_uri", lambda data, mime: f"data:{mime}:{data.decode()}")
    response = MagicMock()
    response.json.return_value = {"result": "rig-task-id"}
    post = MagicMock(return_value=response)
    monkeypatch.setattr(image_gen.httpx, "post", post)

    result = image_gen.dispatch("generate_rigged_model", {"anima_dir": str(anima_dir), "height_meters": 1.7})

    post.assert_called_once_with(
        image_gen.MESHY_RIGGING_URL,
        json={"model_url": "data:model/gltf-binary:model", "height_meters": 1.7},
        headers={"Authorization": "Bearer test"},
        timeout=image_gen._HTTP_TIMEOUT,
    )
    client.poll_rigging_task.assert_called_once_with("rig-task-id")
    client.download_rigged_model.assert_called_once_with({"id": "rig-task"}, fmt="glb")
    client.download_rigging_animations.assert_called_once_with({"id": "rig-task"})
    assert result == {
        "rigged_model": str(assets_dir / "avatar_chibi_rigged.glb"),
        "animations": {"walk": str(assets_dir / "anim_walk.glb")},
        "rig_task_id": "rig-task-id",
    }


def test_image_dispatch_animations_golden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    anima_dir = tmp_path / "mei"
    assets_dir = anima_dir / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "avatar_chibi.glb").write_bytes(b"model")
    client = MagicMock()
    client._headers.return_value = {"Authorization": "Bearer test"}
    client.create_animation_task.return_value = "anim-task"
    client.poll_animation_task.return_value = {"id": "anim-task"}
    client.download_animation.return_value = b"animation"
    monkeypatch.setattr(image_gen, "MeshyClient", MagicMock(return_value=client))
    monkeypatch.setattr(image_gen, "_image_to_data_uri", lambda data, mime: f"data:{mime}:{data.decode()}")
    response = MagicMock()
    response.json.return_value = {"result": "rig-task-id"}
    post = MagicMock(return_value=response)
    monkeypatch.setattr(image_gen.httpx, "post", post)

    result = image_gen.dispatch(
        "generate_animations",
        {"anima_dir": str(anima_dir), "animations": {"idle": "action-id"}},
    )

    client.poll_rigging_task.assert_called_once_with("rig-task-id")
    client.create_animation_task.assert_called_once_with("rig-task-id", "action-id")
    client.poll_animation_task.assert_called_once_with("anim-task")
    client.download_animation.assert_called_once_with({"id": "anim-task"}, fmt="glb")
    assert result == {
        "animations": {"idle": str(assets_dir / "anim_idle.glb")},
        "rig_task_id": "rig-task-id",
    }


def test_image_dispatch_unknown_name_preserves_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown tool: missing"):
        image_gen.dispatch("missing", {})


def test_cli_main_safely_reports_unhandled_error(capsys) -> None:
    from core.integrations._comm_cli import cli_main_safely

    def fail(_value: str) -> None:
        raise RuntimeError("expected failure")

    safe_cli = cli_main_safely(fail)
    with pytest.raises(SystemExit) as exc_info:
        safe_cli("input")

    assert exc_info.value.code == 1
    assert capsys.readouterr().err == "Error: expected failure\n"


def test_cli_main_safely_preserves_explicit_exit_code() -> None:
    from core.integrations._comm_cli import cli_main_safely

    safe_cli = cli_main_safely(lambda: (_ for _ in ()).throw(SystemExit(2)))
    with pytest.raises(SystemExit) as exc_info:
        safe_cli()

    assert exc_info.value.code == 2


def test_notion_cli_preserves_api_error_message(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from core.integrations import notion

    monkeypatch.setattr(notion, "_resolve_cli_token", lambda: "token")
    monkeypatch.setattr(notion, "NotionClient", MagicMock())
    monkeypatch.setattr(
        notion,
        "_run_cli_command",
        MagicMock(side_effect=notion.NotionAPIError("API failed")),
    )

    with pytest.raises(SystemExit) as exc_info:
        notion.cli_main(["search", "query"])

    assert exc_info.value.code == 1
    assert capsys.readouterr().err == "Notion API error: API failed\n"
