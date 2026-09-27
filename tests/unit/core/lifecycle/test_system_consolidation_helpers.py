from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest


def test_activity_log_only_anima_passes_daily_consolidation_gate(tmp_path: Path) -> None:
    from core.lifecycle.system_consolidation import evaluate_daily_consolidation_gate
    from core.memory.activity.logger import ActivityLogger

    anima_dir = tmp_path / "animas" / "ritsu"
    anima_dir.mkdir(parents=True)
    with patch("core.memory.activity.logger.now_iso", return_value="2026-06-10T12:00:00+09:00"):
        ActivityLogger(anima_dir).log(
            "response_sent",
            summary="worked from activity log only",
            content="activity exists before any episode has been generated",
        )

    with patch(
        "core.memory.maintenance.consolidation.now_local",
        return_value=datetime(2026, 6, 11, 2, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
    ):
        gate = evaluate_daily_consolidation_gate(
            anima_dir,
            "ritsu",
            threshold=1,
            hours=24,
        )

    assert gate.should_run is True
    assert gate.activity_count == 1
    assert gate.episode_count == 0


@pytest.mark.asyncio
async def test_consolidation_post_processing_does_not_rebuild_rag_index(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from core.lifecycle.system_consolidation import (
        run_daily_consolidation_post_processing,
        run_weekly_integration_post_processing,
    )

    knowledge_correction = AsyncMock()
    weekly_distillation = AsyncMock()
    monkeypatch.setattr(
        "core.lifecycle.system_consolidation.run_knowledge_self_correction_if_enabled",
        knowledge_correction,
    )
    monkeypatch.setattr("core.lifecycle.system_consolidation.run_weekly_pattern_distillation", weekly_distillation)

    await run_daily_consolidation_post_processing(
        "alice",
        tmp_path / "alice",
        consolidation_cfg=SimpleNamespace(synaptic_downscaling_enabled=False),
        model="test-model",
    )
    await run_weekly_integration_post_processing(
        "alice",
        tmp_path / "alice",
        consolidation_cfg=SimpleNamespace(weekly_distillation_enabled=True),
        model="test-model",
    )

    knowledge_correction.assert_awaited_once()
    weekly_distillation.assert_awaited_once_with(tmp_path / "alice", "alice", model="test-model")
