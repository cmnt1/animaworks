"""Delegation task_id is shared across delegator and receiver, with legacy resolution.

New delegations use one task_id on both sides. The receiver-fallback in
``TaskStore._resolve`` lets legacy rows (where the two sides had different ids)
still be addressed through either id. This module follows the style of
``test_task_publication.py`` and ``test_canonical_tasks.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.messenger import Messenger
from core.schemas import TaskEntry
from core.taskboard.tasks import TaskStore
from core.time_utils import now_iso
from core.tooling.handler_delegation import DelegationMixin


class _DelegationHarness(DelegationMixin):
    def __init__(self, anima_dir: Path, messenger: Messenger) -> None:
        self._anima_dir = anima_dir
        self._anima_name = anima_dir.name
        self._activity = MagicMock()
        self._messenger = messenger
        self._session_origin = "test"
        self._session_origin_chain = []


def _write_status(anima_dir: Path, *, enabled: bool = True, supervisor: str | None = None) -> None:
    payload = {"enabled": enabled}
    if supervisor:
        payload["supervisor"] = supervisor
    (anima_dir / "status.json").write_text(json.dumps(payload), encoding="utf-8")


def _entry(task_id: str) -> TaskEntry:
    return TaskEntry(
        task_id=task_id,
        ts=now_iso(),
        source="anima",
        original_instruction="Do work",
        assignee="sub",
        status="pending",
        summary="Task",
        updated_at=now_iso(),
    )


def test_delegation_shares_single_id_across_both_sides(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    animas_dir = tmp_path / "animas"
    boss_dir = animas_dir / "boss"
    worker_dir = animas_dir / "worker"
    (boss_dir / "state").mkdir(parents=True)
    (worker_dir / "state").mkdir(parents=True)
    _write_status(boss_dir)
    _write_status(worker_dir, supervisor="boss")
    messenger = Messenger(tmp_path / "shared", "boss")
    harness = _DelegationHarness(boss_dir, messenger)

    config = SimpleNamespace(
        animas={
            "boss": SimpleNamespace(supervisor=None, aliases=[]),
            "worker": SimpleNamespace(supervisor="boss", aliases=[]),
        },
        heartbeat=SimpleNamespace(depth_window_s=600, max_depth=6),
    )
    with (
        patch("core.config.models.load_config", return_value=config),
        patch("core.paths.get_animas_dir", return_value=animas_dir),
        patch("core.paths.get_data_dir", return_value=tmp_path),
    ):
        harness._handle_delegate_task(
            {"name": "worker", "instruction": "Prepare the incident summary", "summary": "Incident summary"}
        )

    from core.memory.task_queue import TaskQueueManager

    # 受け側の tasks 行
    worker_view = TaskQueueManager(worker_dir).store.read("worker")
    assert len(worker_view) == 1
    worker_task_id = next(iter(worker_view))

    # 委譲側から見える委譲エントリ
    boss_view = TaskQueueManager(boss_dir).store.read("boss")
    delegated = [entry for entry in boss_view.values() if entry.meta.get("delegated_to") == "worker"]
    assert len(delegated) == 1
    boss_entry = delegated[0]

    # 両側で同じ id が共有され、委譲側の meta も同じ id を指す
    assert boss_entry.task_id == worker_task_id
    assert boss_entry.meta["delegated_task_id"] == worker_task_id


def test_delegator_can_update_via_own_id(monkeypatch, tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "taskboard.sqlite3")
    store.submit("sub", _entry("BBBB"), {"task_id": "BBBB"})
    # 新形式: 委譲側の追跡 id が受け側の実 id と同じ
    store.alias("boss", "BBBB", "sub", "BBBB")

    store.apply("boss", {"_event": "update", "task_id": "BBBB", "status": "done"})
    assert store.get("sub", "BBBB").status == "done"
    assert store.get("boss", "BBBB").status == "done"


def test_receiver_resolves_old_tracking_id(monkeypatch, tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "taskboard.sqlite3")
    store.submit("sub", _entry("BBBB"), {"task_id": "BBBB"})
    # 旧形式データ: 委譲側は AAAA、受け側は BBBB
    store.alias("boss", "AAAA", "sub", "BBBB")

    entry = store.get("sub", "AAAA")
    assert entry is not None
    assert entry.task_id == "BBBB"
    # prepare 受け側自身の解決なので delegated メタは付かない
    assert "delegated_to" not in entry.meta

    store.apply("sub", {"_event": "update", "task_id": "AAAA", "status": "done"})
    assert store.get("sub", "AAAA").status == "done"


def test_delegator_resolves_old_real_id(monkeypatch, tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "taskboard.sqlite3")
    store.submit("sub", _entry("BBBB"), {"task_id": "BBBB"})
    store.alias("boss", "AAAA", "sub", "BBBB")

    entry = store.get("boss", "BBBB")
    assert entry is not None
    # 委譲側の解決なので sub のタスクへ届く
    assert entry.meta.get("delegated_task_id") == "BBBB"


def test_own_task_not_hijacked_by_alias(monkeypatch, tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "taskboard.sqlite3")
    store.submit("sub", _entry("CCCC"), {"task_id": "CCCC"})
    store.alias("boss", "CCCC", "other", "DDDD")

    entry = store.get("sub", "CCCC")
    assert entry is not None
    # 自分が実際に持つタスクはフォールバックに横取りされない
    assert entry.task_id == "CCCC"
    assert "delegated_to" not in entry.meta
