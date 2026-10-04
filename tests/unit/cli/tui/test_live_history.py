# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Turns made while the TUI is open — elsewhere or in the background — show up live."""

from __future__ import annotations

import asyncio

import pytest

from cli.tui.app import AnimaChatApp
from cli.tui.sse import SseEvent
from cli.tui.widgets import AssistantBlock, HumanTurn, SystemNote
from tests.unit.cli.tui.test_app import FakeClient
from tests.unit.cli.tui.test_transcript_display import _colours, _rendered_plain


async def _settle(pilot, rounds=8):
    for _ in range(rounds):
        await pilot.pause()
        await asyncio.sleep(0.02)


def _page(*messages):
    return {"sessions": [{"messages": list(messages)}]}


def _msg(ts, role, content, **extra):
    return {"ts": ts, "role": role, "content": content, **extra}


OPENING = _msg("2026-10-04T10:00:00", "human", "最初の発言")


@pytest.mark.asyncio
async def test_poll_appends_turns_from_other_sessions_and_background():
    client = FakeClient(history=_page(OPENING))
    app = AnimaChatApp(client=client, anima_name="sora")
    async with app.run_test() as pilot:
        await _settle(pilot)
        assert len(list(app.query(HumanTurn))) == 1

        client.history = _page(
            OPENING,
            _msg("2026-10-04T10:01:00", "human", "WEBから送った質問"),
            _msg("2026-10-04T10:01:30", "assistant", "WEBへの返答"),
            _msg("2026-10-04T10:02:00", "system", "コマンド: 巡回", source_key="cron"),
            _msg(
                "2026-10-04T10:03:00",
                "system",
                "確認をお願いします",
                type="human_notify",
                source_key="call_human",
                subject="承認依頼",
            ),
            _msg("2026-10-04T10:04:00", "human", "OKです", type="human_reply", via="slack"),
        )
        await app.poll_history()
        await _settle(pilot)

        humans = list(app.query(HumanTurn))
        assert [h._text for h in humans] == ["最初の発言", "WEBから送った質問", "OKです"]
        assert humans[-1]._label == "You (via slack)"
        assert [b._body for b in app.query(AssistantBlock)] == ["WEBへの返答"]
        notes = list(app.query(SystemNote))
        assert [n._text for n in notes] == ["コマンド: 巡回", "確認をお願いします"]

        # call_human is meant for the reader: not drawn in the faint grey.
        call_human = notes[1]
        assert call_human.label_widget.render().plain == "system · call_human — 承認依頼"
        assert "確認をお願いします" in _rendered_plain(call_human.message)
        assert 8 not in _colours(call_human.message)

        # Polling the same page again adds nothing.
        await app.poll_history()
        await _settle(pilot)
        assert len(list(app.query(HumanTurn))) == 3
        assert len(list(app.query(SystemNote))) == 2


@pytest.mark.asyncio
async def test_poll_does_not_duplicate_this_clients_own_turn():
    client = FakeClient(history=_page(OPENING))
    app = AnimaChatApp(client=client, anima_name="sora")
    async with app.run_test() as pilot:
        await _settle(pilot)
        await app.send_message("TUIからの質問")
        await client.chat_queue.put(SseEvent(event="done", data={"summary": "TUIへの<!-- emotion: {} -->返答"}))
        await client.chat_queue.put(None)
        await _settle(pilot)
        assert not app.busy

        client.history = _page(
            OPENING,
            _msg("2026-10-04T10:05:00", "human", "TUIからの質問"),
            _msg("2026-10-04T10:05:20", "assistant", "TUIへの返答"),
            _msg("2026-10-04T10:06:00", "system", "定期巡回開始", source_key="heartbeat"),
        )
        await app.poll_history()
        await _settle(pilot)

        assert [h._text for h in app.query(HumanTurn)] == ["最初の発言", "TUIからの質問"]
        assert len(list(app.query(AssistantBlock))) == 1
        assert [n._text for n in app.query(SystemNote)] == ["定期巡回開始"]


@pytest.mark.asyncio
async def test_poll_is_skipped_while_a_response_is_streaming():
    client = FakeClient(history=_page(OPENING))
    app = AnimaChatApp(client=client, anima_name="sora")
    async with app.run_test() as pilot:
        await _settle(pilot)
        await app.send_message("考え中の質問")
        await _settle(pilot)
        assert app.busy

        client.history = _page(OPENING, _msg("2026-10-04T10:07:00", "system", "cron", source_key="cron"))
        await app.poll_history()
        await _settle(pilot)
        assert list(app.query(SystemNote)) == []

        await client.chat_queue.put(SseEvent(event="done", data={"summary": "答え"}))
        await client.chat_queue.put(None)
        await _settle(pilot)
        await app.poll_history()
        await _settle(pilot)
        assert [n._text for n in app.query(SystemNote)] == ["cron"]
