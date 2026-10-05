# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for core.tooling.permissions — tool access evaluation and is_action_gated."""

from __future__ import annotations

from unittest.mock import patch

from core.tooling.permissions import (
    _load_execution_profile,
    is_action_gated,
)

# ── is_action_gated ────────────────────────────────────────────────────────


def test_is_action_gated_true_when_gated_and_not_allowed() -> None:
    """is_action_gated returns True for gated action not in permitted."""
    with patch(
        "core.tooling.permissions._load_execution_profile",
        return_value={"send": {"gated": True}},
    ):
        assert is_action_gated("gmail", "send", {"gmail"}) is True


def test_gmail_draft_update_is_gated_by_real_profile() -> None:
    assert is_action_gated("gmail", "draft-update", {"gmail"}) is True
    assert is_action_gated("gmail", "draft-update", {"gmail", "gmail_draft-update"}) is False
    assert is_action_gated("gmail", "draft_update", {"gmail"}) is True
    assert is_action_gated("gmail", "draft_update", {"gmail", "gmail_draft-update"}) is False


def test_is_action_gated_false_when_gated_and_allowed() -> None:
    """is_action_gated returns False for gated action in permitted."""
    with patch(
        "core.tooling.permissions._load_execution_profile",
        return_value={"send": {"gated": True}},
    ):
        assert is_action_gated("gmail", "send", {"gmail", "gmail_send"}) is False


def test_is_action_gated_false_when_non_gated() -> None:
    """is_action_gated returns False for non-gated actions."""
    with patch(
        "core.tooling.permissions._load_execution_profile",
        return_value={"read": {"gated": False}},
    ):
        assert is_action_gated("gmail", "read", {"gmail"}) is False


def test_is_action_gated_true_when_tool_profile_not_found() -> None:
    """is_action_gated returns True (fail-closed) when the tool profile is missing."""
    with patch(
        "core.tooling.permissions._load_execution_profile",
        return_value=None,
    ):
        assert is_action_gated("nonexistent_tool", "send", set()) is True


def test_is_action_gated_respects_gated_as() -> None:
    """An action with gated_as gates under that name's permission key."""
    with patch(
        "core.tooling.permissions._load_execution_profile",
        return_value={"upload": {"gated": True, "gated_as": "send"}},
    ):
        # Allowed when gated_as permission (chatwork_send) is present.
        assert is_action_gated("chatwork", "upload", {"chatwork_send"}) is False
        # Blocked when not present.
        assert is_action_gated("chatwork", "upload", set()) is True


def test_is_action_gated_false_when_action_not_in_profile() -> None:
    """is_action_gated returns False when action not in EXECUTION_PROFILE."""
    with patch(
        "core.tooling.permissions._load_execution_profile",
        return_value={"read": {"gated": False}},
    ):
        assert is_action_gated("gmail", "send", {"gmail"}) is False


# ── all: yes does NOT auto-allow gated actions (moved to test_tool_access) ─


def test_load_execution_profile_returns_profile_for_gmail() -> None:
    """_load_execution_profile returns EXECUTION_PROFILE for gmail."""
    profile = _load_execution_profile("gmail")
    assert profile is not None
    assert "unread" in profile
    assert "draft" in profile


def test_load_execution_profile_returns_none_for_unknown_tool() -> None:
    """_load_execution_profile returns None for unknown tool."""
    profile = _load_execution_profile("nonexistent_tool_xyz")
    assert profile is None
