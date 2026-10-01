from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_chroma_signal_to_supervised_repair_lifecycle(data_dir: Path) -> None:
    """Corruption detection records a request that the root memory owner repairs."""
    from core.memory.rag.repair.detect import RAGRepairService, _reset_for_testing
    from server.supervisor.manager import ProcessSupervisor

    _reset_for_testing()
    anima_dir = data_dir / "animas" / "sora"
    (anima_dir / "state").mkdir(parents=True)
    (anima_dir / "vectordb").mkdir()
    (anima_dir / "status.json").write_text('{"enabled": true}', encoding="utf-8")

    service = RAGRepairService(enabled=True, threshold=1, window_minutes=5, cooldown_minutes=60)
    assert service.record_chroma_error(
        anima_name="sora",
        collection="sora_knowledge",
        error="database disk image is malformed",
        source="query",
    )

    state_path = anima_dir / "state" / "rag_repair.json"
    requested = json.loads(state_path.read_text(encoding="utf-8"))
    assert requested["status"] == "requested"
    assert requested["stage"] == "detect"

    sup = ProcessSupervisor(
        animas_dir=data_dir / "animas",
        shared_dir=data_dir / "shared",
        run_dir=data_dir / "run",
    )
    sup.processes["sora"] = object()

    sup.stop_anima = AsyncMock()
    sup.start_anima = AsyncMock()
    sup.send_request = AsyncMock(return_value={"ok": True, "status": "success"})
    await sup._run_supervised_rag_repair("sora", requested)

    sup.send_request.assert_awaited_once()
    request = sup.send_request.await_args
    assert request.args == (
        "sora",
        "repair_memory",
        {"reason": "sqlite_malformed", "include_shared": True},
    )
    assert request.kwargs["timeout"] > 0
    sup.stop_anima.assert_not_awaited()
    sup.start_anima.assert_not_awaited()
    assert "sora" in sup.processes
    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert final_state["status"] == "healthy"
    assert final_state["stage"] == "unfence"
    assert final_state["last_error"] is None
