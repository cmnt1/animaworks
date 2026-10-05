"""AnimaRunner recovers task runners orphaned by an earlier root process."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call

import psutil
import pytest

from core.runtime.runner import AnimaRunner


def _make_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[AnimaRunner, Path]:
    data_dir = tmp_path / "runtime"
    anima_dir = data_dir / "animas" / "rin"
    anima_dir.mkdir(parents=True)
    shared_dir = data_dir / "shared"
    shared_dir.mkdir()
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", "prior-anima-dir")
    runner = AnimaRunner("rin", tmp_path / "rin.sock", data_dir / "animas", shared_dir)
    return runner, data_dir


def _task_runner_process(
    pid: int,
    data_dir: Path,
    *,
    anima_arg: str = "rin",
    module_name: str = "core.runtime.task_runner",
    env_error: bool = False,
) -> MagicMock:
    process = MagicMock()
    process.pid = pid
    process.cmdline.return_value = [
        "/usr/bin/python",
        "-m",
        module_name,
        "--anima",
        anima_arg,
        "--lane",
        "task",
    ]
    if env_error:
        process.environ.side_effect = psutil.AccessDenied(pid=pid)
    else:
        process.environ.return_value = {"ANIMAWORKS_DATA_DIR": str(data_dir)}
    process.children.return_value = []
    return process


def _install_process_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    task_processes: list[MagicMock],
    *,
    descendants: list[MagicMock] | None = None,
) -> None:
    current = MagicMock()
    current.children.return_value = descendants or []
    monkeypatch.setattr("core.runtime.runner.psutil.Process", lambda *_args: current)
    monkeypatch.setattr("core.runtime.runner.psutil.process_iter", lambda: iter(task_processes))


@pytest.mark.parametrize(
    "module_name",
    [
        "core.runtime.task_runner",
        "core.runtime.task_runner",  # legacy name until 2026-11 (S3a)
    ],
)
def test_matching_orphan_task_runner_is_terminated_as_a_process_group(
    module_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, data_dir = _make_runner(tmp_path, monkeypatch)
    orphan = _task_runner_process(4321, data_dir, module_name=module_name)
    _install_process_snapshot(monkeypatch, [orphan])
    monkeypatch.setattr("core.runtime.runner.psutil.wait_procs", lambda targets, timeout: (targets, []))

    with pytest.MonkeyPatch.context() as scoped:
        terminate = MagicMock()
        scoped.setattr("core.runtime.runner.terminate_pid", terminate)
        runner._cleanup_orphaned_task_runners()

    terminate.assert_called_once_with(4321, include_children=True)


@pytest.mark.parametrize("case", ["different_data_dir", "partial_name", "unreadable_environment", "own_descendant"])
def test_non_matching_or_uninspectable_process_is_not_terminated(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, data_dir = _make_runner(tmp_path, monkeypatch)
    process_data_dir = tmp_path / "other-runtime" if case == "different_data_dir" else data_dir
    orphan = _task_runner_process(
        4322,
        process_data_dir,
        anima_arg="rin2" if case == "partial_name" else "rin",
        env_error=case == "unreadable_environment",
    )
    descendants = [orphan] if case == "own_descendant" else []
    _install_process_snapshot(monkeypatch, [orphan], descendants=descendants)
    terminate = MagicMock()
    monkeypatch.setattr("core.runtime.runner.terminate_pid", terminate)

    runner._cleanup_orphaned_task_runners()

    terminate.assert_not_called()


def test_surviving_task_runner_group_is_force_killed_after_grace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, data_dir = _make_runner(tmp_path, monkeypatch)
    orphan = _task_runner_process(4323, data_dir)
    _install_process_snapshot(monkeypatch, [orphan])
    monkeypatch.setattr(
        "core.runtime.runner.psutil.wait_procs",
        lambda targets, timeout: ([], targets),
    )
    terminate = MagicMock()
    monkeypatch.setattr("core.runtime.runner.terminate_pid", terminate)

    runner._cleanup_orphaned_task_runners()

    assert terminate.call_args_list == [
        call(4323, include_children=True),
        call(4323, force=True, include_children=True),
    ]
    orphan.kill.assert_called_once()
