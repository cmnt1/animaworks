from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from core.config.schemas import HousekeepingConfig
from core.memory.maintenance import housekeeping


def _set_tree_age(root: Path, timestamp: float, *, preserve: set[Path] | None = None) -> None:
    preserve = preserve or set()
    candidates = [root, *root.rglob("*")]
    for path in sorted(candidates, key=lambda candidate: len(candidate.parts), reverse=True):
        if path in preserve or path.is_symlink():
            continue
        os.utime(path, (timestamp, timestamp))


def _run_git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _make_repository(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)
    _run_git(path, "config", "user.name", "Housekeeping Test")
    _run_git(path, "config", "user.email", "housekeeping@example.test")
    (path / "README.md").write_text("initial\n", encoding="utf-8")
    _run_git(path, "add", "README.md")
    _run_git(path, "commit", "-m", "initial")


def _add_linked_worktree(repository: Path, path: Path, branch: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(repository), "worktree", "add", "-q", "-b", branch, str(path)],
        check=True,
        capture_output=True,
        text=True,
    )


def _age_worktree(worktree: Path, timestamp: float) -> None:
    _set_tree_age(worktree, timestamp)
    git_dir = Path(_run_git(worktree, "rev-parse", "--absolute-git-dir"))
    head_log = git_dir / "logs" / "HEAD"
    if head_log.exists():
        os.utime(head_log, (timestamp, timestamp))


def test_shared_worktree_status_includes_both_rename_paths(tmp_path: Path) -> None:
    repository = tmp_path / "parent-repository"
    worktree = tmp_path / "worktrees" / "rename-check"
    _make_repository(repository)
    _add_linked_worktree(repository, worktree, "rename-check")
    _run_git(worktree, "mv", "README.md", "renamed.md")

    info = housekeeping._git_worktree_info(worktree)

    assert info is not None
    changed_paths = {path.relative_to(worktree).as_posix() for path in info["changed_paths"]}
    assert changed_paths == {"README.md", "renamed.md"}


def test_codex_sessions_remove_old_files_and_empty_directories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    animas = tmp_path / "data" / "animas"
    old_file = animas / "alice" / ".codex_home" / "sessions" / "old" / "nested" / "rollout.jsonl"
    recent_file = animas / "alice" / ".codex_home" / "sessions" / "recent" / "rollout.jsonl"
    open_file = animas / "alice" / ".codex_home" / "sessions" / "open" / "rollout.jsonl"
    old_file.parent.mkdir(parents=True)
    recent_file.parent.mkdir(parents=True)
    open_file.parent.mkdir(parents=True)
    old_file.write_text("old conversation", encoding="utf-8")
    recent_file.write_text("recent conversation", encoding="utf-8")
    open_file.write_text("open conversation", encoding="utf-8")
    old_timestamp = time.time() - 8 * 86_400
    os.utime(old_file, (old_timestamp, old_timestamp))
    os.utime(open_file, (old_timestamp, old_timestamp))
    monkeypatch.setattr(housekeeping, "_collect_open_paths", lambda _root: {open_file.resolve()})

    result = housekeeping._cleanup_codex_sessions(animas, retention_days=7)

    assert result["deleted_files"] == 1
    assert result["skipped"] == 2
    assert result["freed_bytes"] == len("old conversation")
    assert not old_file.exists()
    assert not old_file.parent.exists()
    assert recent_file.exists()
    assert open_file.exists()


def test_codex_sessions_remove_empty_sessions_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    animas = tmp_path / "data" / "animas"
    sessions_dir = animas / "alice" / ".codex_home" / "sessions"
    old_file = sessions_dir / "rollout.jsonl"
    sessions_dir.mkdir(parents=True)
    old_file.write_text("old conversation", encoding="utf-8")
    old_timestamp = time.time() - 8 * 86_400
    os.utime(old_file, (old_timestamp, old_timestamp))
    monkeypatch.setattr(housekeeping, "_collect_open_paths", lambda _root: set())

    result = housekeeping._cleanup_codex_sessions(animas, retention_days=7)

    assert result["deleted_files"] == 1
    assert result["deleted_dirs"] == 1
    assert not sessions_dir.exists()


def test_anima_scratch_deletes_old_entries_and_keeps_recent_content(tmp_path: Path) -> None:
    animas = tmp_path / "data" / "animas"
    scratch = animas / "alice" / "scratch"
    old_entry = scratch / "task-old"
    recent_entry = scratch / "session-active"
    in_use_entry = scratch / "task-running"
    old_file = old_entry / "work" / "output.txt"
    recent_file = recent_entry / "work" / "output.txt"
    in_use_file = in_use_entry / "work" / "output.txt"
    old_file.parent.mkdir(parents=True)
    recent_file.parent.mkdir(parents=True)
    in_use_file.parent.mkdir(parents=True)
    old_file.write_text("stale", encoding="utf-8")
    recent_file.write_text("active", encoding="utf-8")
    in_use_file.write_text("running", encoding="utf-8")
    old_timestamp = time.time() - 25 * 3600
    _set_tree_age(old_entry, old_timestamp)
    _set_tree_age(recent_entry, old_timestamp, preserve={recent_file})
    _set_tree_age(in_use_entry, old_timestamp)
    os.utime(recent_file, None)

    result = housekeeping._cleanup_anima_scratch(animas, retention_hours=24, in_use_paths={in_use_file})

    assert result["deleted_entries"] == 1
    assert result["skipped"] == 2
    assert not old_entry.exists()
    assert recent_file.exists()
    assert in_use_file.exists()


