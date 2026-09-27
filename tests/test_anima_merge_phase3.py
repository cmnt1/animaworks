"""End-to-end tests for Anima merge REWRITE_REFS."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.lifecycle.anima_merge import AnimaMergeService, MergePhase
from core.tasks.queue import TaskQueueManager
from tests.test_anima_merge import (
    _add_rewrite_refs_fixture,
    _read_taskboard_events,
    _read_taskboard_metadata,
    _setup_data_dir,
    _stub_rebuild_substeps,
    _write,
)


def test_anima_merge_rewrite_refs_updates_all_external_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir, source, target = _setup_data_dir(tmp_path)
    _add_rewrite_refs_fixture(data_dir, source, target)
    _stub_rebuild_substeps(monkeypatch)
    source_before = {
        path.relative_to(source).as_posix(): path.read_bytes() for path in source.rglob("*") if path.is_file()
    }

    result = AnimaMergeService(data_dir, "source", "target").run(execute=True)

    source_after = {
        path.relative_to(source).as_posix(): path.read_bytes() for path in source.rglob("*") if path.is_file()
    }
    assert {k: v for k, v in source_after.items() if k != "status.json"} == {
        k: v for k, v in source_before.items() if k != "status.json"
    }
    assert json.loads(source_after["status.json"])["enabled"] is False

    worker_status = json.loads((data_dir / "animas" / "worker" / "status.json").read_text(encoding="utf-8"))
    assert worker_status["supervisor"] == "target"
    config = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))
    assert config["animas"]["worker"]["supervisor"] == "target"
    assert config["external_messaging"]["slack"]["anima_mapping"] == {"C1": "target"}
    assert config["external_messaging"]["discord"]["channel_members"] == {"D1": ["target"]}
    assert config["external_messaging"]["zoom"]["meeting_mapping"] == {"M1": "target"}
    assert config["github_webhook"] == {"reviewer_anima": "target", "dispatcher_anima": "target"}
    assert config["external_messaging"]["slack"]["bot_token"] == "config-secret-must-not-be-journaled"

    channel = json.loads((data_dir / "shared" / "channels" / "team.meta.json").read_text(encoding="utf-8"))
    assert channel == {"members": ["target"], "created_by": "source"}
    meeting = json.loads((data_dir / "shared" / "meetings" / "open.json").read_text(encoding="utf-8"))
    assert meeting["participants"] == ["target"]
    assert meeting["chair"] == "target"
    assert meeting["conversation"][0]["speaker"] == "source"

    assert not list((data_dir / "shared" / "inbox" / "source").glob("*.json"))
    moved_message = json.loads(
        (data_dir / "shared" / "inbox" / "target" / "message__from_source.json").read_text(encoding="utf-8")
    )
    assert moved_message["id"] == "message__from_source"
    assert moved_message["thread_id"] == "message__from_source"
    assert moved_message["to_person"] == "target"
    assert moved_message["from_person"] == "source"
    assert moved_message["meta"]["task_id"] == "collision-task__from_source"
    assert moved_message["content"] == "undelivered"
    moved_report = json.loads((data_dir / "shared" / "inbox" / "target" / "report.json").read_text(encoding="utf-8"))
    assert moved_report["to_person"] == "target"
    assert moved_report["meta"]["task_id"] == "collision-task"
    historical = json.loads((data_dir / "shared" / "inbox" / "worker" / "historical.json").read_text(encoding="utf-8"))
    assert historical["from_person"] == "source"

    merged_episode = target / "episodes" / "2026-07-15_source.md"
    assert "attachments/photo__from_source.png" in merged_episode.read_text(encoding="utf-8")
    assert "episodes/2026-07-15_source.md" in (target / "knowledge" / "linked.md").read_text(encoding="utf-8")
    qualified = (target / "knowledge" / "qualified.md").read_text(encoding="utf-8")
    assert "/api/animas/target/attachments/photo__from_source.png" in qualified
    assert "/api/animas/target/attachments/unique.png" in qualified

    mapping = {
        "collision-task": "collision-task__from_source",
        "terminal-result": "terminal-result",
        "unique-task": "unique-task",
    }
    target_queue = [
        entry.model_dump() for entry in TaskQueueManager(target).store.read("target", archived=True).values()
    ]
    assert {entry["task_id"] for entry in target_queue} == {
        "collision-task",
        "collision-task__from_source",
        "unique-task",
    }
    migrated = next(entry for entry in target_queue if entry["task_id"] == "collision-task__from_source")
    assert migrated["assignee"] == "target"
    worker_queue = next(
        iter(TaskQueueManager(data_dir / "animas" / "worker").store.read("worker").values())
    ).model_dump()
    assert worker_queue["assignee"] == "target"
    assert worker_queue["meta"]["delegated_to"] == "target"
    assert worker_queue["meta"]["delegated_task_id"] == "collision-task__from_source"
    assert worker_queue["meta"]["child_ref"] == {
        "anima_name": "target",
        "task_id": "collision-task__from_source",
    }
    with TaskQueueManager(target).store.reader() as database:
        pending = json.loads(
            database.execute(
                "SELECT input_json FROM tasks WHERE anima='target' AND task_id='collision-task__from_source'"
            ).fetchone()[0]
        )
    assert not (target / "state" / "pending" / "collision-task__from_source.json").exists()
    assert pending["task_id"] == "collision-task__from_source"
    assert pending["depends_on"] == ["unique-task"]
    assert pending["submitted_by"] == pending["reply_to"] == "target"
    assert (target / "state" / "task_results" / "unique-task.md").read_text(encoding="utf-8") == "unique result\n"
    assert (target / "state" / "task_results" / "terminal-result.md").read_text(encoding="utf-8") == "terminal result\n"

    metadata = _read_taskboard_metadata(data_dir / "shared" / "taskboard.sqlite3")
    assert {(row["anima_name"], row["task_id"]) for row in metadata} == {
        ("target", "collision-task"),
        ("target", "collision-task__from_source"),
        ("target", "unique-task"),
    }
    moved = next(row for row in metadata if row["task_id"] == "collision-task__from_source")
    assert moved is not None
    assert moved["source_ref"] == "task_queue:target:collision-task__from_source"
    worker_event = next(
        event
        for event in _read_taskboard_events(data_dir / "shared" / "taskboard.sqlite3")
        if event["anima_name"] == "worker"
    )
    assert json.loads(worker_event["payload_json"])["ref"] == {
        "anima_name": "target",
        "task_id": "collision-task__from_source",
    }

    assert (
        json.loads((data_dir / "run" / "notification_map.json").read_text(encoding="utf-8"))["thread"]["anima"]
        == "target"
    )
    assert (
        json.loads((data_dir / "run" / "discord_thread_map.json").read_text(encoding="utf-8"))["message"]["anima"]
        == "target"
    )
    assert json.loads((data_dir / "animas" / ".bootstrap_retries.json").read_text(encoding="utf-8")) == {"target": 1}
    assert not (data_dir / "run" / "events" / "source").exists()
    assert not (data_dir / "run" / "animas" / "source.lock").exists()

    journal_text = result.journal_path.read_text(encoding="utf-8")
    journal = json.loads(journal_text)
    rewrite = journal["phases"][MergePhase.REWRITE_REFS.value]
    assert rewrite["status"] == "completed"
    assert rewrite["artifacts"]["task_id_mapping"] == mapping
    assert rewrite["substeps"]["memory_references"]["artifacts"]["dangling_references"] == 0
    candidates = rewrite["substeps"]["messaging"]["artifacts"]["credential_disable_candidates"]
    assert candidates == [{"storage": "shared/credentials.json", "key": "SLACK_BOT_TOKEN__source"}]
    assert "credential-secret-must-not-be-journaled" not in journal_text
    assert "target-secret-must-not-be-journaled" not in journal_text


def test_anima_merge_rewrite_refs_stops_on_organization_self_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir, _source, target = _setup_data_dir(tmp_path)
    _write(target / "status.json", '{"enabled":true,"supervisor":"source"}\n')
    _stub_rebuild_substeps(monkeypatch)
    status_before = (target / "status.json").read_bytes()

    service = AnimaMergeService(data_dir, "source", "target")
    with pytest.raises(RuntimeError, match="self-reference: target -> target"):
        service.run(execute=True)

    assert (target / "status.json").read_bytes() == status_before
    journal = json.loads(service.journal_path.read_text(encoding="utf-8"))
    assert journal["phases"][MergePhase.REWRITE_REFS.value]["status"] == "failed"
    assert journal["phases"][MergePhase.REWRITE_REFS.value]["substeps"]["organization"]["status"] == "failed"
    assert MergePhase.REBUILD_INDEXES.value not in journal["phases"]


def test_anima_merge_rewrite_refs_resume_reuses_mapping_without_duplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.lifecycle.anima_merge.external_refs import ExternalRefsRewriter

    data_dir, source, target = _setup_data_dir(tmp_path)
    _add_rewrite_refs_fixture(data_dir, source, target)
    _stub_rebuild_substeps(monkeypatch)
    original = ExternalRefsRewriter.rewrite_ancillary_state
    interrupted = False

    def interrupt_after_rewrite(self: ExternalRefsRewriter):
        nonlocal interrupted
        result = original(self)
        if not interrupted:
            interrupted = True
            raise RuntimeError("rewrite interruption")
        return result

    monkeypatch.setattr(ExternalRefsRewriter, "rewrite_ancillary_state", interrupt_after_rewrite)
    service = AnimaMergeService(data_dir, "source", "target")
    with pytest.raises(RuntimeError, match="rewrite interruption"):
        service.run(execute=True)

    failed = json.loads(service.journal_path.read_text(encoding="utf-8"))
    mapping = failed["phases"][MergePhase.REWRITE_REFS.value]["substeps"]["task_id_mapping"]["artifacts"][
        "task_id_mapping"
    ]
    queue_after_failure = (target / "state" / "task_queue.jsonl").read_bytes()
    events_after_failure = _read_taskboard_events(data_dir / "shared" / "taskboard.sqlite3")

    AnimaMergeService(data_dir, "source", "target").run(execute=True, resume=True)

    completed = json.loads(service.journal_path.read_text(encoding="utf-8"))
    assert completed["status"] == "done"
    assert completed["phases"][MergePhase.REWRITE_REFS.value]["artifacts"]["task_id_mapping"] == mapping
    assert (target / "state" / "task_queue.jsonl").read_bytes() == queue_after_failure
    assert _read_taskboard_events(data_dir / "shared" / "taskboard.sqlite3") == events_after_failure
    assert len(list((data_dir / "shared" / "inbox" / "target").glob("message__from_source*.json"))) == 1


def test_anima_merge_phase3_dry_run_leaves_external_state_and_db_unchanged(tmp_path: Path) -> None:
    data_dir, source, target = _setup_data_dir(tmp_path)
    _add_rewrite_refs_fixture(data_dir, source, target)
    observed = [
        data_dir / "config.json",
        data_dir / "shared" / "taskboard.sqlite3",
        data_dir / "shared" / "inbox" / "source" / "message.json",
        data_dir / "animas" / "worker" / "status.json",
        data_dir / "run" / "notification_map.json",
    ]
    before = {str(path): path.read_bytes() for path in observed}

    result = AnimaMergeService(data_dir, "source", "target").run()

    assert result.dry_run is True
    assert {str(path): path.read_bytes() for path in observed} == before
    assert not (data_dir / "state" / "merge_journal_source_target.json").exists()


def test_merge_rebuild_uses_temporary_owner_and_releases_before_enable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from core.memory.rag import cli_access

    data_dir, _source, _target = _setup_data_dir(tmp_path)
    events: list[str] = []
    access = SimpleNamespace(
        mode="owner",
        store=MagicMock(),
        repair=MagicMock(
            return_value={"ok": True, "status": "success", "chunks_indexed": 9, "archive_path": "/archive/vectordb"}
        ),
    )
    context = MagicMock()
    context.__enter__.return_value = access
    context.__exit__.side_effect = lambda *_args: events.append("owner_closed")
    monkeypatch.setattr(cli_access, "open_vector_access", MagicMock(return_value=context))
    service = AnimaMergeService(data_dir, "source", "target")

    result = service._rebuild_vectordb()

    assert result == {"chunks_indexed": 9, "archived_vectordb": "/archive/vectordb"}
    access.repair.assert_called_once_with(include_shared=True)
    assert service._target_access is not None

    service._server_running = lambda: True
    service._pid_path_alive = lambda _path: True

    class Response:
        def raise_for_status(self) -> None:
            return None

    def post(url: str, **_kwargs):
        assert events == ["owner_closed"]
        assert url.endswith("/api/animas/target/enable")
        return Response()

    with patch("requests.post", side_effect=post) as request:
        result = service._smoke_check_target()

    request.assert_called_once()
    assert result["status"] == "passed"
    assert service._target_access is None
    service._close_target_access()
