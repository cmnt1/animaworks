"""Static checks for chat activity collapse rendering."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CHAT_RENDERER_JS = PROJECT_ROOT / "server" / "static" / "pages" / "chat" / "chat-renderer.js"
RENDER_UTILS_JS = PROJECT_ROOT / "server" / "static" / "shared" / "chat" / "render-utils.js"
CHAT_CSS = PROJECT_ROOT / "server" / "static" / "styles" / "chat.css"
I18N_DIR = PROJECT_ROOT / "server" / "static" / "i18n"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_chat_renderer_uses_multi_level_activity_bundle() -> None:
    js = _read(CHAT_RENDERER_JS)
    assert "renderCollapsibleActivityBundle" in js
    assert "getSessionActivityType" in js
    assert "getMessageActivityType" in js
    assert "activityRun.push({ type: sessionActivityType, session })" in js
    assert "activityRun.push({ type: messageActivityType, message: msg })" in js


def test_chat_renderer_passes_known_anima_names_for_dm_detection() -> None:
    js = _read(CHAT_RENDERER_JS)
    assert "knownAnimaNames" in js
    assert "state.animas" in js
    assert "knownUserNames" in js
    assert "state.users" in js
    assert 'document.getElementById("currentUserLabel")' in js


def test_render_utils_detects_dm_without_collapsing_human_chat() -> None:
    js = _read(RENDER_UTILS_JS)
    assert 'legacy event is source_key="dm"' in js
    assert 'if (msg.source_key === "dm") return "dm"' not in js
    assert "from_person" in js
    assert "to_person" in js
    assert "_isKnownAnimaName" in js
    assert "_isKnownUserName" in js
    assert "if (_isKnownUserName(from, opts) || _isKnownUserName(to, opts)) return null;" in js
    assert "opts?.avatarMap" not in js
    assert "Human chat messages remain visible" in js


def test_chat_loads_auth_users_for_human_anima_detection() -> None:
    js = _read(CHAT_RENDERER_JS.parent / "anima-controller.js")
    assert 'api("/api/users").catch(() => [])' in js
    assert "state.users = Array.isArray(users) ? users : []" in js
    assert "knownAnimas.has(m.from_person)" in js


def test_render_utils_has_three_collapse_levels() -> None:
    js = _read(RENDER_UTILS_JS)
    assert "bg-session-bundle" in js
    assert "bg-session-category" in js
    assert "bg-session-entry" in js
    assert "Level 1" in js
    assert "Level 2" in js
    assert "Level 3" in js


def test_chat_css_styles_nested_activity_nodes() -> None:
    css = _read(CHAT_CSS)
    assert ".bg-session-bundle" in css
    assert ".bg-session-category" in css
    assert ".bg-session-entry" in css
    assert ".bg-session-header--dm" in css
    assert ".bg-session-node.expanded > .bg-session-header .bg-session-chevron" in css


def test_i18n_contains_activity_collapse_labels() -> None:
    for locale in ("ja", "en", "ko"):
        data = json.loads((I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))
        assert data["chat.activity_bundle_count"]
        assert data["chat.activity_category_count"]
        assert data["chat.dm_activity"]
