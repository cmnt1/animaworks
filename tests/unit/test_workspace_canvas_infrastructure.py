"""Unit tests for workspace canvas infrastructure — static analysis of JS/CSS source.

Verifies that the org-dashboard has been migrated from 2-column flex layout
to a canvas-based node graph with draggable cards, SVG connections, and KPI bar.
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
APP_JS = (
    REPO_ROOT / "server" / "static" / "workspace" / "modules" / "app.js"
)
STYLE_CSS = REPO_ROOT / "server" / "static" / "workspace" / "style.css"


# ── org-dashboard.js Structure ──────────────────────

class TestOrgDashboardCanvasStructure:
    """Verify org-dashboard.js contains canvas node graph implementation."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_file_exists(self):
        assert ORG_DASHBOARD_JS.exists()

    def test_canvas_root_html_structure(self):
        assert "org-canvas-root" in self.src
        assert "org-kpi-bar" in self.src
        assert "org-canvas-viewport" in self.src
        assert "org-canvas-svg" in self.src
        assert "org-canvas-nodes" in self.src

    def test_old_two_column_removed(self):
        assert "org-col-main" not in self.src
        assert "org-col-right" not in self.src
        assert "org-activity-feed" not in self.src

    def test_old_itree_classes_removed(self):
        assert "org-itree-node" not in self.src
        assert "org-itree-connector" not in self.src
        assert "org-itree-card" not in self.src

    def test_exports_init_and_dispose(self):
        assert "export async function initOrgDashboard" in self.src
        assert "export function disposeOrgDashboard" in self.src

    def test_exports_update_anima_status(self):
        assert "export function updateAnimaStatus" in self.src

    def test_exports_new_api(self):
        assert "export function getCardPosition" in self.src
        assert "export function updateCardActivity" in self.src

    def test_exports_add_activity_item_compat(self):
        assert "export function addActivityItem" in self.src

    def test_add_activity_item_is_noop(self):
        match = re.search(
            r"export function addActivityItem\([^)]*\)\s*\{([^}]*)\}",
            self.src,
        )
        assert match, "addActivityItem function not found"
        body = match.group(1).strip()
        assert body == "" or "no-op" in body or body.startswith("//")


class TestOrgDashboardDragImplementation:
    """Verify drag mechanics are implemented."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_pointer_events_used(self):
        assert "pointerdown" in self.src
        assert "pointermove" in self.src
        assert "pointerup" in self.src

    def test_set_pointer_capture(self):
        assert "setPointerCapture" in self.src

    def test_dragging_class_applied(self):
        assert "org-card--dragging" in self.src

    def test_position_absolute_cards(self):
        assert "position: absolute" in self.src or "style.left" in self.src

    def test_drag_persists_to_localstorage(self):
        assert "localStorage" in self.src
        assert "aw-org-positions" in self.src


class TestOrgDashboardTreeLayout:
    """Verify tree layout algorithm exists."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_compute_tree_layout_exists(self):
        assert "_computeTreeLayout" in self.src

    def test_card_dimensions_defined(self):
        assert "CARD_W" in self.src
        assert "CARD_H" in self.src

    def test_layout_uses_measure_and_position(self):
        assert "measure" in self.src


class TestOrgDashboardSvgConnections:
    """Verify SVG connection line implementation."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_update_connections_function(self):
        assert "_updateConnections" in self.src

    def test_svg_path_creation(self):
        assert "createElementNS" in self.src
        assert "http://www.w3.org/2000/svg" in self.src

    def test_cubic_bezier_curve(self):
        match = re.search(r'`M.*C.*`', self.src)
        assert match, "Cubic bezier SVG path not found"

    def test_connection_line_class(self):
        assert "org-connection-line" in self.src


class TestOrgDashboardKpiBar:
    """Verify KPI bar implementation."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_render_kpi_bar_function(self):
        assert "_renderKpiBar" in self.src

    def test_kpi_shows_active_count(self):
        assert "Active" in self.src

    def test_kpi_shows_events_per_hour(self):
        assert "events/h" in self.src

    def test_kpi_shows_tasks(self):
        assert "Tasks" in self.src

    def test_kpi_shows_errors(self):
        assert "Errors" in self.src


