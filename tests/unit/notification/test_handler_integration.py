"""Tests for call_human integration in ToolHandler."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.messenger import Messenger
from core.notification.interactive import InteractionRequest
from core.notification.notifier import HumanNotifier, NotificationChannel
from core.tooling.handler import ToolHandler

# ── Mock Channel ──────────────────────────────────────────────


class StubChannel(NotificationChannel):
    """A stub channel that records calls."""

    def __init__(self, *, fail: bool = False) -> None:
        super().__init__({})
        self._fail = fail
        self.calls: list[dict[str, str | None]] = []

    @property
    def channel_type(self) -> str:
        return "stub"

    async def send(
        self,
        subject: str,
        body: str,
        priority: str = "normal",
        *,
        anima_name: str = "",
        interaction: InteractionRequest | None = None,
    ) -> str:
        if self._fail:
            raise RuntimeError("stub failure")
        self.calls.append(
            {
                "subject": subject,
                "body": body,
                "priority": priority,
                "anima_name": anima_name,
                "interaction": interaction.callback_id if interaction else None,
            }
        )
        return "stub: OK"


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "test-anima"
    d.mkdir(parents=True)
    (d / "permissions.md").write_text("", encoding="utf-8")
    return d


@pytest.fixture
def memory() -> MagicMock:
    m = MagicMock()
    m.read_permissions.return_value = ""
    return m


@pytest.fixture
def stub_channel() -> StubChannel:
    return StubChannel()


@pytest.fixture
def notifier(stub_channel: StubChannel) -> HumanNotifier:
    return HumanNotifier([stub_channel])


@pytest.fixture
def handler_with_notifier(
    anima_dir: Path,
    memory: MagicMock,
    notifier: HumanNotifier,
) -> ToolHandler:
    handler = ToolHandler(
        anima_dir=anima_dir,
        memory=memory,
        human_notifier=notifier,
    )
    handler._reload_human_notifier_from_config = lambda: (notifier, None)  # type: ignore[attr-defined]
    return handler


@pytest.fixture
def handler_without_notifier(
    anima_dir: Path,
    memory: MagicMock,
) -> ToolHandler:
    return ToolHandler(
        anima_dir=anima_dir,
        memory=memory,
    )


@pytest.fixture
def handler_with_notifier_and_messenger(
    tmp_path: Path,
    anima_dir: Path,
    memory: MagicMock,
    notifier: HumanNotifier,
) -> ToolHandler:
    shared_dir = tmp_path / "shared"
    (shared_dir / "inbox").mkdir(parents=True, exist_ok=True)
    (shared_dir / "channels").mkdir(parents=True, exist_ok=True)
    handler = ToolHandler(
        anima_dir=anima_dir,
        memory=memory,
        messenger=Messenger(shared_dir, anima_dir.name),
        human_notifier=notifier,
    )
    handler._reload_human_notifier_from_config = lambda: (notifier, None)  # type: ignore[attr-defined]
    return handler


# ── Tests ─────────────────────────────────────────────────────


class TestCallHumanHandler:
    def test_call_human_success(
        self,
        handler_with_notifier: ToolHandler,
        stub_channel: StubChannel,
    ):
        result = handler_with_notifier.handle(
            "call_human",
            {
                "subject": "Test Alert",
                "body": "Something happened",
                "priority": "high",
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "sent"
        assert "stub: OK" in parsed["results"]
        assert len(stub_channel.calls) == 1
        assert stub_channel.calls[0]["subject"] == "Test Alert"
        assert stub_channel.calls[0]["priority"] == "high"
        assert stub_channel.calls[0]["anima_name"] == "test-anima"

    def test_call_human_default_priority(
        self,
        handler_with_notifier: ToolHandler,
        stub_channel: StubChannel,
    ):
        result = handler_with_notifier.handle(
            "call_human",
            {
                "subject": "Info",
                "body": "FYI",
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "sent"
        assert stub_channel.calls[0]["priority"] == "normal"

    def test_call_human_no_notifier(
        self,
        handler_without_notifier: ToolHandler,
    ):
        handler_without_notifier._reload_human_notifier_from_config = lambda: (  # type: ignore[attr-defined]
            None,
            (
                "NotificationDisabled",
                "Human notification is disabled",
                "Set human_notification.enabled to true in config.json",
            ),
        )
        result = handler_without_notifier.handle(
            "call_human",
            {
                "subject": "Test",
                "body": "Body",
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "NotificationDisabled"

    def test_call_human_reloads_notifier_from_config(
        self,
        handler_without_notifier: ToolHandler,
        notifier: HumanNotifier,
        stub_channel: StubChannel,
    ):
        handler_without_notifier._reload_human_notifier_from_config = lambda: (notifier, None)  # type: ignore[attr-defined]
        result = handler_without_notifier.handle(
            "call_human",
            {
                "subject": "Reloaded",
                "body": "Config changed",
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "sent"
        assert stub_channel.calls[0]["subject"] == "Reloaded"

    def test_call_human_no_channels(
        self,
        anima_dir: Path,
        memory: MagicMock,
    ):
        empty_notifier = HumanNotifier([])
        handler = ToolHandler(
            anima_dir=anima_dir,
            memory=memory,
            human_notifier=empty_notifier,
        )
        handler._reload_human_notifier_from_config = lambda: (  # type: ignore[attr-defined]
            None,
            (
                "NoNotificationChannels",
                "No enabled notification channels configured",
                "Add an enabled channel to human_notification.channels in config.json",
            ),
        )
        result = handler.handle(
            "call_human",
            {
                "subject": "Test",
                "body": "Body",
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "NoNotificationChannels"

    def test_call_human_discord_target_missing(
        self,
        handler_without_notifier: ToolHandler,
    ):
        handler_without_notifier._reload_human_notifier_from_config = lambda: (  # type: ignore[attr-defined]
            None,
            (
                "DiscordTargetMissing",
                "Discord notification channel has no user_id, channel_id, or webhook_url configured",
                "Set human_notification.channels[].config.user_id, channel_id, or webhook_url",
            ),
        )
        result = handler_without_notifier.handle(
            "call_human",
            {
                "subject": "Test",
                "body": "Body",
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "DiscordTargetMissing"

    def test_call_human_missing_subject(
        self,
        handler_with_notifier: ToolHandler,
    ):
        result = handler_with_notifier.handle(
            "call_human",
            {
                "body": "Body only",
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "InvalidArguments"

    def test_call_human_missing_body(
        self,
        handler_with_notifier: ToolHandler,
    ):
        result = handler_with_notifier.handle(
            "call_human",
            {
                "subject": "Subject only",
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "InvalidArguments"

    def test_call_human_channel_partial_failure(
        self,
        anima_dir: Path,
        memory: MagicMock,
    ):
        ok_ch = StubChannel()
        fail_ch = StubChannel(fail=True)
        notifier = HumanNotifier([ok_ch, fail_ch])
        handler = ToolHandler(
            anima_dir=anima_dir,
            memory=memory,
            human_notifier=notifier,
        )
        handler._reload_human_notifier_from_config = lambda: (notifier, None)  # type: ignore[attr-defined]
        result = handler.handle(
            "call_human",
            {
                "subject": "Test",
                "body": "Body",
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "sent"
        assert any("OK" in r for r in parsed["results"])
        assert any("ERROR" in r for r in parsed["results"])

    def test_call_human_interactive_includes_callback_id(
        self,
        handler_with_notifier: ToolHandler,
        stub_channel: StubChannel,
    ):
        """Interactive mode registers an InteractionRequest and returns callback_id."""
        req = InteractionRequest(
            callback_id="cb_test_1",
            anima_name="test-anima",
            category="approval",
            options=["approve", "reject"],
            allowed_users={"slack": ["U1", "U9"]},
            metadata={},
            created_at=datetime.now(UTC),
            approval_token="tok",
            message_ts={},
        )
        with (
            patch("core.config.models.load_config") as mock_load,
            patch("core.notification.interactive.get_interaction_router") as mock_get_ir,
        ):
            mock_load.return_value.interaction.default_approver_ids = ["U9"]
            mock_get_ir.return_value.create = AsyncMock(return_value=req)

            result = handler_with_notifier.handle(
                "call_human",
                {
                    "subject": "Need approval",
                    "body": "Please approve X",
                    "interactive": True,
                    "category": "approval",
                    "options": ["approve", "reject"],
                    "allowed_users": ["U1"],
                },
            )
        parsed = json.loads(result)
        assert parsed["status"] == "sent"
        assert parsed.get("interactive") is True
        assert parsed.get("callback_id") == "cb_test_1"
        assert stub_channel.calls[0].get("interaction") == "cb_test_1"
        mock_get_ir.return_value.create.assert_called_once()
        _cargs, ckwargs = mock_get_ir.return_value.create.call_args
        assert ckwargs["allowed_users"] == {"slack": ["U1", "U9"]}

    def test_ops_post_without_interactive_call_human_falls_back_to_general(
        self,
        handler_with_notifier_and_messenger: ToolHandler,
    ):
        result = handler_with_notifier_and_messenger.handle(
            "post_channel",
            {"channel": "ops", "text": "Routine status report"},
        )

        assert "Posted to #general" in result
        assert "redirected from #ops" in result

    def test_noninteractive_call_human_ops_post_falls_back_to_general(
        self,
        handler_with_notifier_and_messenger: ToolHandler,
    ):
        notify_result = handler_with_notifier_and_messenger.handle(
            "call_human",
            {
                "subject": "FYI",
                "body": "Non-interactive notification",
            },
        )
        assert json.loads(notify_result)["status"] == "sent"

        post_result = handler_with_notifier_and_messenger.handle(
            "post_channel",
            {"channel": "ops", "text": "Escalation-looking text after non-interactive notify"},
        )

        assert "Posted to #general" in post_result
        assert "redirected from #ops" in post_result

    def test_interactive_call_human_allows_one_ops_post(
        self,
        handler_with_notifier_and_messenger: ToolHandler,
    ):
        req = InteractionRequest(
            callback_id="cb_ops_1",
            anima_name="test-anima",
            category="approval",
            options=["approve", "reject"],
            allowed_users={},
            metadata={},
            created_at=datetime.now(UTC),
            approval_token="tok",
            message_ts={},
        )
        cfg = MagicMock()
        cfg.interaction.default_approver_ids = []
        cfg.heartbeat.channel_post_cooldown_s = 0
        cfg.animas = {}

        with (
            patch("core.config.models.load_config", return_value=cfg),
            patch("core.notification.interactive.get_interaction_router") as mock_get_ir,
        ):
            mock_get_ir.return_value.create = AsyncMock(return_value=req)

            notify_result = handler_with_notifier_and_messenger.handle(
                "call_human",
                {
                    "subject": "Need owner decision",
                    "body": "Please decide whether to proceed.",
                    "interactive": True,
                },
            )
            first_post = handler_with_notifier_and_messenger.handle(
                "post_channel",
                {"channel": "ops", "text": "Owner decision requested via interactive call_human."},
            )
            second_post = handler_with_notifier_and_messenger.handle(
                "post_channel",
                {"channel": "ops", "text": "Second ops post without another interactive call_human."},
            )

        assert json.loads(notify_result)["callback_id"] == "cb_ops_1"
        assert "Posted to #ops" in first_post
        assert "cb_ops_1" in first_post
        assert "Posted to #general" in second_post
        assert "redirected from #ops" in second_post
