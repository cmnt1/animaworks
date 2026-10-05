"""Anima-main IPC handlers for server-originated conversation state."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.memory.conversation.memory import ConversationMemory
from core.runtime.runner import AnimaRunner
from core.schemas import ModelConfig


@pytest.mark.asyncio
async def test_append_conversation_turns_handler_persists_on_anima_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    monkeypatch.setenv("ANIMAWORKS_PROCESS_ROLE", "anima")
    anima = SimpleNamespace(
        model_config=ModelConfig(model="test-model"),
        _validate_thread_id=lambda _thread_id: None,
    )
    runner = SimpleNamespace(anima=anima, anima_name="alice", _anima_dir=anima_dir)

    result = await AnimaRunner._handle_append_conversation_turns(
        runner,
        {
            "thread_id": "default",
            "turns": [
                {"role": "human", "content": "voice input"},
                {"role": "assistant", "content": "voice reply"},
            ],
        },
    )

    assert result == {"status": "saved", "anima": "alice"}
    state = ConversationMemory(anima_dir, anima.model_config).load()
    assert [(turn.role, turn.content) for turn in state.turns] == [
        ("human", "voice input"),
        ("assistant", "voice reply"),
    ]