class TestOrgDashboardCanvasPan:
    """Verify canvas pan implementation."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_pan_setup_function(self):
        assert "_setupPan" in self.src

    def test_pan_uses_scroll(self):
        assert "scrollLeft" in self.src
        assert "scrollTop" in self.src


class TestOrgDashboardReviewFixes:
    """Verify review feedback fixes are applied."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = ORG_DASHBOARD_JS.read_text(encoding="utf-8")

    def test_localstorage_position_validation(self):
        assert "_isValidPos" in self.src
        assert "Number.isFinite" in self.src

    def test_kpi_errors_handles_object_status(self):
        assert "a.status?.state" in self.src or "a.status?.status" in self.src

    def test_drag_click_prevention(self):
        assert "_didDrag" in self.src

    def test_resize_debounced(self):
        assert "cancelAnimationFrame" in self.src
        assert "_resizeRafId" in self.src

    def test_connection_uses_actual_card_dimensions(self):
        assert "_getCardDimensions" in self.src
        assert "offsetWidth" in self.src


# ── CSS Canvas Styles ──────────────────────

class TestOrgDashboardCssCanvasStyles:
    """Verify CSS has been migrated to canvas-based classes."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.css = STYLE_CSS.read_text(encoding="utf-8")

    def test_canvas_root_class(self):
        assert ".org-canvas-root" in self.css

    def test_canvas_viewport_class(self):
        assert ".org-canvas-viewport" in self.css

    def test_canvas_svg_class(self):
        assert ".org-canvas-svg" in self.css

    def test_canvas_nodes_class(self):
        assert ".org-canvas-nodes" in self.css

    def test_card_class(self):
        assert ".org-card " in self.css or ".org-card{" in self.css

    def test_card_dragging_style(self):
        assert ".org-card--dragging" in self.css

    def test_kpi_bar_styles(self):
        assert ".org-kpi-bar" in self.css
        assert ".org-kpi-card" in self.css
        assert ".org-kpi-value" in self.css
        assert ".org-kpi-label" in self.css

    def test_connection_line_style(self):
        assert ".org-connection-line" in self.css

    def test_card_avatar_style(self):
        assert ".org-card-avatar" in self.css

    def test_card_name_style(self):
        assert ".org-card-name" in self.css

    def test_card_dot_status_style(self):
        assert ".org-card-dot" in self.css
        assert ".org-card-status-label" in self.css

    def test_old_classes_removed(self):
        assert ".org-dashboard " not in self.css and ".org-dashboard{" not in self.css
        assert ".org-col-main" not in self.css
        assert ".org-col-right" not in self.css
        assert ".org-itree-node" not in self.css
        assert ".org-itree-connector" not in self.css
        assert ".org-activity-feed" not in self.css
        assert ".org-activity-item" not in self.css

    def test_status_dot_classes_preserved(self):
        assert ".dot-idle" in self.css
        assert ".dot-active" in self.css
        assert ".dot-sleeping" in self.css
        assert ".dot-error" in self.css
        assert ".dot-bootstrap" in self.css
        assert ".dot-unknown" in self.css

    def test_responsive_styles(self):
        assert "@media (max-width: 900px)" in self.css
        assert ".org-kpi-bar" in self.css


# ── app-websocket.js Cleanup ──────────────────────

class TestAppWebsocketCleanup:
    """Verify addActivityItem calls removed from app-websocket.js."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = APP_WEBSOCKET_JS.read_text(encoding="utf-8")

    def test_no_add_activity_item_import(self):
        assert "addActivityItem" not in self.src

    def test_update_anima_status_import_preserved(self):
        assert "updateAnimaStatus" in self.src

    def test_update_anima_status_call_preserved(self):
        match = re.search(r"updateAnimaStatus\(data\.name", self.src)
        assert match, "updateAnimaStatus call not found in websocket handler"


# ── app.js Compatibility ──────────────────────

class TestAppJsCompatibility:
    """Verify app.js still correctly references org-dashboard exports."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.src = APP_JS.read_text(encoding="utf-8")

    def test_imports_init_org_dashboard(self):
        assert "initOrgDashboard" in self.src

    def test_imports_dispose_org_dashboard(self):
        assert "disposeOrgDashboard" in self.src

    def test_switch_view_calls_init(self):
        assert "initOrgDashboard" in self.src

    def test_switch_view_calls_dispose(self):
        match = re.search(r"disposeOrgDashboard\(\)", self.src)
        assert match, "disposeOrgDashboard() call not found in app.js"
