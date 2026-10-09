# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Debate threads: registry, delivery plans and gateway routing inside a registered thread."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.messaging.outbound_auto import prepare_auto_response_text
from server.gateways import discord_debate_threads as D
from server.gateways import discord_gateway as G

PARTICIPANTS = ["airi", "rika", "momoka", "sakura"]
THREAD, PARENT = "900", "100"


def _entry(**extra):
    entry = {
        "participants": PARTICIPANTS,
        "record": "common_knowledge/market_now/run.md",
        "title": "Market Now 10/09 14:11",
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }
    entry.update(extra)
    return entry


# ── module ───────────────────────────────────────────────


class TestRegistry:
    def test_live_entry_is_found_and_expired_one_is_not(self, tmp_path):
        (tmp_path / D.REGISTRY_NAME).write_text(
            json.dumps({THREAD: _entry(), "901": _entry(expires_at="2020-01-01T00:00:00+00:00")}),
            encoding="utf-8",
        )
        assert D.load_entry(THREAD, shared_dir=tmp_path)["title"] == "Market Now 10/09 14:11"
        assert D.load_entry("901", shared_dir=tmp_path) is None
        assert D.load_entry("902", shared_dir=tmp_path) is None

    def test_missing_or_broken_registry_is_ignored(self, tmp_path):
        assert D.load_entry(THREAD, shared_dir=tmp_path) is None
        (tmp_path / D.REGISTRY_NAME).write_text("{broken", encoding="utf-8")
        assert D.load_entry(THREAD, shared_dir=tmp_path) is None

    def test_record_path_stays_inside_common_knowledge(self, tmp_path):
        assert D.record_path(_entry(record="common_knowledge/../secrets.md"), ck_dir=tmp_path) is None
        assert D.record_path(_entry(record="knowledge/x.md"), ck_dir=tmp_path) is None
        assert D.record_path(_entry(), ck_dir=tmp_path) == (tmp_path / "market_now" / "run.md").resolve()


class TestPlans:
    def test_human_message_reaches_everyone_addressed_first(self):
        plan = D.plan_human_deliveries(_entry(), ["momoka"])
        assert plan == [("momoka", True), ("airi", False), ("rika", False), ("sakura", False)]

    def test_non_participant_target_is_not_required(self):
        assert all(not req for _, req in D.plan_human_deliveries(_entry(), ["ayane"]))

    def test_anima_post_reaches_only_named_others(self):
        assert D.plan_anima_deliveries(_entry(), "airi", ["airi", "rika", "ayane", "rika"]) == [("rika", True)]

    def test_turn_budget_resets_on_each_human_message(self):
        D.start_human_turn("t-budget")
        assert [D.take_anima_turn("t-budget") for _ in range(D.MAX_ANIMA_TURNS + 1)] == [True] * D.MAX_ANIMA_TURNS + [False]
        D.start_human_turn("t-budget")
        assert D.take_anima_turn("t-budget")

    def test_delivery_fits_inbox_budget_and_says_what_to_do(self):
        history = [("airi", "あ" * 500)] * 10
        required = D.build_delivery(_entry(), target="rika", required=True, author="cmnt", text="い" * 3000, history=history)
        optional = D.build_delivery(_entry(), target="momoka", required=False, author="cmnt", text="質問", history=[])
        assert len(required) < 2000
        assert "common_knowledge/market_now/run.md" in required and "必ず答える" in required
        assert D.PASS_TOKEN in optional

    def test_pass_is_never_posted(self):
        for text in ("[[PASS]]", " `[[PASS]]` ", "**[[PASS]]**\n"):
            assert prepare_auto_response_text(text) == ""
        assert prepare_auto_response_text("[[PASS]] ではなく反論します") != ""


# ── gateway routing ──────────────────────────────────────


class FakeMessenger:
    deliveries: list[tuple[str, dict]] = []

    def __init__(self, shared_dir, name):
        self.name = name

    def receive_external(self, **kwargs):
        FakeMessenger.deliveries.append((self.name, kwargs))

    def post_channel(self, *args, **kwargs):
        pass


