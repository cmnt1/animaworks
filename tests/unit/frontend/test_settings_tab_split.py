# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Frontend structure checks for the settings page tab split.

Settings is split into 4 tabs (general | activity | api | users) and the
duplicated password / user-management forms were consolidated into the
Users tab.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STATIC = PROJECT_ROOT / "server" / "static"
SETTINGS_JS = STATIC / "pages" / "settings.js"
USERS_JS = STATIC / "pages" / "users.js"
I18N_DIR = STATIC / "i18n"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_settings_has_four_tabs() -> None:
    js = _read(SETTINGS_JS)
    for tab_id, label_key in (
        ("general", "settings.tab_general"),
        ("activity", "settings.tab_activity"),
        ("api", "settings.tab_api"),
        ("users", "settings.tab_users"),
    ):
        assert f'id: "{tab_id}"' in js
        assert label_key in js


def test_sections_split_across_tab_renderers() -> None:
    js = _read(SETTINGS_JS)
    # Dedicated renderers exist
    assert "function _renderGeneral(" in js
    assert "function _renderActivity(" in js
    assert "function _renderApiAuth(" in js

    # General keeps display/theme/font/input, API tab owns auth sections
    general = js.split("function _renderGeneral(")[1].split("\nfunction ")[0]
    for key in (
        "settings.mode.title",
        "settings.theme.title",
        "settings.font_size.title",
        "settings.input.title",
    ):
        assert key in general
    assert "settings.api_auth.title" not in general
    assert "settings.activity_level.title" not in general

    activity = js.split("function _renderActivity(")[1].split("\nfunction ")[0]
    assert "settings.activity_level.title" in activity
    assert "settings.night_mode.label" in activity

    api = js.split("function _renderApiAuth(")[1].split("\nfunction ")[0]
    assert 'id="settingsApiAuthSection"' in api
    assert 'id="authSettings"' in api


def test_password_form_only_in_users_tab() -> None:
    settings_js = _read(SETTINGS_JS)
    users_js = _read(USERS_JS)
    # Duplicated forms removed from settings general/api tabs
    assert 'id="changePasswordForm"' not in settings_js
    assert 'id="addUserForm"' not in settings_js
    # Consolidated in users tab
    assert 'id="changePasswordForm"' in users_js
    # API tab links to the users tab instead
    assert "settings.api_auth.manage_in_users" in settings_js
    assert "#/settings/users" in settings_js


def test_i18n_tab_keys_all_locales() -> None:
    required = (
        "settings.tab_general",
        "settings.tab_activity",
        "settings.tab_api",
        "settings.tab_users",
        "settings.api_auth.manage_in_users",
    )
    for locale in ("en", "ja", "ko"):
        data = json.loads((I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))
        for key in required:
            assert key in data, f"missing {key} in {locale}"
            assert data[key], f"empty {key} in {locale}"
        # Orphaned keys from the removed duplicate forms are gone
        assert "settings.api_auth.password_change" not in data
        assert "settings.api_auth.user_management" not in data
        # Auth banner deep-links to the users tab (where the password form lives)
        assert "#/settings/users" in data["app.auth_banner"]
