"""Tests for pre-resume SDK session recycling."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core._agent_cycle import CycleMixin
from core.schemas import ModelConfig


def _write_state(anima_dir: Path, *, ratio: float, created_at: str | None = None) -> None:
    state_dir = anima_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    (state_dir / "current_session_chat.json").write_text(
        json.dumps(
            {
                "session_id": "session-1",
                "timestamp": now,
                "created_at": created_at or now,
                "updated_at": now,
                "baseline_tokens": 30_000,
                "last_tokens": int(ratio * 200_000),
                "last_ratio": ratio,
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["ceiling", "age"])
async def test_guard_recycles_session(tmp_path: Path, reason: str) -> None:
    created = (datetime.now(UTC) - timedelta(hours=48)).isoformat() if reason == "age" else None
    _write_state(tmp_path, ratio=0.9 if reason == "ceiling" else 0.1, created_at=created)
    owner = SimpleNamespace(anima_dir=tmp_path)
    config = ModelConfig(
        context_absolute_ceiling=0.75,
        max_session_age_hours=24,
    )

    with (
        patch(
            "core.session_compactor._extract_recent_chat_context",
            return_value={
                "accumulated_response": "saved context",
                "tool_uses": [],
                "original_prompt": "prompt",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        ),
        patch("core.memory.activity.ActivityLogger.log") as activity_log,
    ):
        result = await CycleMixin._guard_chat_sdk_session(
            owner,
            mode="s",
            uses_chat_session=True,
            active_model_config=config,
            thread_id="default",
        )

    assert result is None
    assert not (tmp_path / "state" / "current_session_chat.json").exists()
    shortterm_file = tmp_path / "shortterm" / "chat" / "session_state.json"
    assert shortterm_file.exists()
    assert "saved context" in shortterm_file.read_text(encoding="utf-8")
    assert activity_log.call_args.args[0] == "session_recycled"


@pytest.mark.asyncio
async def test_guard_keeps_healthy_session(tmp_path: Path) -> None:
    _write_state(tmp_path, ratio=0.2)
    owner = SimpleNamespace(anima_dir=tmp_path)
    config = ModelConfig(context_absolute_ceiling=0.75, max_session_age_hours=24)

    result = await CycleMixin._guard_chat_sdk_session(
        owner,
        mode="s",
        uses_chat_session=True,
        active_model_config=config,
        thread_id="default",
    )

    assert result is not None
    assert result.session_id == "session-1"


@pytest.mark.asyncio
async def test_guard_does_not_touch_non_sdk_session(tmp_path: Path) -> None:
    owner = SimpleNamespace(anima_dir=tmp_path)
    config = ModelConfig()

    result = await CycleMixin._guard_chat_sdk_session(
        owner,
        mode="a",
        uses_chat_session=True,
        active_model_config=config,
        thread_id="default",
    )

    assert result is None
