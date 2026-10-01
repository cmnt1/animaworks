"""Reproduce and prevent cross-lane conversation disk-write overlap."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core.memory.conversation.memory import ConversationMemory
from core.schemas import ModelConfig


@pytest.mark.asyncio
async def test_chat_and_heartbeat_conversation_writes_are_serialized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat and heartbeat may run concurrently, but the Anima main serializes writes."""
    import core.platform.state_writer as state_writer_module

    monkeypatch.setenv("ANIMAWORKS_PROCESS_ROLE", "anima")
    original_write = state_writer_module.atomic_write_text
    active = 0
    max_active = 0
    lock = threading.Lock()

    def observed_write(path: Path, content: str, **kwargs: object) -> None:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.05)
            original_write(path, content, **kwargs)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(state_writer_module, "atomic_write_text", observed_write)
    model_config = ModelConfig(model="test-model")
    chat = ConversationMemory(tmp_path / "alice", model_config)
    heartbeat = ConversationMemory(tmp_path / "alice", model_config)
    chat.append_turn("human", "chat turn")
    heartbeat.append_turn("assistant", "heartbeat turn")

    await asyncio.gather(chat.asave(), heartbeat.asave())

    assert max_active == 1

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(chat.save), executor.submit(heartbeat.save)]
        for future in futures:
            future.result(timeout=5)
    assert max_active == 1

    saved = json.loads((tmp_path / "alice" / "state" / "conversation.json").read_text(encoding="utf-8"))
    assert isinstance(saved["turns"], list)
