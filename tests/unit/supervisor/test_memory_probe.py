from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from core.supervisor import _mgr_health
from core.supervisor._mgr_health import HealthMixin
from core.supervisor.memory_probe import sample_process_memory


def test_memory_probe_rotates_bounded_jsonl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_MEMORY_PROBE_MAX_BYTES", "1")
    monkeypatch.setenv("ANIMAWORKS_MEMORY_PROBE_KEEP", "2")

    sample_process_memory(anima_name="alice", stage="test", run_dir=tmp_path)
    sample_process_memory(anima_name="alice", stage="test", run_dir=tmp_path)

    active = tmp_path / "memory" / "process_samples.jsonl"
    rotated = tmp_path / "memory" / "process_samples.jsonl.1"
    assert active.exists()
    assert rotated.exists()
    assert json.loads(active.read_text(encoding="utf-8"))["anima"] == "alice"
    assert json.loads(rotated.read_text(encoding="utf-8"))["anima"] == "alice"


def test_health_memory_probe_runs_off_event_loop(tmp_path: Path, monkeypatch) -> None:
    caller_thread = threading.get_ident()
    probe_threads: list[int] = []

    def fake_sample_process_memory(**_kwargs) -> dict:
        probe_threads.append(threading.get_ident())
        return {}

    monkeypatch.setattr(_mgr_health, "sample_process_memory", fake_sample_process_memory)

    class Supervisor(HealthMixin):
        run_dir = tmp_path

    class Handle:
        @staticmethod
        def get_pid() -> int:
            return 123

    asyncio.run(Supervisor()._sample_child_memory("alice", Handle(), stage="test"))

    assert probe_threads
    assert probe_threads[0] != caller_thread
