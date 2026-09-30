"""Unit tests for inbox wakeups, batching, and provider failure backoff."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.messaging.messenger import Messenger
from core.supervisor.inbox_rate_limiter import InboxRateLimiter


def _make_limiter(
    anima_dir: Path,
    *,
    name: str = "alice",
    messenger: Messenger | MagicMock | None = None,
) -> InboxRateLimiter:
    anima = MagicMock()
    anima.anima_dir = anima_dir
    if messenger is None:
        shared_dir = anima_dir.parent.parent / "shared" if anima_dir.parent.name == "animas" else anima_dir / "shared"
        inbox_dir = shared_dir / "inbox" / name
        inbox_dir.mkdir(parents=True, exist_ok=True)
        messenger = MagicMock()
        messenger.inbox_dir = inbox_dir
        messenger.has_unread.return_value = False
    anima.messenger = messenger

    supervisor = MagicMock()
    supervisor.run_inbox = AsyncMock(
        return_value={
            "task_type": "inbox",
            "result": {"action": "responded", "reason": "", "summary": "ok"},
            "success": True,
        }
    )

    scheduler_mgr = MagicMock()
    scheduler_mgr.heartbeat_running = False
    scheduler_mgr._task_runner_supervisor = supervisor
    return InboxRateLimiter(
        anima=anima,
        anima_name=name,
        shutdown_event=asyncio.Event(),
        scheduler_mgr=scheduler_mgr,
    )


async def _stop_watcher(limiter: InboxRateLimiter, task: asyncio.Task) -> None:
    limiter._shutdown_event.set()
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
@pytest.mark.parametrize("raises", [False, True])
async def test_failed_inbox_keeps_unread_and_waits_for_retry_guard(tmp_path: Path, raises: bool) -> None:
    limiter = _make_limiter(tmp_path)
    limiter._anima.messenger.has_unread.return_value = True
    run_inbox = limiter._scheduler_mgr._task_runner_supervisor.run_inbox
    if raises:
        run_inbox.side_effect = ConnectionError("Connection refused")
    else:
        run_inbox.return_value = {
            "task_type": "inbox",
            "result": {"action": "error", "reason": "network", "summary": "API Error: ConnectionRefused"},
            "success": False,
        }

    with patch("core.supervisor.inbox_rate_limiter.time.monotonic", return_value=100.0):
        await limiter.message_triggered_inbox()
        assert limiter._failure_retry_until >= 130.0
        await limiter.message_triggered_inbox()
        assert run_inbox.await_count == 1
        assert limiter._deferred_timer is not None
        limiter.cancel_deferred_timer()

    run_inbox.side_effect = None
    run_inbox.return_value = {
        "task_type": "inbox",
        "result": {"action": "responded", "reason": "", "summary": "ok"},
        "success": True,
    }
    with patch("core.supervisor.inbox_rate_limiter.time.monotonic", return_value=131.0):
        await limiter.message_triggered_inbox()
        assert run_inbox.await_count == 2
        assert limiter._failure_retry_until == 0
        await limiter.message_triggered_inbox()
        assert run_inbox.await_count == 3


def test_inbox_failure_waits_for_all_provider_guards_to_expire(tmp_path: Path) -> None:
    from core.schemas import ModelConfig

    limiter = _make_limiter(tmp_path)
    config = ModelConfig(model="claude-sonnet-4-6", fallback_models=["c:codex/gpt-5.6-luna"])
    limiter._anima.agent.model_config = config
    with (
        patch("core.config.model_config.resolve_effective_model_config", return_value=config),
        patch("core.config.model_config._guard_key_for_model_config", return_value="test:blocked"),
        patch("core.execution.rate_guard.get_rate_guard") as guard,
        patch("core.supervisor.inbox_rate_limiter.time.monotonic", return_value=100.0),
    ):
        guard.return_value.blocked_remaining.return_value = 1800.0
        limiter._record_processing_failure()
    assert limiter._failure_retry_until == 1900.0


class TestInboxWatcherEnabledGuard:
    @pytest.mark.asyncio
    async def test_disabled_skips_processing_and_keeps_inbox(self, tmp_path: Path) -> None:
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "status.json").write_text(json.dumps({"enabled": False}), encoding="utf-8")
        limiter = _make_limiter(anima_dir)
        limiter._anima.messenger.has_unread.return_value = True

        task = asyncio.create_task(limiter.inbox_watcher_loop())
        try:
            await asyncio.sleep(0.1)
            limiter._scheduler_mgr._task_runner_supervisor.run_inbox.assert_not_awaited()
            assert limiter._pending_trigger is False
        finally:
            await _stop_watcher(limiter, task)

    @pytest.mark.asyncio
    async def test_enabled_triggers_processing(self, tmp_path: Path) -> None:
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "status.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")
        limiter = _make_limiter(anima_dir)
        limiter._anima.messenger.has_unread.return_value = True
        triggered = asyncio.Event()

        async def fake_triggered() -> None:
            triggered.set()
            limiter._pending_trigger = False

        with patch.object(limiter, "message_triggered_inbox", side_effect=fake_triggered):
            task = asyncio.create_task(limiter.inbox_watcher_loop())
            try:
                await asyncio.wait_for(triggered.wait(), timeout=2.0)
            finally:
                await _stop_watcher(limiter, task)

        assert triggered.is_set()

    @pytest.mark.asyncio
    async def test_disabled_then_enabled_is_seen_by_safety_rescan(self, tmp_path: Path) -> None:
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        status_path = anima_dir / "status.json"
        status_path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
        limiter = _make_limiter(anima_dir)
        limiter._anima.messenger.has_unread.return_value = True
        triggered = asyncio.Event()

        async def fake_triggered() -> None:
            triggered.set()
            limiter._pending_trigger = False

        with (
            patch("core.supervisor.inbox_rate_limiter._INBOX_RECHECK_INTERVAL_SEC", 0.05),
            patch.object(limiter, "message_triggered_inbox", side_effect=fake_triggered),
        ):
            task = asyncio.create_task(limiter.inbox_watcher_loop())
            try:
                await asyncio.sleep(0.12)
                assert not triggered.is_set()
                status_path.write_text(json.dumps({"enabled": True}), encoding="utf-8")
                await asyncio.wait_for(triggered.wait(), timeout=1.0)
            finally:
                await _stop_watcher(limiter, task)

        assert triggered.is_set()

    @pytest.mark.asyncio
    async def test_new_inbox_file_wakes_without_waiting_for_rescan(self, tmp_path: Path) -> None:
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "status.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")
        shared_dir = tmp_path / "shared"
        receiver = Messenger(shared_dir, "alice")
        sender = Messenger(shared_dir, "bob")
        limiter = _make_limiter(anima_dir, messenger=receiver)
        triggered = asyncio.Event()

        async def fake_triggered() -> None:
            receiver.archive_all()
            limiter._pending_trigger = False
            triggered.set()

        with patch.object(limiter, "message_triggered_inbox", side_effect=fake_triggered):
            task = asyncio.create_task(limiter.inbox_watcher_loop())
            try:
                await asyncio.sleep(0.1)  # Let the filesystem observer start and clear startup wake.
                sender.send("alice", "wake immediately")
                await asyncio.wait_for(triggered.wait(), timeout=3.0)
            finally:
                await _stop_watcher(limiter, task)

        assert triggered.is_set()

    @pytest.mark.asyncio
    async def test_messages_arriving_during_run_are_batched_for_the_next_run(self, tmp_path: Path) -> None:
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "status.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")
        shared_dir = tmp_path / "shared"
        receiver = Messenger(shared_dir, "alice")
        sender = Messenger(shared_dir, "bob")
        sender.send("alice", "initial")
        limiter = _make_limiter(anima_dir, messenger=receiver)
        snapshots: list[list[str]] = []
        second_batch_processed = asyncio.Event()

        async def process_batch() -> dict:
            items = receiver.receive_with_paths()
            snapshots.append([item.msg.content for item in items])
            receiver.archive_paths(items)
            if len(snapshots) == 1:
                sender.send("alice", "arrived during run 1")
                sender.send("alice", "arrived during run 1 too")
            else:
                second_batch_processed.set()
            return {
                "task_type": "inbox",
                "result": {"action": "responded", "reason": "", "summary": "ok"},
                "success": True,
            }

        limiter._scheduler_mgr._task_runner_supervisor.run_inbox = AsyncMock(side_effect=process_batch)
        task = asyncio.create_task(limiter.inbox_watcher_loop())
        try:
            await asyncio.wait_for(second_batch_processed.wait(), timeout=3.0)
        finally:
            await _stop_watcher(limiter, task)

        assert snapshots == [["initial"], ["arrived during run 1", "arrived during run 1 too"]]
        assert limiter._scheduler_mgr._task_runner_supervisor.run_inbox.await_count == 2


class TestReadAnimaEnabledMalformed:
    """Non-object status.json must default to enabled without raising."""

    def test_list_status_json_defaults_true(self, tmp_path: Path) -> None:
        from core.supervisor.inbox_rate_limiter import _read_anima_enabled

        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        (anima_dir / "status.json").write_text("[]", encoding="utf-8")
        assert _read_anima_enabled(anima_dir) is True

    def test_null_status_json_defaults_true(self, tmp_path: Path) -> None:
        from core.supervisor.inbox_rate_limiter import _read_anima_enabled

        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        (anima_dir / "status.json").write_text("null", encoding="utf-8")
        assert _read_anima_enabled(anima_dir) is True

    def test_manager_read_anima_enabled_non_dict_defaults_true(self, tmp_path: Path) -> None:
        from core.supervisor.manager import ProcessSupervisor

        anima_dir = tmp_path / "alice"
        anima_dir.mkdir()
        (anima_dir / "status.json").write_text("[1, 2]", encoding="utf-8")
        assert ProcessSupervisor.read_anima_enabled(anima_dir) is True
