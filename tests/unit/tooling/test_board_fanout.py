"""Tests for centralized board mention fanout through ToolHandler._handle_post_channel."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.i18n import t
from core.tooling.handler import ToolHandler

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    animas_dir = tmp_path / "animas"
    animas_dir.mkdir(parents=True)
    for name in ("test-anima", "alice", "bob", "charlie"):
        candidate = animas_dir / name
        candidate.mkdir()
        (candidate / "status.json").write_text('{"enabled": true}', encoding="utf-8")
        sockets = tmp_path / "run" / "sockets"
        sockets.mkdir(parents=True, exist_ok=True)
        (sockets / f"{name}.sock").touch()
    d = animas_dir / "test-anima"
    (d / "permissions.md").write_text("", encoding="utf-8")
    return d


@pytest.fixture
def memory(anima_dir: Path) -> MagicMock:
    m = MagicMock()
    m.read_permissions.return_value = ""
    m.search_memory_text.return_value = []
    return m


@pytest.fixture
def messenger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    m = MagicMock()
    m.anima_name = "test-anima"
    m.shared_dir = tmp_path / "shared"
    (m.shared_dir / "channels").mkdir(parents=True)
    msg = MagicMock()
    msg.id = "msg_001"
    msg.thread_id = "thread_001"
    m.send.return_value = msg

    from core.messaging.board import anima_principal, post_to_board

    def post_direct(
        channel: str,
        text: str,
        *,
        from_anima: str,
        source: str = "anima",
        from_name: str | None = None,
        request_id: str | None = None,
        suppress_mentions: bool = False,
    ) -> dict:
        channel_path = m.shared_dir / "channels" / f"{channel}.jsonl"
        channel_path.touch(exist_ok=True)
        result = post_to_board(
            channel,
            text,
            anima_principal(from_anima, animas_dir=m.shared_dir.parent / "animas"),
            request_id=request_id,
            origin="internal",
            notify=not suppress_mentions,
            shared_dir=m.shared_dir,
        )
        return {"post": result.to_dict()}

    monkeypatch.setattr("core.messaging.board_client.post_via_server", post_direct)
    return m


@pytest.fixture
def handler_with_messenger(
    anima_dir: Path,
    memory: MagicMock,
    messenger: MagicMock,
) -> ToolHandler:
    return ToolHandler(
        anima_dir=anima_dir,
        memory=memory,
        messenger=messenger,
        tool_registry=[],
    )


# ── Board mention fanout tests ───────────────────────────────


@pytest.mark.unit
class TestBoardMentionFanout:
    """Tests for the centralized post path and inbox mention delivery."""

    @staticmethod
    def _mentions(messenger: MagicMock) -> list[tuple[str, dict]]:
        messages: list[tuple[str, dict]] = []
        for path in (messenger.shared_dir / "inbox").glob("*/*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("type") == "board_mention":
                messages.append((path.parent.name, data))
        return messages

    def test_subordinate_ops_routine_post_is_blocked(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        cfg = SimpleNamespace(
            animas={"test-anima": SimpleNamespace(supervisor="sakura")},
            heartbeat=SimpleNamespace(
                channel_post_cooldown_s=0,
                depth_window_s=600,
                max_depth=6,
            ),
        )
        with patch("core.config.models.load_config", return_value=cfg):
            result = handler_with_messenger.handle(
                "post_channel",
                {"channel": "ops", "text": "定例確認の報告です。問題ありません。"},
            )

        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "OpsEscalationRequired"
        messenger.post_channel.assert_not_called()

    def test_subordinate_ops_escalation_post_is_allowed(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        cfg = SimpleNamespace(
            animas={"test-anima": SimpleNamespace(supervisor="sakura")},
            heartbeat=SimpleNamespace(
                channel_post_cooldown_s=0,
                depth_window_s=600,
                max_depth=6,
            ),
        )
        with patch("core.config.models.load_config", return_value=cfg):
            result = handler_with_messenger.handle(
                "post_channel",
                {"channel": "ops", "text": "緊急エスカレーションです。call_human が必要です。"},
            )

        assert result == t("handler.channel_post_success", channel="ops")
        assert "緊急エスカレーション" in (messenger.shared_dir / "channels" / "ops.jsonl").read_text(encoding="utf-8")

    def test_fanout_at_all_sends_to_enabled_animas(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        """@all reaches enabled Animas with active sockets."""
        handler_with_messenger.handle(
            "post_channel",
            {"channel": "general", "text": "Hello @all!"},
        )

        targets = {target for target, _ in self._mentions(messenger)}
        assert targets == {"alice", "bob", "charlie"}

    def test_fanout_at_name_sends_to_specific_anima(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        """@bob mention sends DM only to bob."""
        handler_with_messenger.handle(
            "post_channel",
            {"channel": "dev", "text": "Hey @bob, check this"},
        )

        targets = {target for target, _ in self._mentions(messenger)}
        assert targets == {"bob"}

    def test_fanout_no_mention_no_dm(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        """Text without any @mention should not trigger any fanout DM."""
        handler_with_messenger.handle(
            "post_channel",
            {"channel": "general", "text": "No mentions here"},
        )

        assert self._mentions(messenger) == []

    def test_fanout_excludes_self(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        """@all should not send a DM to the posting Anima itself (test-anima)."""
        handler_with_messenger.handle(
            "post_channel",
            {"channel": "general", "text": "@all standup time"},
        )

        targets = {target for target, _ in self._mentions(messenger)}
        assert "test-anima" not in targets
        assert "alice" in targets

    def test_fanout_excludes_stopped_animas(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        """A stopped Anima is not sent a Board mention."""
        (messenger.shared_dir.parent / "run" / "sockets" / "bob.sock").unlink()
        handler_with_messenger.handle(
            "post_channel",
            {"channel": "dev", "text": "Hey @bob, are you there?"},
        )

        assert self._mentions(messenger) == []

    def test_fanout_dm_content_format(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        """Fanout DM content should contain board_reply tag, original text, and reply instructions."""
        original_text = "Hey @bob, please review the PR"
        handler_with_messenger.handle(
            "post_channel",
            {"channel": "dev", "text": original_text},
        )

        fanout_calls = self._mentions(messenger)
        assert len(fanout_calls) == 1
        content = fanout_calls[0][1]["content"]

        # Check board_reply tag with channel and from fields
        assert "[board_reply:channel=dev,from=test-anima]" in content
        # Check original text is included
        assert original_text in content
        # Check reply instructions point to the Board CLI
        assert "animaworks-tool board post dev -" in content

    def test_fanout_dm_type_is_board_mention(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        """Fanout DM must use msg_type='board_mention'."""
        handler_with_messenger.handle(
            "post_channel",
            {"channel": "general", "text": "@all hello"},
        )

        fanout_calls = self._mentions(messenger)
        assert len(fanout_calls) >= 1
        for _, message in fanout_calls:
            assert message["type"] == "board_mention"

    def test_fanout_multiple_named_mentions(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        """@bob @charlie should send DM to both bob and charlie."""
        handler_with_messenger.handle(
            "post_channel",
            {"channel": "project", "text": "@bob @charlie please review"},
        )

        targets = {target for target, _ in self._mentions(messenger)}
        assert targets == {"bob", "charlie"}
        # alice should NOT receive a DM (not mentioned)
        assert "alice" not in targets

    def test_fanout_message_includes_board_post_meta(
        self,
        handler_with_messenger: ToolHandler,
        messenger: MagicMock,
    ):
        """Fanout DMs include the channel and source post ID in metadata."""
        handler_with_messenger.handle(
            "post_channel",
            {"channel": "dev", "text": "Hey @bob"},
        )

        fanout_calls = self._mentions(messenger)
        assert len(fanout_calls) == 1
        channel_path = messenger.shared_dir / "channels" / "dev.jsonl"
        post_id = json.loads(channel_path.read_text(encoding="utf-8").splitlines()[-1])["id"]
        assert fanout_calls[0][1]["meta"] == {"board_channel": "dev", "board_post_id": post_id}

    def test_posted_channel_guard_is_shared_within_runtime_context(
        self,
        anima_dir: Path,
        memory: MagicMock,
        messenger: MagicMock,
    ) -> None:
        from core.execution.session.session_context import RuntimeSessionContext, runtime_session_scope
        from core.tooling.handler_base import active_session_type

        ctx = RuntimeSessionContext.create(session_type="chat", thread_id="thread-a", trigger="message")
        first = ToolHandler(anima_dir, memory, messenger, tool_registry=[])
        second = ToolHandler(anima_dir, memory, messenger, tool_registry=[])
        first.bind_runtime_session(ctx)
        second.bind_runtime_session(ctx)

        first_token = first.set_active_session_type(ctx.session_type)
        try:
            with runtime_session_scope(ctx):
                first_result = first.handle("post_channel", {"channel": "general", "text": "first"})
        finally:
            active_session_type.reset(first_token)

        second_token = second.set_active_session_type(ctx.session_type)
        try:
            with runtime_session_scope(ctx):
                second_result = second.handle("post_channel", {"channel": "general", "text": "second"})
        finally:
            active_session_type.reset(second_token)

        # CLI invocations and the agent share the same per-run guard.
        from core.i18n import t

        assert first_result == t("handler.channel_post_success", channel="general")
        assert "Error" in second_result
        assert len((messenger.shared_dir / "channels" / "general.jsonl").read_text(encoding="utf-8").splitlines()) == 1

    def test_escalation_is_consumed_across_handlers(self, anima_dir, memory, messenger):
        from core.execution.session.session_context import RuntimeSessionContext, runtime_session_scope
        from core.tooling.handler_base import active_session_type

        ctx = RuntimeSessionContext.create(session_type="chat", thread_id="thread-a", trigger="message")
        first = ToolHandler(anima_dir, memory, messenger, tool_registry=[])
        second = ToolHandler(anima_dir, memory, messenger, tool_registry=[])
        token = active_session_type.set("chat")
        try:
            with runtime_session_scope(ctx):
                with first._shared_comms_state("call_human"):
                    first._record_ops_human_escalation("callback-1")
                with second._shared_comms_state("post_channel"):
                    assert second._consume_ops_human_escalation() == "callback-1"
                with first._shared_comms_state("post_channel"):
                    assert not first._has_ops_human_escalation()
            other = RuntimeSessionContext.create(session_type="chat", thread_id="thread-b", trigger="message")
            with runtime_session_scope(other), first._shared_comms_state("call_human"):
                assert not first._has_ops_human_escalation()
                first._record_ops_human_escalation("callback-other")
            with runtime_session_scope(ctx), first._shared_comms_state("post_channel"):
                assert not first._has_ops_human_escalation()
        finally:
            active_session_type.reset(token)

    def test_posted_channel_guard_is_per_handler_without_runtime_context(
        self,
        anima_dir: Path,
        memory: MagicMock,
        messenger: MagicMock,
    ) -> None:
        from core.tooling.handler_base import active_session_type

        first = ToolHandler(anima_dir, memory, messenger, tool_registry=[])
        second = ToolHandler(anima_dir, memory, messenger, tool_registry=[])

        token = active_session_type.set("unknown")
        try:
            first_result = first.handle("post_channel", {"channel": "general", "text": "first"})
            second_result = second.handle("post_channel", {"channel": "general", "text": "second"})
        finally:
            active_session_type.reset(token)

        # The guard is per run (per handler); nothing is carried over from files.
        from core.i18n import t

        assert first_result == t("handler.channel_post_success", channel="general")
        assert second_result == t("handler.channel_post_success", channel="general")
        assert len((messenger.shared_dir / "channels" / "general.jsonl").read_text(encoding="utf-8").splitlines()) == 2
