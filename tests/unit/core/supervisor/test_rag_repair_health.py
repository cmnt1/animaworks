# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Supervisor integration tests for RAG auto-repair triggers."""

from __future__ import annotations

from types import SimpleNamespace

from core.memory.rag.repair import RepairResult
from core.supervisor._mgr_health import HealthMixin


class _SupervisorForTest(HealthMixin):
    def __init__(self) -> None:
        self._restart_counts: dict[str, int] = {"sora": 2}
        self.events: list[tuple[str, dict]] = []

    async def _broadcast_event(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


class _RepairServiceForTest:
    def __init__(self, *, recent: bool) -> None:
        self.recent = recent
        self.calls: list[dict] = []

    def has_recent_corruption(self, anima_name: str) -> bool:
        return self.recent

    def repair_anima_if_allowed(self, anima_name: str, **kwargs):
        self.calls.append({"anima_name": anima_name, **kwargs})
        return RepairResult(
            status="success",
            anima_name=anima_name,
            reason=str(kwargs["reason"]),
            chunks_indexed=7,
            quarantine_path="/tmp/vectordb-corrupt",
        )


async def test_repair_before_restart_on_sigsegv(monkeypatch):
    service = _RepairServiceForTest(recent=False)
    monkeypatch.setattr("core.memory.rag.repair.get_repair_service", lambda: service)

    supervisor = _SupervisorForTest()
    handle = SimpleNamespace(stats=SimpleNamespace(exit_code=-11))

    repaired = await supervisor._maybe_repair_rag_before_restart("sora", handle)

    assert repaired is True
    assert service.calls[0]["reason"] == "native_segfault"
    assert supervisor._restart_counts["sora"] == 0
    assert supervisor.events[0][0] == "system.rag_repair"


async def test_repair_before_restart_on_recent_rag_corruption(monkeypatch):
    service = _RepairServiceForTest(recent=True)
    monkeypatch.setattr("core.memory.rag.repair.get_repair_service", lambda: service)

    supervisor = _SupervisorForTest()
    handle = SimpleNamespace(stats=SimpleNamespace(exit_code=None))

    repaired = await supervisor._maybe_repair_rag_before_restart("sora", handle)

    assert repaired is True
    assert service.calls[0]["reason"] == "recent_rag_corruption"


async def test_no_repair_without_exit_or_recent_signal(monkeypatch):
    service = _RepairServiceForTest(recent=False)
    monkeypatch.setattr("core.memory.rag.repair.get_repair_service", lambda: service)

    supervisor = _SupervisorForTest()
    handle = SimpleNamespace(stats=SimpleNamespace(exit_code=1))

    repaired = await supervisor._maybe_repair_rag_before_restart("sora", handle)

    assert repaired is False
    assert service.calls == []
