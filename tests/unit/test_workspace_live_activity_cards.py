"""Unit tests for workspace live activity cards — static analysis of JS/CSS source.

Verifies that org-dashboard cards include activity stream areas,
data-status based animations, card expand mode, and that
app-websocket.js dispatches events to updateCardActivity.
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ORG_DASHBOARD_JS = (
    REPO_ROOT / "server" / "static" / "workspace" / "modules" / "org-dashboard.js"
)
APP_WEBSOCKET_JS = (
    REPO_ROOT / "server" / "static" / "workspace" / "modules" / "app-websocket.js"
)
STYLE_CSS = REPO_ROOT / "server" / "static" / "workspace" / "style.css"


# ── org-dashboard.js: Card HTML Structure ──────────────────────

class TestCardHtmlStructure:
    """Verify card elements include header wrapper and stream area."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_card_has_header_wrapper(self):
        assert "org-card-header" in self.src

    def test_card_has_stream_area(self):
        assert "org-card-stream" in self.src
        assert "orgStream_" in self.src

    def test_card_has_data_status_attribute(self):
        assert "dataset.status" in self.src

    def test_card_shows_idle_placeholder(self):
        assert "org-stream-idle" in self.src

    def test_create_card_sets_status_attr(self):
        assert "statusAttr" in self.src
        assert "getStatusAttr" in self.src


# ── org-dashboard.js: Activity Stream Logic ──────────────────────

class TestActivityStreamLogic:
    """Verify updateCardActivity and stream rendering implementation."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_update_card_activity_exported(self):
        assert "export function updateCardActivity" in self.src

    def test_update_card_activity_not_placeholder(self):
        match = re.search(
            r"export function updateCardActivity\([^)]*\)\s*\{([^}]*(?:\{[^}]*\})*[^}]*)\}",
            self.src,
            re.DOTALL,
        )
        assert match, "updateCardActivity function not found"
        body = match.group(1).strip()
        assert "Placeholder" not in body
        assert "void name" not in body

    def test_card_streams_map_exists(self):
        assert "_cardStreams" in self.src
        assert "new Map()" in self.src

    def test_max_stream_entries_constant(self):
        assert "MAX_STREAM_ENTRIES" in self.src

    def test_handles_tool_start_event(self):
        assert 'eventType === "tool_start"' in self.src

    def test_handles_tool_end_event(self):
        assert 'eventType === "tool_end"' in self.src or 'eventType === "tool_use"' in self.src

    def test_handles_board_post_event(self):
        assert 'eventType === "board_post"' in self.src

    def test_handles_cron_event(self):
        assert 'eventType === "cron"' in self.src

    def test_handles_heartbeat_event(self):
        assert 'eventType === "heartbeat"' in self.src

    def test_render_stream_function_exists(self):
        assert "_renderStream" in self.src

    def test_stream_entries_clipped(self):
        assert "MAX_STREAM_ENTRIES * 2" in self.src
        assert "slice(-MAX_STREAM_ENTRIES)" in self.src

    def test_running_entries_show_elapsed_time(self):
        assert "Date.now() - e.ts" in self.src

    def test_stream_type_icons_present(self):
        for icon_key in ["tool", "board", "cron", "heartbeat"]:
            assert f'"{icon_key}"' in self.src


# ── org-dashboard.js: Stale Entry Timeout ──────────────────────

class TestStaleEntryTimeout:
    """Verify running entries auto-complete after timeout."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_stale_timeout_constant(self):
        assert "STALE_TIMEOUT_MS" in self.src

    def test_stale_timer_exists(self):
        assert "_staleTimerId" in self.src
        assert "_ensureStaleTimer" in self.src

    def test_stale_timer_marks_timeout(self):
        assert "(timeout)" in self.src

    def test_stale_timer_cleanup_on_dispose(self):
        assert "clearInterval(_staleTimerId)" in self.src


# ── org-dashboard.js: Card Expand Mode ──────────────────────