def test_shared_worktrees_apply_idle_protection_and_git_removal(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    company_root = data_dir / "companies" / "acme" / "shared" / "worktrees"
    repository = tmp_path / "parent-repository"
    _make_repository(repository)
    old_timestamp = time.time() - 25 * 3600
    old_commit_date = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(old_timestamp))
    subprocess.run(
        ["git", "-C", str(repository), "commit", "--amend", "--no-edit", "--date", old_commit_date],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_DATE": old_commit_date,
            "GIT_COMMITTER_DATE": old_commit_date,
        },
    )

    stale_dirty = company_root / "stale-dirty"
    _add_linked_worktree(repository, stale_dirty, "stale-dirty")
    (stale_dirty / "README.md").write_text("old uncommitted change\n", encoding="utf-8")
    _age_worktree(stale_dirty, old_timestamp)

    stale_clean = company_root / "stale-clean"
    _add_linked_worktree(repository, stale_clean, "stale-clean")
    _age_worktree(stale_clean, old_timestamp)

    standalone = company_root / "standalone"
    subprocess.run(["git", "clone", "-q", str(repository), str(standalone)], check=True, capture_output=True)
    _age_worktree(standalone, old_timestamp)

    recent_commit = company_root / "recent-commit"
    _add_linked_worktree(repository, recent_commit, "recent-commit")
    (recent_commit / "committed.txt").write_text("recent commit\n", encoding="utf-8")
    _run_git(recent_commit, "add", "committed.txt")
    _run_git(recent_commit, "commit", "-m", "recent")
    _age_worktree(recent_commit, old_timestamp)

    recent_change = company_root / "recent-change"
    _add_linked_worktree(repository, recent_change, "recent-change")
    recent_file = recent_change / "recent.txt"
    recent_file.write_text("new uncommitted change\n", encoding="utf-8")
    _age_worktree(recent_change, old_timestamp)
    os.utime(recent_file, None)
    for directory in (recent_change, recent_change / "."):
        os.utime(directory, (old_timestamp, old_timestamp))

    protected_marker = company_root / "permanent-marker"
    protected_marker.mkdir(parents=True)
    marker = protected_marker / ".rig-permanent-do-not-delete"
    marker.write_text("preserve", encoding="utf-8")
    _set_tree_age(protected_marker, old_timestamp)

    protected_name = company_root / "AI-Schreiber-debug3-env"
    protected_name.mkdir(parents=True)
    (protected_name / "debug.txt").write_text("preserve", encoding="utf-8")
    _set_tree_age(protected_name, old_timestamp)

    in_use = company_root / "in-use"
    in_use.mkdir(parents=True)
    in_use_file = in_use / "task.txt"
    in_use_file.write_text("working", encoding="utf-8")
    _set_tree_age(in_use, old_timestamp)

    old_residue = company_root / "broken-residue"
    old_residue.mkdir(parents=True)
    (old_residue / "partial.bin").write_bytes(b"old")
    _set_tree_age(old_residue, old_timestamp)
    residue_alias = company_root / "broken-residue-alias"
    if os.name != "nt":
        residue_alias.symlink_to(old_residue, target_is_directory=True)

    global_worktrees = data_dir / "shared" / "worktrees"
    global_worktrees.parent.mkdir(parents=True)
    if os.name != "nt":
        global_worktrees.symlink_to(company_root, target_is_directory=True)

    result = housekeeping._cleanup_shared_worktrees(
        data_dir,
        idle_hours=24,
        in_use_paths={in_use_file},
    )

    assert result["deleted_entries"] == 2
    assert result["failed"] == 0
    assert stale_dirty.exists()
    assert not stale_clean.exists()
    assert standalone.exists()
    assert recent_commit.exists()
    assert recent_file.exists()
    assert marker.exists()
    assert protected_name.exists()
    assert in_use.exists()
    assert not old_residue.exists()
    assert not residue_alias.is_symlink()
    worktree_list = _run_git(repository, "worktree", "list", "--porcelain")
    assert stale_dirty.as_posix() in worktree_list
    assert stale_clean.as_posix() not in worktree_list
    assert recent_commit.as_posix() in worktree_list


