from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

from core.memory.activity.logger import ActivityEntry, ActivityLogger


def _append_large_activity_rows(anima_dir: str, process_id: int, barrier) -> None:
    logger = ActivityLogger(Path(anima_dir))
    barrier.wait(timeout=10)
    for index in range(4):
        marker = f"process-{process_id}-entry-{index}"
        entry = ActivityEntry(
            ts="2026-09-27T00:00:00",
            type="concurrent_test",
            content=marker + ":" + ("x" * 9_000),
        )
        assert logger._append(entry)


def test_large_activity_rows_remain_valid_json_across_processes(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    processes = [
        context.Process(target=_append_large_activity_rows, args=(str(anima_dir), process_id, barrier))
        for process_id in range(2)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0

    log_path = anima_dir / "activity_log" / "2026-09-27.jsonl"
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 8
    assert {row["content"].split(":", 1)[0] for row in rows} == {
        f"process-{process_id}-entry-{index}" for process_id in range(2) for index in range(4)
    }