class FakeChannel:
    def __init__(self, thread=True):
        self.id = int(THREAD) if thread else int(PARENT)
        self.parent_id = int(PARENT) if thread else None
        self.name = "market-now"

    def history(self, **kwargs):
        async def gen():
            for name, text in [("momoka", "VIX25 で 25C が効く"), ("airi", "要約です")]:
                yield SimpleNamespace(author=SimpleNamespace(display_name=name, name=name), content=text)
        return gen()


def _message(text, *, author="cmnt", webhook=False, thread=True):
    return SimpleNamespace(
        id=int(uuid.uuid4().int % 10**15),
        author=SimpleNamespace(id=7 if not webhook else 8, display_name=author, name=author),
        webhook_id=1 if webhook else None,
        content=text,
        mentions=[],
        channel=FakeChannel(thread),
        guild=object(),
        reference=None,
    )


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    discord_cfg = SimpleNamespace(
        channel_members={PARENT: ["sakura", "ayane", "momoka", "airi", "rika"]},
        anima_mapping={}, board_mapping={}, default_anima="sakura", system_agents={},
    )
    cfg = SimpleNamespace(
        animas={name: SimpleNamespace(aliases=[]) for name in [*PARTICIPANTS, "ayane"]},
        external_messaging=SimpleNamespace(discord=discord_cfg, user_aliases=[]),
    )
    monkeypatch.setattr(G, "load_config", lambda: cfg)
    for name in [*PARTICIPANTS, "ayane"]:
        (tmp_path / "animas" / name).mkdir(parents=True)
    monkeypatch.setattr(G, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(G, "get_shared_dir", lambda: tmp_path)
    monkeypatch.setattr(G, "Messenger", FakeMessenger)
    record = tmp_path / "ck" / "market_now" / "run.md"
    record.parent.mkdir(parents=True)
    record.write_text("# 記録\n", encoding="utf-8")
    monkeypatch.setattr(D, "_common_knowledge_dir", lambda: tmp_path / "ck")
    monkeypatch.setattr(D, "load_entry", lambda thread_id, **_: _entry() if str(thread_id) == THREAD else None)
    FakeMessenger.deliveries = []
    mgr = G.DiscordGatewayManager()
    mgr._bot_user_id = 1
    mgr._build_anima_patterns()
    return mgr, record


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestGatewayInDebateThread:
    def test_unaddressed_human_message_goes_to_all_with_sakura_required(self, gateway):
        mgr, record = gateway
        _run(mgr._handle_message(_message("金利の見方は？")))
        plan = {name: "必ず答える" in kw["content"] for name, kw in FakeMessenger.deliveries}
        assert plan == {"sakura": True, "airi": False, "rika": False, "momoka": False}
        assert all(kw["external_thread_ts"] == THREAD and kw["external_channel_id"] == PARENT
                   for _, kw in FakeMessenger.deliveries)
        assert "VIX25 で 25C が効く" in FakeMessenger.deliveries[0][1]["content"]   # recent flow included
        assert "金利の見方は？" in record.read_text(encoding="utf-8")

    def test_named_participant_is_required(self, gateway):
        mgr, _ = gateway
        _run(mgr._handle_message(_message("rika、その数字の出典は？")))
        required = [name for name, kw in FakeMessenger.deliveries if "必ず答える" in kw["content"]]
        assert required == ["rika"]

    def test_anima_post_naming_another_relays_within_budget(self, gateway):
        mgr, record = gateway
        _run(mgr._handle_message(_message("どう？")))
        FakeMessenger.deliveries = []
        for _ in range(D.MAX_ANIMA_TURNS + 1):
            _run(mgr._handle_message(_message("momoka、反論ある？", author="airi", webhook=True)))
        assert [name for name, _ in FakeMessenger.deliveries] == ["momoka"] * D.MAX_ANIMA_TURNS
        assert record.read_text(encoding="utf-8").count("momoka、反論ある？") == D.MAX_ANIMA_TURNS + 1

    def test_outside_debate_threads_routing_is_unchanged(self, gateway):
        mgr, _ = gateway
        _run(mgr._handle_message(_message("こんにちは", thread=False)))
        assert [name for name, _ in FakeMessenger.deliveries] == ["sakura"]
        assert "必ず答える" not in FakeMessenger.deliveries[0][1]["content"]
