from __future__ import annotations

import subprocess
from pathlib import Path

from core.platform.scratch import remove_scratch_entry, task_scratch_dir


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


def test_task_scratch_dir_sanitizes_task_id(tmp_path: Path) -> None:
    assert task_scratch_dir(tmp_path, "../a b").name == "task-.._a_b"
    assert task_scratch_dir(tmp_path, "..").name == "task-unknown"
    assert task_scratch_dir(tmp_path, "x" * 100).name == "task-" + "x" * 64


def test_remove_scratch_entry_prunes_linked_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
    scratch = tmp_path / "anima" / "scratch" / "task-1"
    scratch.mkdir(parents=True)
    worktree = scratch / "checkout"
    _git(repo, "worktree", "add", "-q", "-b", "feat", str(worktree))
    (worktree / "dirty.txt").write_text("x", encoding="utf-8")

    remove_scratch_entry(scratch)

    assert not scratch.exists()
    assert str(worktree) not in _git(repo, "worktree", "list", "--porcelain")
    # The branch is no longer held by the deleted worktree.
    _git(repo, "worktree", "add", "-q", str(tmp_path / "again"), "feat")


def test_remove_scratch_entry_handles_files_and_missing(tmp_path: Path) -> None:
    f = tmp_path / "note.txt"
    f.write_text("x", encoding="utf-8")
    remove_scratch_entry(f)
    remove_scratch_entry(tmp_path / "missing")
    assert not f.exists()
