from __future__ import annotations

from pathlib import Path

import pytest

from core.lifecycle.system_consolidation import run_weekly_pattern_distillation


@pytest.mark.asyncio
async def test_weekly_pattern_distillation_calls_distiller(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    class FakeDistiller:
        def __init__(self, anima_dir: Path, anima_name: str) -> None:
            calls["init"] = (anima_dir, anima_name)

        async def weekly_pattern_distill(self, *, model: str, days: int) -> dict[str, object]:
            calls["distill"] = {"model": model, "days": days}
            return {"procedures_created": ["procedures/runbook.md"], "patterns_detected": 1}

    monkeypatch.setattr("core.memory.distillation.ProceduralDistiller", FakeDistiller)

    await run_weekly_pattern_distillation(tmp_path / "animas" / "sakura", "sakura", model="test-model")

    assert calls["init"] == (tmp_path / "animas" / "sakura", "sakura")
    assert calls["distill"] == {"model": "test-model", "days": 7}
