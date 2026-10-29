from __future__ import annotations

import pytest

from core.platform.state_writer import LocalStateWriter
from core.tasks.pending_executor import _task_thread_id


def test_short_task_id_is_kept() -> None:
    assert _task_thread_id("6e5ace3706ce") == "6e5ace3706ce"


@pytest.mark.parametrize(
    "task_id",
    [
        "hb-20261017-pr7078-review-conflict-0035",
        "x" * 396,
        "PR #7078 再確認",
    ],
)
def test_unsafe_task_id_maps_to_stable_valid_thread_id(task_id: str) -> None:
    thread_id = _task_thread_id(task_id)

    assert LocalStateWriter._thread_id(thread_id) == thread_id
    assert thread_id == _task_thread_id(task_id)
    assert thread_id != _task_thread_id(task_id + "-other")
