# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio

import pytest

from cli.tui.app import AnimaChatApp


class FakeClient:
    """A stub AnimaWorksClient with Phase 2 methods."""

    def __init__(
        self,
        *,
        animas=None,
        history=None,
        skills=None,
        active_refs=None,
    ):
        self.animas = animas or [
            {"name": "sora", "status": "running", "busy": None},
            {"name": "rin", "status": "running", "busy": None},
            {"name": "mei", "status": "running", "busy": None},
        ]
        self.history = history or {"sessions": []}
        self.skills = skills or []
        self.active_refs = active_refs or []
        self._ws_queue: asyncio.Queue = asyncio.Queue()
        self.history_calls: list[str] = []
        self.skill_calls: list[str] = []
        self.active_calls: list[str] = []
        self.set_active_calls: list = []
        self.resolve_calls: list = []
        self.chat_queue: asyncio.Queue = asyncio.Queue()
        self.messages: list = []
        self.post_calls: list = []
        self.board_calls: list = []
        self.tasks_calls: list = []

    def push_ws(self, event_type: str, data: dict) -> None:
        self._ws_queue.put_nowait({"type": event_type, "data": data})

    async def list_animas(self):
        return self.animas

    async def get_history(self, anima, *, thread_id="default", limit=50):
        self.history_calls.append(anima)
        return self.history

    async def interrupt(self, anima, *, thread_id):
        return {"status": "interrupted"}

    async def chat_stream(self, anima, message, *, thread_id="default", resume=None, last_event_id=None):
        self.messages.append((anima, message))
        while True:
            ev = await self.chat_queue.get()
            if ev is None:
                return
            yield ev

    async def ws_events(self):
        while True:
            ev = await self._ws_queue.get()
            if ev is None:
                return
            yield ev

    async def list_skills(self, anima, thread_id="default"):
        self.skill_calls.append(anima)
        return {"anima": anima, "thread_id": thread_id, "skills": self.skills}

    async def get_active_skills(self, anima, thread_id="default"):
        self.active_calls.append(anima)
        return {
            "anima": anima,
            "thread_id": thread_id,
            "accepted": [{"ref": r, "name": r, "active": True} for r in self.active_refs],
            "rejections": [],
            "warnings": [],
        }

    async def set_active_skills(self, anima, thread_id="default", refs=None, confirm_risk=False):
        self.set_active_calls.append((anima, thread_id, list(refs or []), confirm_risk))
        return {
            "accepted": [{"ref": r, "name": r, "active": True} for r in (refs or [])],
            "rejections": [],
            "warnings": [],
        }

    async def list_channels(self):
        return [{"name": "dev", "message_count": 2}]

    async def read_channel(self, name, limit=50):
        self.board_calls.append((name, limit))
        return {"channel": name, "messages": [{"from": "mei", "ts": "2026-01-01T10:00:00", "text": "hello"}]}

    async def post_channel(self, name, text):
        self.post_calls.append((name, text))
        return {"status": "ok", "channel": name}

    async def list_tasks(self, assignee=None):
        self.tasks_calls.append(assignee)
        return {"tasks": [{"title": "a task", "status": "todo"}]}

    async def resolve_interaction(self, anima, callback_id, decision, comment=""):
        self.resolve_calls.append((anima, callback_id, decision))
        return {"status": "ok", "decision": decision}


async def _pump(n=80):
    for _ in range(n):
        await asyncio.sleep(0)


def _app(client, anima="sora"):
    return AnimaChatApp(client=client, anima_name=anima)


# ── (a) sidebar shows all animas, ws status changes badge ──
@pytest.mark.asyncio
async def test_sidebar_lists_all_animas_and_ws_status_changes_badge():
    client = FakeClient()
    app = _app(client)
    async with app.run_test() as _:
        await _pump()
        assert set(app.state.animas) >= {"sora", "rin", "mei"}
        client.push_ws("anima.status", {"name": "rin", "status": "thinking"})
        await _pump()
        assert app.state.animas["rin"].status == "thinking"


