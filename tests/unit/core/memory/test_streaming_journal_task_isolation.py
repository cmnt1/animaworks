from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Task-specific StreamingJournal concurrency regression tests."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

from core.memory.streaming_journal import StreamingJournal


def test_task_journals_do_not_truncate_or_unlink_each_other(tmp_path: Path) -> None:
    """Concurrent task journals remain isolated throughout their lifecycles."""
    anima_dir = tmp_path / "anima"
    task_a = StreamingJournal(anima_dir, session_type="task", thread_id="task-a")
    task_b = StreamingJournal(anima_dir, session_type="task", thread_id="task-b")
    opened = Barrier(3)
    written = Barrier(3)
    finalize_a = Event()
    finalize_b = Event()
    finalized_a = Event()
    finalized_b = Event()

    def run_journal(
        journal: StreamingJournal,
        text: str,
        finalize_gate: Event,
        finalized: Event,
    ) -> None:
        journal.open(trigger="taskexec", session_id=text)
        opened.wait(timeout=5)
        # Exceed the flush threshold so the payload is durable while the
        # other task's journal is still open.
        journal.write_text(text * 501)
        written.wait(timeout=5)
        assert finalize_gate.wait(timeout=5)
        journal.finalize(summary=f"{text} done")
        finalized.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(run_journal, task_a, "A", finalize_a, finalized_a)
        future_b = pool.submit(run_journal, task_b, "B", finalize_b, finalized_b)
        try:
            opened.wait(timeout=5)
            written.wait(timeout=5)

            assert task_a._journal_path.exists()
            assert task_b._journal_path.exists()
            assert set(StreamingJournal.list_orphan_thread_ids(anima_dir, "task")) == {
                "task-a",
                "task-b",
            }
            recovery_a = StreamingJournal.recover(anima_dir, "task", thread_id="task-a")
            recovery_b = StreamingJournal.recover(anima_dir, "task", thread_id="task-b")
            assert recovery_a is not None
            assert recovery_a.recovered_text == "A" * 501
            assert recovery_b is not None
            assert recovery_b.recovered_text == "B" * 501

            # Finalizing task A must not truncate or unlink task B's nested
            # journal, and orphan discovery must stop reporting only task A.
            finalize_a.set()
            assert finalized_a.wait(timeout=5)
            assert not task_a._journal_path.exists()
            assert task_b._journal_path.exists()
            assert StreamingJournal.list_orphan_thread_ids(anima_dir, "task") == ["task-b"]
            recovery_b = StreamingJournal.recover(anima_dir, "task", thread_id="task-b")
            assert recovery_b is not None
            assert recovery_b.recovered_text == "B" * 501

            finalize_b.set()
            assert finalized_b.wait(timeout=5)
            assert not task_b._journal_path.exists()
            assert StreamingJournal.list_orphan_thread_ids(anima_dir, "task") == []
            assert StreamingJournal.has_orphan(anima_dir, "task") is False
        finally:
            finalize_a.set()
            finalize_b.set()

        future_a.result(timeout=5)
        future_b.result(timeout=5)
