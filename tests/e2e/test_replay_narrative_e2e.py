# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""E2E smoke coverage for workspace replay narrative."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = REPO_ROOT / "server" / "static" / "workspace"
REPLAY_ENGINE_JS = WORKSPACE / "modules" / "replay-engine.js"
REPLAY_UI_JS = WORKSPACE / "modules" / "replay-ui.js"
ORG_DASHBOARD_JS = WORKSPACE / "modules" / "org-dashboard.js"
STYLE_CSS = WORKSPACE / "style.css"


class TestReplayNarrativeBand:
    """Narrative state mirrors the visible semantic event at the replay cursor."""

    ONE_HOUR_MS = 60 * 60 * 1000

    def event_time_ms(self, evt: dict) -> int:
        ts = evt.get("ts") or evt.get("timestamp")
        if ts:
            return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
        return 0

    def build_narrative_state(self, events: list[dict], current_ms: int) -> dict:
        visible = [
            evt
            for evt in events
            if evt.get("kind") and int(evt.get("importance") or 0) >= 2
        ]
        current_event = None
        current_index = -1
        for idx, evt in enumerate(visible):
            if self.event_time_ms(evt) > current_ms:
                break
            current_event = evt
            current_index = idx

        active_group_id = current_event.get("group_id", "") if current_event else ""
        suppressed_count = sum(
            int(evt.get("debug", {}).get("suppressed_count") or 0)
            for evt in events
            if active_group_id and evt.get("group_id") == active_group_id
        )
        hour_before = current_ms - self.ONE_HOUR_MS
        visible_events_in_last_hour = sum(
            1 for evt in visible if hour_before <= self.event_time_ms(evt) <= current_ms
        )
        return {
            "currentEvent": current_event,
            "currentIndex": current_index,
            "totalEvents": len(visible),
            "visibleEventsInLastHour": visible_events_in_last_hour,
            "activeGroupId": active_group_id,
            "activeGroupType": current_event.get("group_type", "") if current_event else "",
            "suppressedCount": suppressed_count,
        }

    def test_narrative_state_selects_latest_visible_semantic_event(self):
        now = datetime.now(UTC).replace(microsecond=0)
        events = [
            {
                "id": "hidden",
                "ts": (now - timedelta(minutes=30)).isoformat(),
                "kind": "heartbeat",
                "importance": 1,
                "group_id": "g-hidden",
            },
            {
                "id": "first",
                "ts": (now - timedelta(minutes=20)).isoformat(),
                "kind": "message",
                "importance": 2,
                "group_id": "g1",
                "group_type": "conversation",
                "debug": {"suppressed_count": 2},
            },
            {
                "id": "future",
                "ts": (now + timedelta(minutes=5)).isoformat(),
                "kind": "response",
                "importance": 3,
                "group_id": "g1",
                "debug": {"suppressed_count": 3},
            },
        ]
        state = self.build_narrative_state(events, int(now.timestamp() * 1000))
        assert state["currentEvent"]["id"] == "first"
        assert state["currentIndex"] == 0
        assert state["totalEvents"] == 2
        assert state["visibleEventsInLastHour"] == 1
        assert state["activeGroupId"] == "g1"
        assert state["suppressedCount"] == 5

    def test_workspace_replay_narrative_smoke_contract(self):
        engine = REPLAY_ENGINE_JS.read_text(encoding="utf-8")
        ui = REPLAY_UI_JS.read_text(encoding="utf-8")
        dashboard = ORG_DASHBOARD_JS.read_text(encoding="utf-8")
        css = STYLE_CSS.read_text(encoding="utf-8")

        assert "_buildNarrativeState" in engine
        assert "onNarrativeUpdate" in engine
        assert "orgReplayNarrative" in ui
        assert "updateNarrative(state" in ui
        assert "No activity at this time" in ui
        assert "onNarrativeUpdate: _handleNarrativeUpdate" in dashboard
        assert "_showSemanticReplayLine(state.currentEvent" in dashboard
        assert ".org-replay-narrative" in css
        assert ".org-replay-row" in css
