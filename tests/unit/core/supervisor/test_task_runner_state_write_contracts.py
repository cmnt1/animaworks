"""Task-runner contracts delegate managed-state writes to the Anima main."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from core.runtime.state_writer import IpcStateWriter, LocalStateWriter, configure_state_writer, get_state_writer
from core.schemas import CronTask


class _Result:
    action = "responded"
    reason = ""
    usage = None
    summary = "contract result"

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        del mode
        return {"action": self.action, "summary": self.summary}


class _FakeAnima:
    name = "alice"

    def __init__(self, anima_dir: Path) -> None:
        self.anima_dir = anima_dir
        self.agent = type("Agent", (), {"_executor": type("Executor", (), {"supports_message_injection": False})()})()

    async def process_message(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        writer = get_state_writer(self.anima_dir)
        await writer.save_conversation("default", {"anima_name": "alice", "turns": []})
        await writer.append_transcript({"ts": "2026-10-01T10:00:00+09:00", "role": "human"})
        return {"summary": "chat"}

    async def run_heartbeat(self) -> _Result:
        writer = get_state_writer(self.anima_dir)
        await writer.write_heartbeat_checkpoint({"trigger": "heartbeat"})
        await writer.clear_heartbeat_checkpoint()
        return _Result()

    async def run_cron_task(self, *args: Any, **kwargs: Any) -> _Result:
        await get_state_writer(self.anima_dir).log_token_usage({"ts": "2026-10-01T10:00:00+09:00", "total_tokens": 1})
        return _Result()

    async def process_inbox_message(self) -> _Result:
        await get_state_writer(self.anima_dir).update_inbox_read_counts({"message.json": 1})
        return _Result()

    def drain_notifications(self) -> list[dict[str, Any]]:
        return []


class _AnimaMainLink:
    def __init__(self, anima_dir: Path) -> None:
        self.writer = LocalStateWriter(anima_dir)
        self.operations: list[str] = []

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        assert method == "state_write"
        self.operations.append(params["operation"])
        role = os.environ.get("ANIMAWORKS_PROCESS_ROLE")
        os.environ["ANIMAWORKS_PROCESS_ROLE"] = "anima"
        try:
            return {"result": await self.writer.execute_operation(params["operation"], params["payload"])}
        finally:
            if role is None:
                os.environ.pop("ANIMAWORKS_PROCESS_ROLE", None)
            else:
                os.environ["ANIMAWORKS_PROCESS_ROLE"] = role

    async def send_unanswered_request(self, method: str, params: dict[str, Any]) -> None:
        raise AssertionError(f"unexpected chunked request in contract test: {method} {params}")


@pytest.mark.asyncio
async def test_chat_heartbeat_cron_inbox_and_task_contracts_use_ipc_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.runtime.task_runner as task_runner_module
    from core.tasks.pending_executor import PendingTaskExecutor

    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    link = _AnimaMainLink(anima_dir)
    monkeypatch.setenv("ANIMAWORKS_PROCESS_ROLE", "task_runner")
    configure_state_writer(IpcStateWriter(link))
    anima = _FakeAnima(anima_dir)

    async def _fake_task(self: PendingTaskExecutor, task_desc: dict[str, Any], completed: Any = None) -> str:
        await get_state_writer(anima_dir).save_task_result(task_desc["task_id"], None, "task result")
        return "task result"

    monkeypatch.setattr(PendingTaskExecutor, "_run_llm_task", _fake_task)
    try:
        chat = await task_runner_module.execute_chat_contract(
            anima,
            kind="message",
            payload={"message": "hello"},
            send_stream_event=lambda *_args, **_kwargs: None,
        )
        heartbeat = await task_runner_module.execute_heartbeat_contract(anima)
        cron = await task_runner_module.execute_cron_contract(
            anima,
            CronTask(name="daily", schedule="0 0 * * *", description="daily"),
        )
        inbox = await task_runner_module.execute_inbox_contract(anima)
        task = await task_runner_module.execute_task_contract(anima, {"task_id": "task-1"})
    finally:
        configure_state_writer(None)
        monkeypatch.delenv("ANIMAWORKS_PROCESS_ROLE", raising=False)

    assert chat["response"] == "chat"
    assert heartbeat["task_type"] == "heartbeat"
    assert cron["task_type"] == "llm"
    assert inbox["task_type"] == "inbox"
    assert task["result"] == "task result"
    assert {
        "save_conversation",
        "append_transcript",
        "write_heartbeat_checkpoint",
        "clear_heartbeat_checkpoint",
        "log_token_usage",
        "update_inbox_read_counts",
        "save_task_result",
    } <= set(link.operations)
    assert (anima_dir / "state" / "task_results" / "task-1.md").read_text(encoding="utf-8") == "task result"
