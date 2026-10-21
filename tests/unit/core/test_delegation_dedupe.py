"""Delegation deduplication by (delegator, recipient, subject, version).

The registration is consolidated inside the task-store publication transaction;
the recipient's freedom to accept, refuse, or reshape the work is unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.i18n import t
from core.messaging.messenger import Messenger
from core.tasks.dispatch import DelegationResult, publish_delegation
from core.tasks.queue import TaskQueueManager
from core.tooling.handler_delegation import DelegationMixin


class _DelegationHarness(DelegationMixin):
    def __init__(self, anima_dir: Path, messenger: Messenger | None) -> None:
        self._anima_dir = anima_dir
        self._anima_name = anima_dir.name
        self._activity = MagicMock()
        self._messenger = messenger
        self._session_origin = "test"
        self._session_origin_chain = []


def _write_status(anima_dir: Path, *, supervisor: str | None = None) -> None:
    payload: dict[str, object] = {"enabled": True}
    if supervisor:
        payload["supervisor"] = supervisor
    (anima_dir / "status.json").write_text(json.dumps(payload), encoding="utf-8")


def _setup_animas(tmp_path: Path, *, delegators: tuple[str, ...] = ("boss",)) -> tuple[Path, dict[str, Path]]:
    animas_dir = tmp_path / "animas"
    dirs: dict[str, Path] = {}
    for name in (*delegators, "worker"):
        directory = animas_dir / name
        (directory / "state").mkdir(parents=True)
        dirs[name] = directory
        _write_status(directory, supervisor=None if name != "worker" else delegators[0])
    return animas_dir, dirs


def _config(delegators: tuple[str, ...] = ("boss",)) -> SimpleNamespace:
    animas = {name: SimpleNamespace(supervisor=None, aliases=[]) for name in delegators}
    animas["worker"] = SimpleNamespace(supervisor=delegators[0], aliases=[])
    return SimpleNamespace(animas=animas, heartbeat=SimpleNamespace(delegation_dm_enabled=True))


def _delegate(harness: _DelegationHarness, **overrides: str) -> dict[str, object]:
    args = {
        "name": "worker",
        "instruction": "Review the pull request",
        "summary": "[PR #123] Review",
        "subject": "github:acme/repo#123",
        "version": "sha-abc",
    }
    args.update(overrides)
    return json.loads(harness._handle_delegate_task(args))


def _run(harness: _DelegationHarness, animas_dir: Path, config: SimpleNamespace, fn):
    with (
        patch("core.config.models.load_config", return_value=config),
        patch("core.paths.get_animas_dir", return_value=animas_dir),
        patch("core.paths.get_data_dir", return_value=animas_dir.parent),
        patch(
            "core.tooling.handler_delegation.build_outgoing_origin_chain",
            return_value=["anima"],
        ),
    ):
        return fn()


def test_same_open_request_is_consolidated_and_dm_sent_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    animas_dir, dirs = _setup_animas(tmp_path)
    messenger = MagicMock()
    harness = _DelegationHarness(dirs["boss"], messenger)
    config = _config()

    first = _run(harness, animas_dir, config, lambda: _delegate(harness))
    second = _run(harness, animas_dir, config, lambda: _delegate(harness))

    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert first["task_id"] == second["task_id"]
    assert first["status"] == second["status"] == "pending"
    assert set(first) == {"task_id", "status", "deduplicated", "notified", "note"}
    assert first["notified"] is True
    assert second["notified"] is False
    assert "まとめました" in str(second["note"])

    worker_tasks = TaskQueueManager(dirs["worker"]).store.read("worker", archived=True)
    assert len(worker_tasks) == 1
    assert messenger.send.call_count == 1
    dedup_log = t(
        "handler.delegate_dedup_log",
        target_name="worker",
        task_id=second["task_id"],
        summary="[PR #123] Review",
    )
    assert harness._activity.log.call_args_list[-1].kwargs["summary"] == dedup_log


def test_different_version_creates_a_separate_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    animas_dir, dirs = _setup_animas(tmp_path)
    messenger = MagicMock()
    harness = _DelegationHarness(dirs["boss"], messenger)
    config = _config()

    first = _run(harness, animas_dir, config, lambda: _delegate(harness, version="sha-one"))
    second = _run(harness, animas_dir, config, lambda: _delegate(harness, version="sha-two"))

    assert first["task_id"] != second["task_id"]
    assert first["deduplicated"] is False and second["deduplicated"] is False
    assert len(TaskQueueManager(dirs["worker"]).store.read("worker", archived=True)) == 2
    assert messenger.send.call_count == 2


def test_missing_subject_keeps_creating_new_tasks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    animas_dir, dirs = _setup_animas(tmp_path)
    messenger = MagicMock()
    harness = _DelegationHarness(dirs["boss"], messenger)
    config = _config()

    first = _run(harness, animas_dir, config, lambda: _delegate(harness, subject=""))
    second = _run(harness, animas_dir, config, lambda: _delegate(harness, subject=""))

    assert first["task_id"] != second["task_id"]
    assert len(TaskQueueManager(dirs["worker"]).store.read("worker", archived=True)) == 2
    assert messenger.send.call_count == 2


@pytest.mark.parametrize("terminal_status", ["done", "cancelled"])
def test_terminal_request_allows_a_new_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: str,
) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    animas_dir, dirs = _setup_animas(tmp_path)
    messenger = MagicMock()
    harness = _DelegationHarness(dirs["boss"], messenger)
    config = _config()

    first = _run(harness, animas_dir, config, lambda: _delegate(harness))
    TaskQueueManager(dirs["worker"]).update_status(str(first["task_id"]), terminal_status)
    second = _run(harness, animas_dir, config, lambda: _delegate(harness))

    assert second["task_id"] != first["task_id"]
    assert second["deduplicated"] is False
    assert second["status"] == "pending"
    assert len(TaskQueueManager(dirs["worker"]).store.read("worker", archived=True)) == 2
    assert messenger.send.call_count == 2


def test_another_delegator_gets_its_own_task(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    animas_dir, dirs = _setup_animas(tmp_path, delegators=("boss", "other-boss"))
    worker_dir = dirs["worker"]

    def task(task_id: str) -> dict[str, object]:
        return {
            "task_type": "llm",
            "task_id": task_id,
            "title": "[PR #123] Review",
            "description": "Review the pull request",
            "source": "delegation",
            "subject": "github:acme/repo#123",
            "version": "sha-abc",
        }

    first = publish_delegation(worker_dir, task("first-task"), delegator="boss", tracking_task_id="first-task")
    second = publish_delegation(
        worker_dir,
        task("second-task"),
        delegator="other-boss",
        tracking_task_id="second-task",
    )

    assert isinstance(first, DelegationResult)
    assert first.deduplicated is False and second.deduplicated is False
    assert first.task_id == "first-task" and second.task_id == "second-task"
    assert len(TaskQueueManager(worker_dir).store.read("worker", archived=True)) == 2


def _make_test_app():
    from fastapi import FastAPI

    from server.routes.internal import create_internal_router

    app = FastAPI()
    app.state.ws_manager = MagicMock()
    app.state.ws_manager.broadcast = MagicMock()
    app.include_router(create_internal_router(), prefix="/api")
    return app


def _host_payload(sub_task_id: str, tracking_task_id: str, **overrides) -> dict:
    payload = {
        "delegator": "rin",
        "target": "natsume",
        "instruction": "fix the merge conflict on PR #3553",
        "summary": "PR #3553 conflict",
        "sub_task_id": sub_task_id,
        "tracking_task_id": tracking_task_id,
        "workspace": "",
        "subject": "github:acme/repo#3553",
        "version": "sha-abc",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_internal_delegate_route_consolidates_the_same_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    animas = tmp_path / "animas"
    for name in ("rin", "natsume"):
        directory = animas / name
        (directory / "state").mkdir(parents=True)
        _write_status(directory)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("core.paths.get_animas_dir", lambda: animas)

    async with AsyncClient(transport=ASGITransport(app=_make_test_app()), base_url="http://test") as client:
        first_response = await client.post(
            "/api/internal/delegate-task",
            json=_host_payload("aabbccddeeff", "112233445566"),
        )
        second_response = await client.post(
            "/api/internal/delegate-task",
            json=_host_payload("bbccddeeffaa", "223344556677"),
        )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    first = first_response.json()
    second = second_response.json()

    assert first["task_id"] == "aabbccddeeff"
    assert first["status"] == "pending"
    assert first["deduplicated"] is False
    assert first["via_host"] is False
    assert second["task_id"] == first["task_id"]
    assert second["sub_task_id"] == first["task_id"]
    assert second["status"] == "pending"
    assert second["deduplicated"] is True

    assert len(TaskQueueManager(animas / "natsume").store.read("natsume", archived=True)) == 1
