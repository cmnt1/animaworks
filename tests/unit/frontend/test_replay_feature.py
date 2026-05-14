# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Dashboard replay feature."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]  # tests/unit/frontend/ → root

# Paths
REPLAY_ENGINE_JS = REPO_ROOT / "server" / "static" / "workspace" / "modules" / "replay-engine.js"
REPLAY_UI_JS = REPO_ROOT / "server" / "static" / "workspace" / "modules" / "replay-ui.js"
ACTIVITY_NORMALIZE_JS = REPO_ROOT / "server" / "static" / "workspace" / "modules" / "activity-normalize.js"
ORG_DASHBOARD_JS = REPO_ROOT / "server" / "static" / "workspace" / "modules" / "org-dashboard.js"
APP_WS_JS = REPO_ROOT / "server" / "static" / "workspace" / "modules" / "app-websocket.js"
APP_JS = REPO_ROOT / "server" / "static" / "workspace" / "modules" / "app.js"
STYLE_CSS = REPO_ROOT / "server" / "static" / "workspace" / "style.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── ReplayEngine Structure ──────────────────────────────────────


class TestReplayEngineStructure:
    """replay-engine.js exists and has correct structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        assert REPLAY_ENGINE_JS.exists(), f"replay-engine.js not found at {REPLAY_ENGINE_JS}"
        self.src = _read(REPLAY_ENGINE_JS)

    def test_replay_engine_class_export(self):
        assert "export class ReplayEngine" in self.src, (
            "ReplayEngine must be exported as a class"
        )

    def test_load_method(self):
        assert re.search(r"\bload\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have load method"
        )

    def test_play_method(self):
        assert re.search(r"\bplay\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have play method"
        )

    def test_pause_method(self):
        assert re.search(r"\bpause\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have pause method"
        )

    def test_seek_method(self):
        assert re.search(r"\bseek\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have seek method"
        )

    def test_setSpeed_method(self):
        assert re.search(r"\bsetSpeed\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have setSpeed method"
        )

    def test_getSpeed_method(self):
        assert re.search(r"\bgetSpeed\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have getSpeed method"
        )

    def test_isPlaying_method(self):
        assert re.search(r"\bisPlaying\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have isPlaying method"
        )

    def test_isLoaded_method(self):
        assert re.search(r"\bisLoaded\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have isLoaded method"
        )

    def test_getTimeRange_method(self):
        assert re.search(r"\bgetTimeRange\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have getTimeRange method"
        )

    def test_getCurrentTime_method(self):
        assert re.search(r"\bgetCurrentTime\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have getCurrentTime method"
        )

    def test_getProgress_method(self):
        assert re.search(r"\bgetProgress\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have getProgress method"
        )

    def test_dispose_method(self):
        assert re.search(r"\bdispose\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have dispose method"
        )

    def test_bufferLiveEvent_method(self):
        assert re.search(r"\bbufferLiveEvent\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have bufferLiveEvent method"
        )

    def test_flushLiveBuffer_method(self):
        assert re.search(r"\bflushLiveBuffer\s*\([^)]*\)\s*\{", self.src), (
            "ReplayEngine must have flushLiveBuffer method"
        )

    def test_speed_options_include_200(self):
        assert "SPEED_OPTIONS = [1, 5, 10, 50, 100, 200]" in self.src or (
            "[1, 5, 10, 50, 100, 200]" in self.src and "SPEED" in self.src
        ), "Speed options must include 200x"

    def test_load_uses_replay_page_loop(self):
        assert "REPLAY_PAGE_LIMIT = 5000" in self.src
        assert "MAX_REPLAY_EVENTS = 200000" in self.src
        assert "URLSearchParams" in self.src
        assert 'replay: "true"' in self.src
        assert 'grouped: "true"' in self.src
        assert 'semantic: "true"' in self.src
        assert "while (true)" in self.src
        assert "data.has_more" in self.src
        assert "offset += pageEvents.length" in self.src

    def test_load_fails_on_stalled_capped_page(self):
        assert "Replay page stalled" in self.src
        assert "pageEvents.length === 0" in self.src

    def test_load_uses_shared_normalizer(self):
        assert 'from "./activity-normalize.js"' in self.src
        assert "normalizeActivityEvent" in self.src

    def test_semantic_stream_entries_use_labels_and_summary(self):
        assert "semanticEventToStreamEntry" in self.src
        assert "semanticStreamType" in self.src
        assert "summarizeSemanticEvent" in self.src
        assert "evt.label" in self.src
        assert "evt.summary" in self.src
        assert "evt.kind" in self.src
        assert "isVisibleReplayEvent" in self.src

    def test_replay_engine_exposes_narrative_hook(self):
        assert "onNarrativeUpdate" in self.src
        assert "_buildNarrativeState" in self.src


# ── ReplayUI Structure ──────────────────────────────────────────


class TestReplayUIStructure:
    """replay-ui.js exists and has correct structure."""

    @pytest.fixture(autouse=True)
    def _load(self):
        assert REPLAY_UI_JS.exists(), f"replay-ui.js not found at {REPLAY_UI_JS}"
        self.src = _read(REPLAY_UI_JS)

    def test_replay_ui_class_export(self):
        assert "export class ReplayUI" in self.src, (
            "ReplayUI must be exported as a class"
        )

    def test_show_method(self):
        assert re.search(r"\bshow\s*\([^)]*\)\s*\{", self.src), (
            "ReplayUI must have show method"
        )

    def test_hide_method(self):
        assert re.search(r"\bhide\s*\([^)]*\)\s*\{", self.src), (
            "ReplayUI must have hide method"
        )

    def test_updateTime_method(self):
        assert re.search(r"\bupdateTime\s*\([^)]*\)\s*\{", self.src), (
            "ReplayUI must have updateTime method"
        )

    def test_updateTimeRange_method(self):
        assert re.search(r"\bupdateTimeRange\s*\([^)]*\)\s*\{", self.src), (
            "ReplayUI must have updateTimeRange method"
        )

    def test_setPlaying_method(self):
        assert re.search(r"\bsetPlaying\s*\([^)]*\)\s*\{", self.src), (
            "ReplayUI must have setPlaying method"
        )

    def test_setSpeed_method(self):
        assert re.search(r"\bsetSpeed\s*\([^)]*\)\s*\{", self.src), (
            "ReplayUI must have setSpeed method"
        )

    def test_setLoading_method(self):
        assert re.search(r"\bsetLoading\s*\([^)]*\)\s*\{", self.src), (
            "ReplayUI must have setLoading method"
        )

    def test_setError_method(self):
        assert re.search(r"\bsetError\s*\([^)]*\)\s*\{", self.src), (
            "ReplayUI must have setError method"
        )

    def test_clearError_method(self):
        assert re.search(r"\bclearError\s*\([^)]*\)\s*\{", self.src), (
            "ReplayUI must have clearError method"
        )

    def test_dispose_method(self):
        assert re.search(r"\bdispose\s*\([^)]*\)\s*\{", self.src), (
            "ReplayUI must have dispose method"
        )


# ── Org Dashboard Replay Integration ────────────────────────────


class TestOrgDashboardReplayIntegration:
    """org-dashboard.js has replay integration."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(ORG_DASHBOARD_JS)

    def test_exports_startReplay(self):
        assert "export async function startReplay" in self.src or (
            "export function startReplay" in self.src
        ), "org-dashboard must export startReplay"

    def test_exports_stopReplay(self):
        assert "export function stopReplay" in self.src, (
            "org-dashboard must export stopReplay"
        )

    def test_exports_isReplayMode(self):
        assert "export function isReplayMode" in self.src, (
            "org-dashboard must export isReplayMode"
        )

    def test_exports_bufferReplayEvent(self):
        assert "export function bufferReplayEvent" in self.src, (
            "org-dashboard must export bufferReplayEvent"
        )

    def test_dispose_cleans_up_replay_engine(self):
        assert "_replayEngine" in self.src and "dispose" in self.src, (
            "disposeOrgDashboard must reference _replayEngine"
        )
        assert "_replayEngine?.dispose()" in self.src or (
            "_replayEngine" in self.src and "dispose" in self.src
        ), "disposeOrgDashboard must dispose _replayEngine"

    def test_dispose_cleans_up_replay_ui(self):
        assert "_replayUI" in self.src, (
            "disposeOrgDashboard must reference _replayUI"
        )
        assert "_replayUI?.dispose()" in self.src or (
            "_replayUI" in self.src and "dispose" in self.src
        ), "disposeOrgDashboard must dispose _replayUI"

    def test_showMessageLine_supports_replaySpeed_option(self):
        assert "replaySpeed" in self.src, (
            "showMessageLine must support replaySpeed option"
        )
        assert "replaySpeed >= 100" in self.src or "replaySpeed >= 50" in self.src, (
            "showMessageLine must have speed-dependent duration logic"
        )

    def test_replay_handler_uses_semantic_card_renderer(self):
        assert "updateCardSemanticActivity" in self.src
        assert "_semanticCardNames(evt)" in self.src
        assert "_showSemanticReplayLine(evt, speed)" in self.src
        assert "evt?.kind" in self.src
        assert "evt.meta?.to_person" not in self.src
        assert "evt.meta?.from_person" not in self.src
        assert "updateCardActivity(anima, data)" not in self.src

    def test_startReplay_returns_boolean(self):
        assert "return true;" in self.src
        assert "return false;" in self.src
        assert "_replayUI.setError" in self.src

    def test_exports_semantic_activity_update(self):
        assert "export function updateCardSemanticActivity" in self.src
        assert "_semanticStreamType(event, name)" in self.src
        assert "eventTimeMs(event)" in self.src