class TestCardExpandMode:
    """Verify card click toggles expanded detail view."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_toggle_expand_function_exists(self):
        assert "_toggleCardExpand" in self.src

    def test_expanded_class_used(self):
        assert "org-card--expanded" in self.src

    def test_detail_element_created(self):
        assert "org-card-detail" in self.src
        assert "org-card-detail-header" in self.src
        assert "org-card-detail-list" in self.src

    def test_detail_shows_recent_entries(self):
        assert "slice(-20)" in self.src

    def test_only_one_card_expanded(self):
        assert 'querySelectorAll(".org-card--expanded")' in self.src

    def test_stream_click_triggers_expand(self):
        assert "org-card-stream" in self.src

    def test_drag_excludes_stream_area(self):
        assert 'closest(".org-card-stream")' in self.src
        assert 'closest(".org-card-detail")' in self.src

    def test_connections_updated_after_expand(self):
        assert "_updateConnections()" in self.src


# ── org-dashboard.js: Status Attribute ──────────────────────

class TestStatusAttribute:
    """Verify data-status attribute is set and updated."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_get_status_attr_function(self):
        assert "function getStatusAttr" in self.src

    def test_status_attr_values(self):
        for val in ["idle", "working", "error", "bootstrapping", "chatting"]:
            assert f'"{val}"' in self.src

    def test_update_anima_status_delegates_to_helpers(self):
        fn_match = re.search(
            r"export function updateAnimaStatus\([^)]*\)\s*\{(.*?)\n\}",
            self.src,
            re.DOTALL,
        )
        assert fn_match, "updateAnimaStatus not found"
        body = fn_match.group(1)
        assert "_syncCardSpinner" in body
        assert "getStatusDotClass" in body or "getStatusLabel" in body

    def test_heartbeat_sets_temp_status(self):
        assert '"heartbeat"' in self.src
        assert 'dataset.status' in self.src


# ── app-websocket.js: Event Dispatches ──────────────────────

class TestWebSocketEventDispatches:
    """Verify app-websocket.js dispatches events to updateCardActivity."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = APP_WEBSOCKET_JS.read_text(encoding="utf-8")

    def test_imports_update_card_activity(self):
        assert "updateCardActivity" in self.src
        assert "import" in self.src.split("updateCardActivity")[0].split("\n")[-1]

    def test_tool_activity_dispatches_to_card(self):
        tool_section = self.src[self.src.index("anima.tool_activity"):]
        assert "updateCardActivity" in tool_section[:1600]

    def test_heartbeat_dispatches_to_card(self):
        hb_section = self.src[self.src.index("anima.heartbeat"):]
        assert "updateCardActivity" in hb_section[:800]

    def test_cron_dispatches_to_card(self):
        cron_section = self.src[self.src.index("anima.cron"):]
        assert "updateCardActivity" in cron_section[:800]

    def test_board_post_dispatches_to_card(self):
        board_section = self.src[self.src.index("board.post"):]
        assert "updateCardActivity" in board_section[:1000]

    def test_dispatches_guarded_by_org_view(self):
        matches = re.findall(r'getCurrentView\(\)\s*===\s*"org"', self.src)
        assert len(matches) >= 2, f"Expected ≥2 org view guards, found {len(matches)}"


# ── style.css: Status Animations ──────────────────────

class TestStatusAnimationCss:
    """Verify data-status CSS animations exist."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = STYLE_CSS.read_text(encoding="utf-8")

    def test_data_status_idle(self):
        assert 'data-status="idle"' in self.src

    def test_data_status_working(self):
        assert 'data-status="working"' in self.src

    def test_data_status_heartbeat(self):
        assert 'data-status="heartbeat"' in self.src

    def test_data_status_chatting(self):
        assert 'data-status="chatting"' in self.src

    def test_data_status_error(self):
        assert 'data-status="error"' in self.src

    def test_data_status_bootstrapping(self):
        assert 'data-status="bootstrapping"' in self.src

    def test_keyframes_org_spin(self):
        assert "@keyframes org-spin" in self.src

    def test_keyframes_org_pulse(self):
        assert "@keyframes org-pulse" in self.src

    def test_keyframes_org_heartbeat(self):
        assert "@keyframes org-heartbeat" in self.src

    def test_keyframes_org_blink(self):
        assert "@keyframes org-blink" in self.src

    def test_working_dot_has_rotating_ring(self):
        assert "border-top-color" in self.src
        assert "org-spin" in self.src