# ── (b)(c) palette opens with skills and filters ──
@pytest.mark.asyncio
async def test_palette_opens_and_lists_skills_then_filters():
    skills = [
        {
            "ref": "pr",
            "name": "pr-review",
            "description": "review a PR",
            "active": False,
            "is_common": False,
            "is_procedure": False,
        },
    ]
    client = FakeClient(skills=skills)
    app = _app(client)
    async with app.run_test() as pilot:
        await _pump()
        app.input_container.focus_input()
        await pilot.press("/")
        await _pump()
        assert app.palette.is_open
        values = {it.value for it in app._palette_items()}
        assert "/skill pr-review" in values

        # Narrow to the skill — candidate count must drop and the skill remain.
        await pilot.press("p", "r")
        await _pump()
        assert app.palette.is_open
        items = app._palette_items()
        filtered = [it for it in items if "/skill pr-review" in it.value]
        assert filtered
        # every remaining item matches the query
        for it in app.palette._items:
            assert it.matches("pr")
        # clean up the ws worker
        client.push_ws("anima.status", {"name": "rin", "status": "idle"})


# ── (d) /skill foo sets active skills with existing refs + foo ──
@pytest.mark.asyncio
async def test_skill_command_replaces_with_existing_plus_new():
    skills = [
        {
            "ref": "foo-ref",
            "name": "foo",
            "description": "d",
            "active": False,
            "is_common": False,
            "is_procedure": False,
        },
    ]
    client = FakeClient(skills=skills, active_refs=["existing-ref"])
    app = _app(client)
    async with app.run_test() as _:
        await _pump()
        await app._handle_message("/skill foo")
        await _pump()
        assert client.set_active_calls, "set_active_skills was not called"
        anima, thread_id, refs, confirm = client.set_active_calls[-1]
        assert anima == "sora"
        assert set(refs) == {"existing-ref", "foo-ref"}
        assert confirm is False


# ── (e) /anima rin switches, history fetched for rin ──
@pytest.mark.asyncio
async def test_switch_anima_loads_rin_history():
    client = FakeClient()
    app = _app(client)
    async with app.run_test() as _:
        await _pump()
        assert "sora" in client.history_calls
        await app._handle_message("/anima rin")
        await _pump()
        assert app.anima_name == "rin"
        assert app.state.current == "rin"
        assert client.history_calls[-1] == "rin"


# ── (f) switching is rejected while busy ──
@pytest.mark.asyncio
async def test_switch_rejected_while_busy():
    client = FakeClient()
    app = _app(client)
    async with app.run_test() as _:
        await _pump()
        app.busy = True
        await app._handle_message("/anima rin")
        await _pump()
        assert app.anima_name == "sora"
        assert app.state.current == "sora"
        assert app.busy is True


# ── (g) proactive: unread for other anima, transcript for current ──
@pytest.mark.asyncio
async def test_proactive_other_anima_increments_unread():
    client = FakeClient()
    app = _app(client)
    async with app.run_test() as _:
        await _pump()
        client.push_ws(
            "anima.proactive_message",
            {"anima": "rin", "subject": "subj", "body": "need you"},
        )
        await _pump()
        assert app.state.animas["rin"].unread == 1
        assert app.state.animas["sora"].unread == 0


@pytest.mark.asyncio
async def test_proactive_current_anima_renders_in_transcript():
    client = FakeClient()
    app = _app(client)
    async with app.run_test() as _:
        await _pump()
        client.push_ws(
            "anima.proactive_message",
            {"anima": "sora", "subject": "subj", "body": "hello there"},
        )
        await _pump()
        from cli.tui.widgets import AssistantBlock

        blocks = list(app.query(AssistantBlock))
        assert blocks, "no assistant block rendered"
        assert any("hello there" in b._body for b in blocks)
