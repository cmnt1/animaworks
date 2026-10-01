from __future__ import annotations

import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.memory.manager import MemoryManager
from core.time_utils import today_local
from core.tooling.handler_memory import MemoryToolsMixin, _MemoryWriteRequest

_ROWS_PER_PROCESS = 100


def _append_episode_rows(anima_dir: str, process_id: int, barrier) -> None:
    manager = object.__new__(MemoryManager)
    manager.episodes_dir = Path(anima_dir) / "episodes"
    barrier.wait(timeout=20)
    for index in range(_ROWS_PER_PROCESS):
        marker = f"process-{process_id}-episode-{index}"
        result = manager.append_episode(f"{marker} {'x' * 1_000}", _defer_index=True)
        assert result is not None


class _EpisodeToolWriter(MemoryToolsMixin):
    def __init__(self, anima_dir: Path) -> None:
        self._anima_dir = anima_dir


def _append_episode_rows_through_tool(anima_dir: Path, process_id: int, barrier) -> None:
    writer = _EpisodeToolWriter(anima_dir)
    episode_path = anima_dir / "episodes" / f"{today_local().isoformat()}.md"
    barrier.wait(timeout=10)
    for index in range(_ROWS_PER_PROCESS):
        marker = f"tool-{process_id}-episode-{index}"
        request = _MemoryWriteRequest(
            rel=f"episodes/{episode_path.name}",
            path=episode_path,
            content=f"{marker} {'y' * 500}\n",
            mode="append",
            was_existing=True,
            write_origin="",
        )
        assert writer._write_episode_memory_file(request).error is None


def test_episode_and_tool_writers_share_the_same_lock(tmp_path: Path) -> None:
    anima_dir = tmp_path / "runtime" / "animas" / "alice"
    episodes_dir = anima_dir / "episodes"
    episodes_dir.mkdir(parents=True)
    barrier = threading.Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        framework_write = executor.submit(_append_episode_rows, str(anima_dir), 0, barrier)
        tool_write = executor.submit(_append_episode_rows_through_tool, anima_dir, 1, barrier)
        framework_write.result()
        tool_write.result()

    episode_path = episodes_dir / f"{today_local().isoformat()}.md"
    content = episode_path.read_text(encoding="utf-8")
    assert sum(content.count(f"process-0-episode-{index} ") for index in range(_ROWS_PER_PROCESS)) == 100
    assert sum(content.count(f"tool-1-episode-{index} ") for index in range(_ROWS_PER_PROCESS)) == 100


def test_episode_append_keeps_all_concurrent_entries(tmp_path: Path) -> None:
    anima_dir = tmp_path / "runtime" / "animas" / "alice"
    episodes_dir = anima_dir / "episodes"
    episodes_dir.mkdir(parents=True)
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    processes = [
        context.Process(target=_append_episode_rows, args=(str(anima_dir), process_id, barrier))
        for process_id in range(2)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=90)
        assert process.exitcode == 0

    episode_path = next(episodes_dir.glob("*.md"))
    content = episode_path.read_text(encoding="utf-8")
    assert sum(content.count(f"process-{process_id}-episode-") for process_id in range(2)) == 200
    for process_id in range(2):
        for index in range(_ROWS_PER_PROCESS):
            assert content.count(f"process-{process_id}-episode-{index} ") == 1