@pytest.mark.asyncio
async def test_only_workspace_sweep_rules_collect_in_use_paths_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def collect_paths() -> set[Path]:
        nonlocal calls
        calls += 1
        return set()

    monkeypatch.setattr(housekeeping, "_collect_workspace_in_use_paths", collect_paths)
    monkeypatch.setattr("core.platform.scratch.workspace_cleanup_supported", lambda: True)
    results = await housekeeping.run_housekeeping(
        tmp_path / "data",
        housekeeping=HousekeepingConfig(),
        only={"codex_sessions", "anima_scratch", "shared_worktrees"},
    )

    assert set(results) == {"codex_sessions", "anima_scratch", "shared_worktrees"}
    assert calls == 1


def test_workspace_sweep_config_defaults_and_validation() -> None:
    config = HousekeepingConfig()
    assert config.codex_sessions_retention_days == 7
    assert config.anima_scratch_retention_hours == 24
    assert config.shared_worktrees_idle_hours == 24
    assert config.workspace_sweep_enabled is True

    with pytest.raises(ValueError):
        HousekeepingConfig(codex_sessions_retention_days=0)
    with pytest.raises(ValueError):
        HousekeepingConfig(anima_scratch_retention_hours=0)
    with pytest.raises(ValueError):
        HousekeepingConfig(shared_worktrees_idle_hours=0)


@pytest.mark.asyncio
@pytest.mark.parametrize("only", [None, {"codex_sessions", "anima_scratch", "shared_worktrees"}])
@pytest.mark.parametrize("enabled,supported", [(False, True), (True, False)])
async def test_workspace_sweep_guards_apply_to_daily_and_hourly_runs(tmp_path, monkeypatch, only, enabled, supported):
    monkeypatch.setattr("core.platform.scratch.workspace_cleanup_supported", lambda: supported)
    collect = Mock(side_effect=AssertionError("Disabled cleanup must not scan processes"))
    monkeypatch.setattr(housekeeping, "_collect_workspace_in_use_paths", collect)
    handlers = []
    for key in ("codex_sessions", "anima_scratch", "shared_worktrees"):
        handler = Mock(side_effect=AssertionError("Protected workspace must not be deleted"))
        handlers.append(handler)
        monkeypatch.setitem(housekeeping._HOUSEKEEPING_HANDLERS, key, handler)

    results = await housekeeping.run_housekeeping(
        tmp_path / "data", housekeeping=HousekeepingConfig(workspace_sweep_enabled=enabled), only=only
    )

    collect.assert_not_called()
    for handler in handlers:
        handler.assert_not_called()
    for key in ("codex_sessions", "anima_scratch", "shared_worktrees"):
        assert results[key]["skipped"] is True


def test_terminal_scratch_cleanup_preserves_data_without_process_tracking(tmp_path, monkeypatch):
    from core.platform.scratch import task_scratch_dir
    from core.tasks.pending_executor import _cleanup_task_scratch

    monkeypatch.setattr("core.platform.scratch.workspace_cleanup_supported", lambda: False)
    anima_dir = tmp_path / "alice"
    scratch = task_scratch_dir(anima_dir, "completed")
    scratch.mkdir(parents=True)
    artifact = scratch / "uncommitted.txt"
    artifact.write_text("keep this work", encoding="utf-8")

    _cleanup_task_scratch(anima_dir, "completed", status="done")

    assert artifact.read_text(encoding="utf-8") == "keep this work"


def test_shared_worktrees_keep_repository_when_git_inspection_fails(tmp_path):
    data_dir = tmp_path / "data"
    worktree = data_dir / "shared" / "worktrees" / "broken-repository"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("invalid git metadata", encoding="utf-8")
    artifact = worktree / "work.txt"
    artifact.write_text("keep this work", encoding="utf-8")
    _set_tree_age(worktree, time.time() - 25 * 3600)

    result = housekeeping._cleanup_shared_worktrees(data_dir, idle_hours=24)

    assert result["deleted_entries"] == 0
    assert result["skipped"] == 1
    assert artifact.read_text(encoding="utf-8") == "keep this work"


def test_shared_worktree_changed_after_inspection_is_not_forcibly_removed(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    repository = tmp_path / "repository"
    worktree = data_dir / "shared" / "worktrees" / "concurrent-edit"
    _make_repository(repository)
    _add_linked_worktree(repository, worktree, "concurrent-edit")
    old_timestamp = time.time() - 25 * 3600
    _age_worktree(worktree, old_timestamp)
    inspect = housekeeping._git_worktree_info

    def edit_after_inspection(path):
        info = inspect(path)
        assert not info["changed_paths"]
        info["last_activity_ts"] = old_timestamp
        (path / "README.md").write_text("new concurrent work", encoding="utf-8")
        return info

    monkeypatch.setattr(housekeeping, "_git_worktree_info", edit_after_inspection)

    result = housekeeping._cleanup_shared_worktrees(data_dir, idle_hours=24)

    assert result["deleted_entries"] == 0
    assert result["failed"] == 1
    assert (worktree / "README.md").read_text(encoding="utf-8") == "new concurrent work"