# ── style.css: Stream Area ──────────────────────

class TestStreamCss:
    """Verify activity stream CSS classes and layout."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = STYLE_CSS.read_text(encoding="utf-8")

    def test_card_header_class(self):
        assert ".org-card-header" in self.src

    def test_card_flex_column(self):
        card_match = re.search(
            r"\.org-card\s*\{([^}]+)\}",
            self.src,
        )
        assert card_match
        assert "flex-direction: column" in card_match.group(1)

    def test_stream_area_class(self):
        assert ".org-card-stream" in self.src

    def test_stream_max_height(self):
        assert "max-height" in self.src
        assert "overflow-y" in self.src

    def test_stream_entry_classes(self):
        assert ".org-stream-entry" in self.src
        assert ".org-stream--running" in self.src
        assert ".org-stream--done" in self.src
        assert ".org-stream--error" in self.src

    def test_stream_idle_class(self):
        assert ".org-stream-idle" in self.src

    def test_stream_spinner(self):
        assert ".org-stream-spinner" in self.src

    def test_stream_text_ellipsis(self):
        assert "text-overflow: ellipsis" in self.src

    def test_fadein_animation(self):
        assert "@keyframes org-stream-fadein" in self.src


# ── style.css: Expanded Card ──────────────────────

class TestExpandedCardCss:
    """Verify expanded card CSS styles."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = STYLE_CSS.read_text(encoding="utf-8")

    def test_expanded_class(self):
        assert ".org-card--expanded" in self.src

    def test_expanded_wider(self):
        expanded_match = re.search(
            r"\.org-card--expanded\s*\{([^}]+)\}",
            self.src,
        )
        assert expanded_match
        assert "width: 360px" in expanded_match.group(1)

    def test_detail_styles(self):
        assert ".org-card-detail" in self.src
        assert ".org-card-detail-header" in self.src
        assert ".org-card-detail-list" in self.src
        assert ".org-detail-entry" in self.src


# ── style.css: Reduced Motion ──────────────────────

class TestReducedMotionCss:
    """Verify prefers-reduced-motion media query disables animations."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = STYLE_CSS.read_text(encoding="utf-8")

    def test_prefers_reduced_motion_query(self):
        assert "prefers-reduced-motion" in self.src

    def test_dot_animations_disabled(self):
        last_rm_idx = self.src.rindex("prefers-reduced-motion")
        rm_section = self.src[last_rm_idx:]
        assert "animation: none" in rm_section[:500]

    def test_spinner_disabled(self):
        last_rm_idx = self.src.rindex("prefers-reduced-motion")
        rm_section = self.src[last_rm_idx:]
        assert "org-stream-spinner" in rm_section[:500]


# ── style.css: Responsive ──────────────────────

class TestResponsiveCss:
    """Verify responsive adjustments for smaller screens."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = STYLE_CSS.read_text(encoding="utf-8")

    def test_responsive_card_no_fixed_height(self):
        responsive_start = self.src.index("Org Dashboard Responsive")
        responsive_section = self.src[responsive_start:responsive_start + 500]
        assert "height: 70px" not in responsive_section

    def test_responsive_stream_max_height(self):
        responsive_start = self.src.index("Org Dashboard Responsive")
        responsive_section = self.src[responsive_start:responsive_start + 500]
        assert ".org-card-stream" in responsive_section
