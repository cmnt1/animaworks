# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for workspace replay narrative UI."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = REPO_ROOT / "server" / "static" / "workspace"
REPLAY_ENGINE_JS = WORKSPACE / "modules" / "replay-engine.js"
REPLAY_UI_JS = WORKSPACE / "modules" / "replay-ui.js"
ORG_DASHBOARD_JS = WORKSPACE / "modules" / "org-dashboard.js"
STYLE_CSS = WORKSPACE / "style.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestReplayNarrativeEngine:
    def test_narrative_callback_contract(self):
        src = _read(REPLAY_ENGINE_JS)
        for token in ("onNarrativeUpdate", "_onNarrativeUpdate", "_buildNarrativeState", "_emitNarrativeUpdate"):
            assert token in src
        for field in (
            "currentTimeMs",
            "currentEvent",
            "currentIndex",
            "totalEvents",
            "visibleEventsInLastHour",
            "activeGroupId",
            "activeGroupType",
            "suppressedCount",
        ):
            assert field in src, f"Narrative state must include {field}"

    def test_narrative_state_uses_visible_semantic_events(self):
        src = _read(REPLAY_ENGINE_JS)
        assert "const visibleEvents = this._visibleEvents()" in src
        assert "evt?.kind && isVisibleReplayEvent(evt)" in src
        assert "Number(evt.importance || 0) >= 2" in src
        assert "_eventIndexAtOrBefore(visibleEvents, currentTimeMs)" in src
        assert "_firstEventIndexAtOrAfter(visibleEvents, hourBeforeT)" in src
        assert "let out = -1" in src
        assert "debug?.suppressed_count" in src

    def test_narrative_update_emitted_on_load_seek_tick_and_complete(self):
        src = _read(REPLAY_ENGINE_JS)
        assert "this._emitNarrativeUpdate();" in src
        assert src.count("this._emitNarrativeUpdate();") >= 4
        assert "this._onNarrativeUpdate(this._buildNarrativeState" in src


class TestReplayNarrativeUI:
    def test_update_narrative_method(self):
        src = _read(REPLAY_UI_JS)
        assert re.search(r"\bupdateNarrative\s*\([^)]*\)\s*\{", src)
        assert "state.currentEvent" in src
        assert "suppressedCount" in src

    def test_narrative_dom_contract(self):
        src = _read(REPLAY_UI_JS)
        for cls in (
            "org-replay-narrative",
            "org-replay-narrative-main",
            "org-replay-narrative-kind",
            "org-replay-narrative-label",
            "org-replay-narrative-summary",
            "org-replay-narrative-meta",
            "org-replay-narrative-route",
            "org-replay-narrative-group",
            "org-replay-narrative-status",
            "org-replay-narrative-count",
        ):
            assert cls in src, f"Replay narrative DOM must include {cls}"

    def test_narrative_empty_state(self):
        src = _read(REPLAY_UI_JS)
        assert "No activity at this time" in src
        assert "`0 / ${total}`" in src
        assert '"0 / 0"' in src


class TestReplayNarrativeDashboard:
    def test_wires_narrative_callback(self):
        src = _read(ORG_DASHBOARD_JS)
        assert "onNarrativeUpdate: _handleNarrativeUpdate" in src
        assert "function _handleNarrativeUpdate(state)" in src
        assert "_replayUI?.updateNarrative(state)" in src

    def test_seek_narrative_draws_stable_line_when_paused(self):
        src = _read(ORG_DASHBOARD_JS)
        assert '_msgLinesGroup.innerHTML = ""' in src
        assert "_replayEngine?.isPlaying()" in src
        assert "_showSemanticReplayLine(state.currentEvent" in src


class TestReplayNarrativeCSS:
    def test_org_replay_narrative_styles(self):
        src = _read(STYLE_CSS)
        for selector in (
            ".org-replay-row",
            ".org-replay-narrative",
            ".org-replay-narrative-main",
            ".org-replay-narrative-meta",
            ".org-replay-narrative [hidden]",
        ):
            assert selector in src, f"CSS must define {selector}"
        assert "min-height: 48px" in src
        assert "text-overflow: ellipsis" in src
