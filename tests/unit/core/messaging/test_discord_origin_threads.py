"""Discord origin carried across internal Anima threads."""

from __future__ import annotations

from types import SimpleNamespace

from core.messaging.discord_origin_threads import (
    active_origin,
    lookup_origin,
    record_origin,
    set_active_origin,
)
from core.messaging.outbound_auto import DiscordAutoResponder

ORIGIN = {"channel_id": "100", "thread_ts": "200", "user_id": "300"}


def test_record_and_lookup(tmp_path):
    record_origin(tmp_path, "t1", ORIGIN)
    found = lookup_origin(tmp_path, "t1")
    assert found is not None
    assert (found["channel_id"], found["thread_ts"], found["user_id"]) == ("100", "200", "300")
    assert lookup_origin(tmp_path, "other") is None
    assert lookup_origin(tmp_path, "") is None


def test_record_ignores_missing_channel(tmp_path):
    record_origin(tmp_path, "t1", {"channel_id": ""})
    assert lookup_origin(tmp_path, "t1") is None


def test_active_origin_only_in_inbox_sessions(tmp_path, monkeypatch):
    monkeypatch.delenv("ANIMAWORKS_SESSION_TYPE", raising=False)
    set_active_origin(tmp_path, ORIGIN)
    assert active_origin(tmp_path, {}, "heartbeat") == {}
    assert active_origin(tmp_path, {}, "inbox:discord")["channel_id"] == "100"

    monkeypatch.setenv("ANIMAWORKS_SESSION_TYPE", "inbox")
    assert active_origin(tmp_path, {}, "")["channel_id"] == "100"

    set_active_origin(tmp_path, None)
    assert active_origin(tmp_path, {}, "") == {}


def test_linked_origin_becomes_target():
    item = SimpleNamespace(msg=SimpleNamespace(source="anima"))
    targets = DiscordAutoResponder._collect_discord_targets([item], set(), [ORIGIN, dict(ORIGIN)])
    assert targets == [{"channel_id": "100", "thread_id": "200", "mention_prefix": "<@300> "}]


def test_linked_origin_deduplicated_with_discord_item():
    item = SimpleNamespace(
        msg=SimpleNamespace(
            source="discord",
            external_channel_id="100",
            external_thread_ts="200",
            external_user_id="300",
            from_name="x",
        )
    )
    targets = DiscordAutoResponder._collect_discord_targets([item], set(), [ORIGIN])
    assert len(targets) == 1
