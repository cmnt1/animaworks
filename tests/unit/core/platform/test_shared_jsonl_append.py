from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

from core.platform.atomic_io import append_jsonl_locked

_ROWS_PER_PROCESS = 200
_PAYLOAD_CHARS = 8_000


def _append_rows(path: str, process_id: int, barrier) -> None:
    target = Path(path)
    barrier.wait(timeout=20)
    for index in range(_ROWS_PER_PROCESS):
        marker = f"process-{process_id}-row-{index}"
        append_jsonl_locked(
            target,
            {
                "process": process_id,
                "index": index,
                "marker": marker,
                "payload": marker + ":" + ("x" * _PAYLOAD_CHARS),
            },
        )


def test_locked_jsonl_append_keeps_long_process_rows_intact(tmp_path: Path) -> None:
    path = tmp_path / "shared" / "messages.jsonl"
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    processes = [context.Process(target=_append_rows, args=(str(path), process_id, barrier)) for process_id in range(2)]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=90)
        assert process.exitcode == 0

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 * _ROWS_PER_PROCESS
    assert {(row["process"], row["index"]) for row in rows} == {
        (process_id, index) for process_id in range(2) for index in range(_ROWS_PER_PROCESS)
    }
    assert all(len(row["payload"]) >= _PAYLOAD_CHARS for row in rows)
