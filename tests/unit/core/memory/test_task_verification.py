from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.memory.task_verification and the done-gate in TaskQueueManager."""

import subprocess
from pathlib import Path

from core.memory.task_queue import TaskQueueManager
from core.memory.task_verification import (
    extract_criteria,
    verify_completion_criteria,
)

# ── Helpers ─────────────────────────────────────────────────────────────


def _make_manager(tmp_path: Path) -> TaskQueueManager:
    anima_dir = tmp_path / "anima"
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)
    return TaskQueueManager(anima_dir)


def _add_task(tqm: TaskQueueManager, meta: dict | None = None):
    return tqm.add_task(
        source="human",
        original_instruction="milestone task",
        assignee="anima",
        summary="milestone",
        meta=meta,
    )


# ── extract_criteria ───────────────────────────────────────────────────


def test_extract_criteria_absent_or_malformed() -> None:
    assert extract_criteria(None) == []
    assert extract_criteria({}) == []
    assert extract_criteria({"completion_criteria": "not-a-list"}) == []
    assert extract_criteria({"completion_criteria": ["not-a-dict", {"type": "path_exists"}]}) == [
        {"type": "path_exists"}
    ]


# ── individual checkers ────────────────────────────────────────────────


def test_path_exists_criterion(tmp_path: Path) -> None:
    existing = tmp_path / "artifact.txt"
    existing.write_text("x", encoding="utf-8")
    assert verify_completion_criteria([{"type": "path_exists", "path": str(existing)}]) == []
    failures = verify_completion_criteria([{"type": "path_exists", "path": str(tmp_path / "missing")}])
    assert len(failures) == 1


def test_file_contains_criterion(tmp_path: Path) -> None:
    f = tmp_path / "report.md"
    f.write_text("結果: 一致 OK\n", encoding="utf-8")
    assert verify_completion_criteria([{"type": "file_contains", "path": str(f), "pattern": "一致 OK"}]) == []
    failures = verify_completion_criteria([{"type": "file_contains", "path": str(f), "pattern": "NG$"}])
    assert len(failures) == 1


def test_unknown_type_fails_closed() -> None:
    failures = verify_completion_criteria([{"type": "no_such_check"}])
    assert failures and "unknown type" in failures[0]


def test_openspec_tasks_checked(tmp_path: Path) -> None:
    tasks_md = tmp_path / "tasks.md"
    tasks_md.write_text(
        "## Phase 1\n- [x] 1.1 計測基盤を実装\n- [ ] 1.2 一致検証を実行\n",
        encoding="utf-8",
    )
    # Unchecked matching box -> failure
    failures = verify_completion_criteria(
        [{"type": "openspec_tasks_checked", "tasks_md": str(tasks_md), "pattern": r"^1\."}]
    )
    assert failures and "unchecked" in failures[0]
    # All matching boxes checked -> pass
    assert (
        verify_completion_criteria(
            [{"type": "openspec_tasks_checked", "tasks_md": str(tasks_md), "pattern": r"^1\.1"}]
        )
        == []
    )
    # No matching boxes -> failure (fail-closed)
    failures = verify_completion_criteria(
        [{"type": "openspec_tasks_checked", "tasks_md": str(tasks_md), "pattern": r"^9\."}]
    )
    assert failures and "no checkbox" in failures[0]


def test_git_commit_criterion(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    env_args = ["-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), *env_args, "commit", "-q", "-m", "feat(fin047): phase1 impl"],
        check=True,
    )
    assert (
        verify_completion_criteria(
            [{"type": "git_commit", "repo": str(repo), "message_pattern": "fin047", "min_count": 1}]
        )
        == []
    )
    failures = verify_completion_criteria(
        [{"type": "git_commit", "repo": str(repo), "message_pattern": "fin047", "min_count": 2}]
    )
    assert len(failures) == 1
    failures = verify_completion_criteria([{"type": "git_commit", "repo": str(tmp_path / "norepo")}])
    assert len(failures) == 1


def test_channel_post_criterion(tmp_path: Path, monkeypatch) -> None:
    import json

    channels = tmp_path / "shared" / "channels"
    channels.mkdir(parents=True)
    (channels / "finance.jsonl").write_text(
        json.dumps({"ts": "2026-07-18T18:00:00+09:00", "from": "airi", "text": "FIN-047 進捗: 一致検証OK"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("core.paths.get_shared_dir", lambda: tmp_path / "shared")

    base = {"type": "channel_post", "channel": "finance", "sender": "airi", "pattern": "(?i)fin-?047"}
    assert verify_completion_criteria([dict(base)]) == []
    # since_ts より前の投稿は無効
    assert verify_completion_criteria([dict(base, since_ts="2026-07-18T18:30:00+09:00")]) != []
    # 別 sender は不一致
    assert verify_completion_criteria([dict(base, sender="momoka")]) != []
    # pattern 不一致
    assert verify_completion_criteria([dict(base, pattern="FIN-099")]) != []
    # チャンネルログなし
    assert verify_completion_criteria([dict(base, channel="nosuch")]) != []


# ── done-gate in TaskQueueManager.update_status ────────────────────────


def test_done_rejected_while_criteria_unmet(tmp_path: Path) -> None:
    tqm = _make_manager(tmp_path)
    artifact = tmp_path / "deliverable.txt"
    entry = _add_task(
        tqm,
        meta={"completion_criteria": [{"type": "path_exists", "path": str(artifact)}]},
    )

    result = tqm.update_status(entry.task_id, "done", summary="done!")
    assert result is not None
    assert result.status == "pending"  # unchanged
    notes = result.meta.get("status_notes")
    assert notes and "completion criteria unmet" in notes[-1]["note"]
    rejection = result.meta.get("completion_rejection")
    assert rejection and rejection["failures"]

    # Persisted state also unchanged
    reloaded = tqm.get_task_by_id(entry.task_id)
    assert reloaded is not None
    assert reloaded.status == "pending"


def test_repeat_identical_rejection_not_reappended(tmp_path: Path) -> None:
    """Retry loops must not grow the queue log with identical rejections."""
    tqm = _make_manager(tmp_path)
    entry = _add_task(
        tqm,
        meta={"completion_criteria": [{"type": "path_exists", "path": str(tmp_path / "never")}]},
    )

    tqm.update_status(entry.task_id, "done")
    size_after_first = tqm.queue_path.stat().st_size
    tqm.update_status(entry.task_id, "done")
    tqm.update_status(entry.task_id, "done")
    assert tqm.queue_path.stat().st_size == size_after_first

    reloaded = tqm.get_task_by_id(entry.task_id)
    assert reloaded is not None
    notes = reloaded.meta.get("status_notes") or []
    assert len([n for n in notes if "completion criteria unmet" in n["note"]]) == 1


def test_done_allowed_once_criteria_met(tmp_path: Path) -> None:
    tqm = _make_manager(tmp_path)
    artifact = tmp_path / "deliverable.txt"
    entry = _add_task(
        tqm,
        meta={"completion_criteria": [{"type": "path_exists", "path": str(artifact)}]},
    )

    artifact.write_text("built", encoding="utf-8")
    result = tqm.update_status(entry.task_id, "done")
    assert result is not None
    assert result.status == "done"


def test_done_gate_ignores_tasks_without_criteria(tmp_path: Path) -> None:
    tqm = _make_manager(tmp_path)
    entry = _add_task(tqm, meta=None)
    result = tqm.update_status(entry.task_id, "done")
    assert result is not None
    assert result.status == "done"


def test_cancel_not_gated_by_criteria(tmp_path: Path) -> None:
    tqm = _make_manager(tmp_path)
    entry = _add_task(
        tqm,
        meta={"completion_criteria": [{"type": "path_exists", "path": str(tmp_path / "never")}]},
    )
    result = tqm.update_status(entry.task_id, "cancelled")
    assert result is not None
    assert result.status == "cancelled"
