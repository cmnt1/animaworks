from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch


def test_vector_worker_circuit_rejection_logs_are_rate_limited(monkeypatch, caplog) -> None:
    from core.memory.rag import vector_worker

    monkeypatch.setattr(vector_worker, "_CIRCUIT_REJECTION_LOG_INTERVAL_SECONDS", 60.0)
    vector_worker._write_circuit_breakers.clear()
    vector_worker._write_circuit_breakers["shared:knowledge"] = {
        "owner": "shared",
        "collection": "knowledge",
        "consecutive_failures": 3,
        "next_retry_at": 100.0,
        "last_logged_at": 0.0,
        "suppressed_count": 0,
    }

    with (
        caplog.at_level(logging.ERROR, logger="animaworks.rag.vector_worker"),
        patch("core.memory.rag.vector_worker.time.monotonic", side_effect=[1.0, 2.0, 70.0]),
    ):
        assert vector_worker._before_vector_write(None, "knowledge") is not None
        assert vector_worker._before_vector_write(None, "knowledge") is not None
        assert vector_worker._before_vector_write(None, "knowledge") is not None

    messages = [record.getMessage() for record in caplog.records if "circuit breaker open" in record.getMessage()]
    assert len(messages) == 2
    assert "suppressed=0" in messages[0]
    assert "suppressed=1" in messages[1]


def test_vector_worker_escalates_three_lightweight_failures_once_per_cooldown(caplog) -> None:
    from core.memory.rag import vector_worker

    class FailingStore:
        def operation(self) -> bool:
            return False

        def consume_lightweight_self_heal_failure(self) -> bool:
            return True

    store = FailingStore()
    reset = MagicMock()

    vector_worker._self_heal_failures.clear()
    vector_worker._self_heal_last_escalated_at.clear()
    with (
        patch("core.memory.rag.singleton.get_vector_store", return_value=store),
        patch("core.memory.rag.singleton.reset_vector_store", reset),
        patch("core.memory.rag.vector_worker.time.monotonic", side_effect=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
        caplog.at_level(logging.WARNING, logger="animaworks.rag.vector_worker"),
    ):
        for _ in range(6):
            assert vector_worker._call_vector_store("sora", lambda current: current.operation()) is False

    reset.assert_called_once_with("sora")
    messages = [record.getMessage() for record in caplog.records if "Escalating repeated lightweight" in record.getMessage()]
    assert len(messages) == 1
