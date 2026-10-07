from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for best-effort server notifications from messaging entry points."""

from unittest.mock import MagicMock, patch

from core.tooling.standalone import notify_server_message_sent


def test_notification_skips_when_server_is_not_running() -> None:
    with (
        patch("core.platform.pid.is_server_running", return_value=False),
        patch("core.host_api.host_api.post") as post,
    ):
        notify_server_message_sent("alice", "bob", "hello")

    post.assert_not_called()


def test_notification_posts_broadcast_and_message_id() -> None:
    response = MagicMock(status_code=200)
    with (
        patch("core.platform.pid.is_server_running", return_value=True),
        patch("core.host_api.host_api.post", return_value=response) as post,
    ):
        notify_server_message_sent("alice", "bob", "x" * 240, "msg-123")

    post.assert_called_once_with(
        "/api/internal/message-sent",
        json={
            "from_person": "alice",
            "to_person": "bob",
            "content": "x" * 200,
            "message_id": "msg-123",
        },
        timeout=5.0,
    )


def test_notification_failure_is_silent() -> None:
    with (
        patch("core.platform.pid.is_server_running", return_value=True),
        patch("core.host_api.host_api.post", side_effect=RuntimeError("connection failed")),
    ):
        notify_server_message_sent("alice", "#channel:general", "hello")
