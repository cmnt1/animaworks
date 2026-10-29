from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest


def test_activity_log_only_anima_passes_daily_consolidation_gate(tmp_path: Path) -> None:
    from core.activity.logger import ActivityLogger
    from core.lifecycle.system_consolidation import evaluate_daily_consolidation_gate

    anima_dir = tmp_path / "animas" / "ritsu"
    anima_dir.mkdir(parents=True)
    with patch("core.activity.logger.now_iso", return_value="2026-06-10T12:00:00+09:00"):
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
async def test_daily_post_processing_runs_forgetting_vector_calls_in_worker_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.lifecycle.system_consolidation import run_daily_consolidation_post_processing
    from core.memory.maintenance.forgetting import ForgettingEngine
    from core.memory.rag.store import Document, SearchResult
    from core.time_utils import now_jst

    root_thread_id = threading.get_ident()
    vector_threads: list[int] = []
    old_date = (now_jst() - timedelta(days=120)).isoformat()

    class FakeStore:
        def get_all(self, collection: str, *, limit: int = 100_000):  # noqa: ANN001, ARG002
            vector_threads.append(threading.get_ident())
            assert threading.get_ident() != root_thread_id
            if collection == "alice_knowledge":
                return [
                    SearchResult(
                        document=Document(
                            id=f"chunk-{index}",
                            content="old knowledge",
                            metadata={
                                "memory_type": "knowledge",
                                "updated_at": old_date,
                                "access_count": 0,
                            },
                        ),
                        score=1.0,
                    )
                    for index in range(3)
                ]
            return []

        def update_metadata(self, collection: str, ids: list[str], metadatas: list[dict]):  # noqa: ANN001, ARG002
            vector_threads.append(threading.get_ident())
            assert threading.get_ident() != root_thread_id
            return True

    fake_store = FakeStore()
    monkeypatch.setattr(ForgettingEngine, "_get_vector_store", lambda _self: fake_store)
    original_downscaling = ForgettingEngine.synaptic_downscaling
    result: dict = {}

    def capture_result(self, *args, **kwargs):  # noqa: ANN002, ANN003
        scanned = original_downscaling(self, *args, **kwargs)
        result.update(scanned)
        return scanned

    monkeypatch.setattr(ForgettingEngine, "synaptic_downscaling", capture_result)
    # This post-processing call should skip knowledge correction and isolate the
    # event-loop regression test to the synchronous vector scan.
    await run_daily_consolidation_post_processing(
        "alice",
        tmp_path / "alice",
        consolidation_cfg=SimpleNamespace(
            synaptic_downscaling_enabled=True,
            knowledge_self_correction_enabled=False,
        ),
        model="test-model",
    )

    assert result["scanned"] == 3
    assert vector_threads
    assert all(thread_id != root_thread_id for thread_id in vector_threads)


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
    weekly_distillation.assert_awaited_once_with(tmp_path / "alice", "alice", model="")
