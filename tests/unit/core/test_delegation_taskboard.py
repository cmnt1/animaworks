from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.messaging.messenger import Messenger
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


def test_delegate_task_writes_canonical_task_and_alias(monkeypatch, tmp_path: Path) -> None:
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
        heartbeat=SimpleNamespace(delegation_dm_enabled=True),
    )
    with (
        patch("core.config.models.load_config", return_value=config),
        patch("core.paths.get_animas_dir", return_value=animas_dir),
        patch("core.paths.get_data_dir", return_value=tmp_path),
    ):
        result = harness._handle_delegate_task(
            {
                "name": "worker",
                "instruction": "Prepare the incident summary",
                "summary": "Incident summary",
            }
        )

    assert "worker" in result
    assert "DM" in result
    from core.tasks.queue import TaskQueueManager

    worker_store = TaskQueueManager(worker_dir).store
    worker_tasks = worker_store.read("worker")
    # The receiver owns one canonical task.
    assert len(worker_tasks) == 1
    sub_task_id = next(iter(worker_tasks))

    # The delegator sees the delegated work through a viewer alias (no taskboard).
    boss_view = TaskQueueManager(boss_dir)._load_all()
    delegated = [task for task in boss_view.values() if task.meta.get("delegated_to") == "worker"]
    assert len(delegated) == 1
    assert delegated[0].meta["delegated_task_id"] == sub_task_id

    # The alias is recorded in the shared store.
    with worker_store.reader() as db:
        alias = db.execute("SELECT anima, task_id FROM task_aliases WHERE viewer='boss' AND anima='worker'").fetchone()
    assert alias is not None
    assert alias["task_id"] == sub_task_id
    # No presentation metadata table is created.
    import sqlite3

    db_path = tmp_path / "shared" / "taskboard.sqlite3"
    if db_path.exists():
        with sqlite3.connect(db_path) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "taskboard_metadata" not in tables


def test_delegate_task_missing_instruction_creates_no_tasks(monkeypatch, tmp_path: Path) -> None:
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
        heartbeat=SimpleNamespace(delegation_dm_enabled=True),
    )
    with (
        patch("core.config.models.load_config", return_value=config),
        patch("core.paths.get_animas_dir", return_value=animas_dir),
        patch("core.paths.get_data_dir", return_value=tmp_path),
    ):
        result = harness._handle_delegate_task(
            {
                "name": "worker",
                "instruction": "",
                "summary": "Incident summary",
            }
        )

    assert "InvalidArguments" in result
    from core.tasks.queue import TaskQueueManager

    assert TaskQueueManager(worker_dir).list_tasks() == []
    assert not (worker_dir / "state" / "task_queue.jsonl").exists()
    assert not (boss_dir / "state" / "task_queue.jsonl").exists()
