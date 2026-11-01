from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Per-Anima scratch directory paths and removal.

Scratch lives at ``{anima_dir}/scratch/`` and is disposable: task runs get
``scratch/task-<id>/`` (removed when the task ends) and other sessions get
``scratch/<session_type>/`` (removed by housekeeping once idle).
"""

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_SAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9_.-]")
_MAX_COMPONENT_LENGTH = 64
_GIT_LINK_SCAN_DEPTH = 3
_GIT_PRUNE_TIMEOUT_SECONDS = 10


def safe_scratch_component(value: str, *, fallback: str) -> str:
    component = _SAFE_COMPONENT_RE.sub("_", value)[:_MAX_COMPONENT_LENGTH]
    return fallback if component in {"", ".", ".."} else component


def scratch_root(anima_dir: Path) -> Path:
    return Path(anima_dir).resolve() / "scratch"


def task_scratch_dir(anima_dir: Path, task_id: str) -> Path:
    """Return a task scratch path without creating it."""
    return scratch_root(anima_dir) / f"task-{safe_scratch_component(task_id, fallback='unknown')}"


def _linked_worktree_common_dirs(path: Path) -> set[Path]:
    """Find linked worktrees (``.git`` files) under *path* and return their repos' common dirs."""
    common_dirs: set[Path] = set()
    pending = [(path, 0)]
    while pending:
        current, depth = pending.pop()
        git_file = current / ".git"
        if git_file.is_file() and not git_file.is_symlink():
            try:
                text = git_file.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                text = ""
            if text.startswith("gitdir:"):
                gitdir = Path(text.removeprefix("gitdir:").strip())
                if not gitdir.is_absolute():
                    gitdir = current / gitdir
                # <common>/worktrees/<name>
                if gitdir.parent.name == "worktrees":
                    common_dirs.add(gitdir.parent.parent.resolve(strict=False))
            continue
        if depth >= _GIT_LINK_SCAN_DEPTH:
            continue
        try:
            with os.scandir(current) as entries:
                pending.extend(
                    (Path(entry.path), depth + 1) for entry in entries if entry.is_dir(follow_symlinks=False)
                )
        except OSError:
            continue
    return common_dirs


def remove_scratch_entry(path: Path) -> None:
    """Delete a scratch entry and prune worktree registrations it leaves behind.

    Raises ``OSError`` when the tree itself cannot be removed.
    """
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
        return
    common_dirs = _linked_worktree_common_dirs(path)
    shutil.rmtree(path)
    env = {**os.environ, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory", "GIT_CONFIG_VALUE_0": "*"}
    for common_dir in sorted(common_dirs):
        if not common_dir.is_dir():
            continue
        try:
            subprocess.run(
                ["git", f"--git-dir={common_dir}", "worktree", "prune"],
                capture_output=True,
                check=False,
                timeout=_GIT_PRUNE_TIMEOUT_SECONDS,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.debug("git worktree prune failed for %s", common_dir, exc_info=True)
