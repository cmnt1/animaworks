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

    def test_speed_options_are_1_5_10_50_100(self):
        assert "SPEED_OPTIONS = [1, 5, 10, 50, 100]" in self.src or (
            "[1, 5, 10, 50, 100]" in self.src and "SPEED" in self.src
        ), "Speed options must be [1, 5, 10, 50, 100]"


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