# ── Activity Normalize Shared Module ───────────────────────────


class TestActivityNormalizeModule:
    """activity-normalize.js exports shared replay/timeline resolvers."""

    @pytest.fixture(autouse=True)
    def _load(self):
        assert ACTIVITY_NORMALIZE_JS.exists(), "activity-normalize.js must exist"
        self.src = _read(ACTIVITY_NORMALIZE_JS)

    def test_exports_normalize_and_resolvers(self):
        for name in (
            "normalizeActivityEvent",
            "resolveEventPersons",
            "resolveEventText",
            "resolveEventChannel",
            "eventTimeMs",
        ):
            assert f"export function {name}" in self.src

    def test_resolver_prefers_meta_then_toplevel(self):
        body = self.src
        assert "meta.from_person" in body
        assert "evt.from_person" in body
        assert body.index("meta.from_person") < body.index("evt.from_person")
        assert "meta.to_person" in body
        assert "evt.to_person" in body
        assert body.index("meta.to_person") < body.index("evt.to_person")


# ── WS Buffering During Replay ──────────────────────────────────


class TestWSBufferingDuringReplay:
    """app-websocket.js buffers during replay."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(APP_WS_JS)

    def test_imports_isReplayMode(self):
        assert "isReplayMode" in self.src, (
            "app-websocket must import isReplayMode"
        )

    def test_imports_bufferReplayEvent(self):
        assert "bufferReplayEvent" in self.src, (
            "app-websocket must import bufferReplayEvent"
        )

    def test_has_buffering_logic_in_handlers(self):
        assert "isReplayMode()" in self.src, (
            "app-websocket must check isReplayMode in handlers"
        )
        assert "bufferReplayEvent" in self.src, (
            "app-websocket must call bufferReplayEvent when in replay mode"
        )

    def test_visual_effects_are_behind_buffer_helper(self):
        assert "function applyOrBufferReplay" in self.src
        for call in ("showMessageEffect", "showMessageLine", "showExternalLine"):
            idx = self.src.index(f"{call}(")
            context = self.src[max(0, idx - 300):idx]
            assert "applyOrBufferReplay" in context, (
                f"{call} must be called through replay buffer helper"
            )


# ── App.js Replay Button ───────────────────────────────────────


class TestAppJSReplayButton:
    """app.js imports replay functions and has replay button."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(APP_JS)

    def test_imports_startReplay(self):
        assert "startReplay" in self.src, "app.js must import startReplay"

    def test_imports_stopReplay(self):
        assert "stopReplay" in self.src, "app.js must import stopReplay"

    def test_imports_isReplayMode(self):
        assert "isReplayMode" in self.src, "app.js must import isReplayMode"

    def test_imports_from_org_dashboard(self):
        assert "org-dashboard" in self.src and "startReplay" in self.src, (
            "app.js must import replay functions from org-dashboard"
        )

    def test_replay_button_awaits_startReplay(self):
        assert "await startReplay(24)" in self.src
        assert "const started" in self.src
        assert "if (started)" in self.src


# ── Replay CSS Styles ───────────────────────────────────────────


class TestReplayCSSStyles:
    """CSS has replay classes."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = _read(STYLE_CSS)

    def test_org_replay_bar(self):
        assert ".org-replay-bar" in self.src, (
            "CSS must define .org-replay-bar"
        )

    def test_org_replay_btn(self):
        assert ".org-replay-btn" in self.src, (
            "CSS must define .org-replay-btn"
        )

    def test_org_replay_slider(self):
        assert ".org-replay-slider" in self.src, (
            "CSS must define .org-replay-slider"
        )

    def test_org_replay_speed(self):
        assert ".org-replay-speed" in self.src, (
            "CSS must define .org-replay-speed"
        )

    def test_org_replay_controls(self):
        assert ".org-replay-controls" in self.src or ".org-replay-seek" in self.src, (
            "CSS must define replay control layout classes"
        )

    def test_org_replay_error(self):
        assert ".org-replay-error" in self.src, (
            "CSS must define replay error status styles"
        )
