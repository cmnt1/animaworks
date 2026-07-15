"""Tests for the resumable ``animaworks anima merge`` Phase 1 command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from core.lifecycle.anima_merge import AnimaMergeError, AnimaMergeService, MergePhase
from core.memory.facts import FactRecord, append_fact_records, iter_fact_records


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _stub_rebuild_substeps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        AnimaMergeService,
        "_rebuild_vectordb",
        lambda self: {"chunks_indexed": 6, "archived_vectordb": None},
    )
    monkeypatch.setattr(AnimaMergeService, "_rebuild_entities", lambda self: {"entities": 2})
    monkeypatch.setattr(AnimaMergeService, "_rebuild_bm25", lambda self: {"documents": 4})
    monkeypatch.setattr(AnimaMergeService, "_rebuild_graph_cache", lambda self: {"rebuilt": True})


def _setup_data_dir(tmp_path: Path) -> tuple[Path, Path, Path]:
    data_dir = tmp_path / "data"
    source = data_dir / "animas" / "source"
    target = data_dir / "animas" / "target"
    for anima_dir, name in ((source, "source"), (target, "target")):
        anima_dir.mkdir(parents=True)
        _write(anima_dir / "identity.md", f"# {name}\n")
        _write(anima_dir / "injection.md", f"injection-{name}\n")
        _write(anima_dir / "permissions.json", json.dumps({"allow": [name]}) + "\n")
        _write(anima_dir / "heartbeat.md", f"heartbeat-{name}\n")
        _write(anima_dir / "cron.md", f"cron-{name}\n")
        _write(
            anima_dir / "status.json",
            json.dumps({"enabled": True, "memory_backend": "legacy", "role": "general"}) + "\n",
        )
        (anima_dir / "state").mkdir()
    (data_dir / "shared" / "inbox" / "source").mkdir(parents=True)
    (data_dir / "shared" / "inbox" / "target").mkdir(parents=True)
    _write(data_dir / "shared" / "inbox" / "source" / "message.json", '{"message":"source"}\n')
    _write(data_dir / "shared" / "inbox" / "target" / "message.json", '{"message":"target"}\n')
    return data_dir, source, target


def _add_collision_fixture(data_dir: Path, source: Path, target: Path) -> None:
    _write(source / "episodes" / "2026-07-01.md", "source episode\n")
    _write(target / "episodes" / "2026-07-01.md", "target episode\n")
    _write(source / "knowledge" / "topic.md", "---\norigin: source\n---\nsource knowledge\n")
    _write(target / "knowledge" / "topic.md", "---\norigin: target\n---\ntarget knowledge\n")
    _write(source / "knowledge" / "same.md", "same knowledge\n")
    _write(target / "knowledge" / "same.md", "same knowledge\n")
    _write(source / "procedures" / "deploy.md", "same procedure\n")
    _write(target / "procedures" / "deploy.md", "same procedure\n")
    _write(source / "skills" / "writer" / "SKILL.md", "# Source writer\n")
    _write(target / "skills" / "writer" / "SKILL.md", "# Target writer\n")
    _write(source / "skills" / "quarantine" / "risky" / "SKILL.md", "# Source risky\n")
    _write(target / "skills" / "quarantine" / "risky" / "SKILL.md", "# Target risky\n")
    _write(source / "attachments" / "photo.png", "source image")
    _write(target / "attachments" / "photo.png", "target image")
    _write(source / "state" / "task_queue.jsonl", '{"task_id":"collision-task"}\n')
    _write(target / "state" / "task_queue.jsonl", '{"task_id":"collision-task"}\n')
    _write(source / "state" / "conversations" / "thread-a.json", "{}\n")
    _write(target / "state" / "conversations" / "thread-a.json", "{}\n")

    other = data_dir / "animas" / "other"
    other.mkdir(parents=True)
    _write(other / "status.json", '{"supervisor":"source"}\n')
    _write(
        data_dir / "config.json",
        json.dumps(
            {
                "external_messaging": {
                    "slack": {"anima_mapping": {"C1": "source"}, "bot_token": "must-not-appear"},
                    "discord": {"channel_members": {"D1": ["source", "target"]}},
                }
            }
        )
        + "\n",
    )


def _add_memory_fixture(source: Path, target: Path) -> None:
    duplicate = FactRecord(
        text="Shared fact",
        source_entity="A",
        target_entity="B",
        valid_at="2026-07-01T00:00:00+00:00",
        recorded_at="2026-07-01T01:00:00+00:00",
        source_episode="episodes/2026-07-01.md",
    )
    unique = FactRecord(
        text="Source-only fact",
        source_entity="Source",
        target_entity="Memory",
        valid_at="2026-07-02T00:00:00+00:00",
        recorded_at="2026-07-02T01:00:00+00:00",
        source_episode="episodes/2026-07-01.md",
    )
    append_fact_records(target, [duplicate])
    append_fact_records(source, [duplicate, unique])
    _write(
        source / "state" / "conversation.json",
        json.dumps({"anima_name": "source", "compressed_summary": "Source summary", "turns": []}) + "\n",
    )
    _write(
        source / "transcripts" / "2026-07-01.jsonl",
        json.dumps({"ts": "2026-07-01T10:00:00+09:00", "role": "user", "content": "Remember this"})
        + "\n",
    )
    _write(source / "activity_log" / "2026-07-01.jsonl", '{"event":"audit"}\n')
    _write(source / "token_usage" / "2026-07-01.jsonl", '{"tokens":10}\n')
    _write(source / "prompt_logs" / "2026-07-01.jsonl", '{"secret":"not copied"}\n')
    _write(source / "state" / "skill_usage.jsonl", '{"skill":"writer"}\n')
    _write(source / "state" / "current_state.md", "Work that must be retained\n")
    _write(
        source / "shortterm" / "chat" / "session_state.json",
        json.dumps(
            {
                "original_prompt": "Finish the merge",
                "accumulated_response": "Work in progress",
                "notes": "Do not replay into the active conversation",
            }
        )
        + "\n",
    )
    _write(
        source / "shortterm" / "streaming_journal_chat.jsonl",
        '{"ev":"start","trigger":"chat","session_id":"source-session"}\n'
        '{"ev":"text","t":"Recovered stream text"}\n',
    )


def test_anima_merge_dry_run_manifest_reports_collisions_and_references(tmp_path: Path) -> None:
    data_dir, source, target = _setup_data_dir(tmp_path)
    _add_collision_fixture(data_dir, source, target)

    result = AnimaMergeService(data_dir, "source", "target").run()

    assert result.dry_run is True
    assert result.journal_path is None
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert manifest["memory_backend"] == {"source": "legacy", "target": "legacy"}
    assert len(manifest["collisions"]["episodes"]) == 1
    assert {item["path"] for item in manifest["collisions"]["knowledge"]} == {
        "knowledge/same.md",
        "knowledge/topic.md",
    }
    assert manifest["collisions"]["skills"]
    assert manifest["collisions"]["attachments"][0]["basename"] == "photo.png"
    assert manifest["task_id_collisions"] == ["collision-task"]
    assert manifest["thread_id_collisions"] == ["thread-a"]
    assert manifest["external_references"]["supervisors"] == [
        {"anima": "other", "path": "animas/other/status.json"}
    ]
    mapping_paths = {item["path"] for item in manifest["external_references"]["external_messaging"]}
    assert "external_messaging.slack.anima_mapping.C1" in mapping_paths
    assert "external_messaging.discord.channel_members.D1[0]" in mapping_paths
    assert "must-not-appear" not in result.manifest_json.read_text(encoding="utf-8")
    markdown = result.manifest_markdown.read_text(encoding="utf-8")
    assert "# Anima merge dry-run: source → target" in markdown
    assert "task IDs: collision-task" in markdown


def test_anima_merge_execute_merges_canonical_memory_and_journals_mappings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir, source, target = _setup_data_dir(tmp_path)
    _stub_rebuild_substeps(monkeypatch)
    _add_collision_fixture(data_dir, source, target)
    _add_memory_fixture(source, target)
    protected = {
        name: (target / name).read_bytes()
        for name in ("identity.md", "injection.md", "permissions.json", "heartbeat.md", "cron.md", "status.json")
    }
    source_identity = (source / "identity.md").read_bytes()

    result = AnimaMergeService(data_dir, "source", "target", force=True).run(execute=True)

    assert result.dry_run is False
    assert result.snapshot_path is not None
    assert (result.snapshot_path / "animas" / "source" / "identity.md").is_file()
    assert (result.snapshot_path / "animas" / "target" / "identity.md").is_file()
    assert (result.snapshot_path / "config.json").is_file()
    assert (result.snapshot_path / "shared" / "inbox" / "source" / "message.json").is_file()

    assert (target / "episodes" / "2026-07-01.md").read_text(encoding="utf-8") == "target episode\n"
    assert (target / "episodes" / "2026-07-01_source.md").read_text(encoding="utf-8") == "source episode\n"
    assert (target / "knowledge" / "topic.md").read_text(encoding="utf-8").endswith("target knowledge\n")
    assert (target / "knowledge" / "topic__from_source.md").read_text(encoding="utf-8").endswith(
        "source knowledge\n"
    )
    assert not (target / "knowledge" / "same__from_source.md").exists()
    assert not (target / "procedures" / "deploy__from_source.md").exists()
    assert (target / "skills" / "writer__from_source" / "SKILL.md").is_file()
    assert (target / "skills" / "quarantine" / "risky__from_source" / "SKILL.md").is_file()
    assert (target / "attachments" / "photo.png").read_text(encoding="utf-8") == "target image"
    assert (target / "attachments" / "photo__from_source.png").read_text(encoding="utf-8") == "source image"

    facts = list(iter_fact_records(target, include_expired=True))
    assert {fact.text for fact in facts} == {"Shared fact", "Source-only fact"}
    source_only = next(fact for fact in facts if fact.text == "Source-only fact")
    assert source_only.source_episode == "episodes/2026-07-01_source.md"
    generated = list((target / "episodes").glob("merged_*_from_source_*.md"))
    assert any("conversation" in path.name for path in generated)
    assert any("transcript" in path.name for path in generated)
    generated_content = "\n".join(path.read_text(encoding="utf-8") for path in generated)
    assert "Source summary" in generated_content
    assert "Recovered stream text" in generated_content
    assert "Work that must be retained" in generated_content
    assert "Do not replay into the active conversation" in generated_content
    assert (source / "shortterm" / "streaming_journal_chat.jsonl").is_file()
    assert not (target / "archive" / "merged_from_source").exists()

    for name, content in protected.items():
        assert (target / name).read_bytes() == content
    assert (source / "identity.md").read_bytes() == source_identity
    assert source.is_dir()

    assert result.journal_path is not None
    journal = json.loads(result.journal_path.read_text(encoding="utf-8"))
    assert journal["status"] == "done"
    assert journal["phases"][MergePhase.MERGE_MEMORY.value]["status"] == "completed"
    assert journal["phases"][MergePhase.REBUILD_INDEXES.value]["status"] == "completed"
    artifacts = journal["phases"][MergePhase.MERGE_MEMORY.value]["artifacts"]
    assert artifacts["episode_mapping"]["episodes/2026-07-01.md"] == "episodes/2026-07-01_source.md"
    assert artifacts["facts_read"] == 2
    assert artifacts["facts_appended"] == 1
    assert artifacts["skill_mapping"]["skills/writer"] == "skills/writer__from_source"
    assert artifacts["attachment_mapping"]["attachments/photo.png"] == ("attachments/photo__from_source.png")
    assert artifacts["skill_state_provenance"]["activated"] is False
    assert {item["source"] for item in artifacts["archive_plan"]} == {
        "animas/source/activity_log",
        "animas/source/prompt_logs",
        "animas/source/token_usage",
    }


def test_anima_merge_resume_after_mid_memory_failure_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir, source, target = _setup_data_dir(tmp_path)
    _stub_rebuild_substeps(monkeypatch)
    _add_collision_fixture(data_dir, source, target)
    _add_memory_fixture(source, target)
    service = AnimaMergeService(data_dir, "source", "target", force=True)
    original = service._merge_markdown_tree
    interrupted = False

    def fail_after_knowledge(category: str):
        nonlocal interrupted
        result = original(category)
        if category == "knowledge" and not interrupted:
            interrupted = True
            raise RuntimeError("artificial interruption")
        return result

    monkeypatch.setattr(service, "_merge_markdown_tree", fail_after_knowledge)
    with pytest.raises(RuntimeError, match="artificial interruption"):
        service.run(execute=True)

    failed_journal = json.loads(service.journal_path.read_text(encoding="utf-8"))
    assert failed_journal["phases"][MergePhase.MERGE_MEMORY.value]["status"] == "failed"
    resumed = AnimaMergeService(data_dir, "source", "target", force=True).run(execute=True, resume=True)

    assert resumed.journal_path == service.journal_path
    assert (target / "episodes" / "2026-07-01_source.md").is_file()
    assert not (target / "episodes" / "2026-07-01_source_2.md").exists()
    assert (target / "knowledge" / "topic__from_source.md").is_file()
    assert not (target / "knowledge" / "topic__from_source_2.md").exists()
    assert len(list(iter_fact_records(target, include_expired=True))) == 2
    assert (target / "attachments" / "photo__from_source.png").is_file()
    assert not (target / "attachments" / "photo__from_source_2.png").exists()
    completed = json.loads(service.journal_path.read_text(encoding="utf-8"))
    assert completed["status"] == "done"


def test_anima_merge_attachment_copy_is_idempotent_after_later_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir, source, target = _setup_data_dir(tmp_path)
    _add_collision_fixture(data_dir, source, target)
    _stub_rebuild_substeps(monkeypatch)
    service = AnimaMergeService(data_dir, "source", "target")
    original = service._merge_conversation_history
    interrupted = False

    def fail_after_attachments():
        nonlocal interrupted
        result = original()
        if not interrupted:
            interrupted = True
            raise RuntimeError("after attachment copy")
        return result

    monkeypatch.setattr(service, "_merge_conversation_history", fail_after_attachments)
    with pytest.raises(RuntimeError, match="after attachment copy"):
        service.run(execute=True)

    assert (target / "attachments" / "photo__from_source.png").is_file()
    AnimaMergeService(data_dir, "source", "target").run(execute=True, resume=True)
    assert not (target / "attachments" / "photo__from_source_2.png").exists()
    journal = json.loads(service.journal_path.read_text(encoding="utf-8"))
    mapping = journal["phases"][MergePhase.MERGE_MEMORY.value]["artifacts"]["attachment_mapping"]
    assert mapping == {"attachments/photo.png": "attachments/photo__from_source.png"}


def test_anima_merge_dry_run_only_writes_manifest_and_estimates_rebuild(tmp_path: Path) -> None:
    data_dir, source, target = _setup_data_dir(tmp_path)
    _add_collision_fixture(data_dir, source, target)
    _add_memory_fixture(source, target)

    before = {
        str(path.relative_to(data_dir)): path.read_bytes()
        for root in (source, target)
        for path in root.rglob("*")
        if path.is_file()
    }
    result = AnimaMergeService(data_dir, "source", "target", force=True).run()
    after = {
        str(path.relative_to(data_dir)): path.read_bytes()
        for root in (source, target)
        for path in root.rglob("*")
        if path.is_file()
    }

    assert after == before
    assert not (data_dir / "state" / "merge_journal_source_target.json").exists()
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    estimate = manifest["rebuild_indexes"]
    assert estimate["target"] == "target"
    assert estimate["estimated_inputs"]["facts"] == 2
    assert estimate["neo4j_action"] == "skip_not_configured"


def test_anima_merge_rebuilds_entities_and_bm25_from_merged_source_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir, source, target = _setup_data_dir(tmp_path)
    _add_collision_fixture(data_dir, source, target)
    _add_memory_fixture(source, target)
    monkeypatch.setattr(
        AnimaMergeService,
        "_rebuild_vectordb",
        lambda self: {"chunks_indexed": 6, "archived_vectordb": None},
    )
    monkeypatch.setattr(AnimaMergeService, "_rebuild_graph_cache", lambda self: {"rebuilt": True})
    store = Mock()
    store.upsert.return_value = True
    monkeypatch.setattr(
        AnimaMergeService,
        "_target_vector_components",
        lambda self: (store, Mock()),
    )
    monkeypatch.setattr(
        "core.memory.rag.singleton.generate_embeddings",
        lambda texts, **kwargs: [[0.1, 0.2] for _text in texts],
    )

    result = AnimaMergeService(data_dir, "source", "target", force=True).run(execute=True)

    registry = json.loads((target / "state" / "entity_registry.json").read_text(encoding="utf-8"))
    assert "source" in registry["entities"]
    bm25 = json.loads((target / "state" / "bm25_longterm_index.json").read_text(encoding="utf-8"))
    source_docs = [doc for doc in bm25["documents"] if "topic__from_source.md" in doc["source_file"]]
    assert source_docs
    journal = json.loads(result.journal_path.read_text(encoding="utf-8"))
    substeps = journal["phases"][MergePhase.REBUILD_INDEXES.value]["substeps"]
    assert substeps["entities"]["artifacts"]["entities"] >= 2
    assert substeps["bm25"]["artifacts"]["documents"] >= 1
    assert substeps["neo4j"]["status"] == "skipped"


def test_anima_merge_resume_skips_completed_rebuild_substeps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir, _source, _target = _setup_data_dir(tmp_path)
    calls: list[str] = []
    interrupted = False

    def vector(self):
        calls.append("vectordb")
        return {"chunks_indexed": 1}

    def entities(self):
        nonlocal interrupted
        calls.append("entities")
        if not interrupted:
            interrupted = True
            raise RuntimeError("entity interruption")
        return {"entities": 0}

    monkeypatch.setattr(AnimaMergeService, "_rebuild_vectordb", vector)
    monkeypatch.setattr(AnimaMergeService, "_rebuild_entities", entities)
    monkeypatch.setattr(
        AnimaMergeService,
        "_rebuild_bm25",
        lambda self: calls.append("bm25") or {"documents": 0},
    )
    monkeypatch.setattr(
        AnimaMergeService,
        "_rebuild_graph_cache",
        lambda self: calls.append("graph_cache") or {"rebuilt": False},
    )

    service = AnimaMergeService(data_dir, "source", "target")
    with pytest.raises(RuntimeError, match="entity interruption"):
        service.run(execute=True)
    failed = json.loads(service.journal_path.read_text(encoding="utf-8"))
    substeps = failed["phases"][MergePhase.REBUILD_INDEXES.value]["substeps"]
    assert substeps["vectordb"]["status"] == "completed"
    assert substeps["entities"]["status"] == "failed"

    AnimaMergeService(data_dir, "source", "target").run(execute=True, resume=True)

    assert calls == ["vectordb", "entities", "entities", "bm25", "graph_cache"]


def test_anima_merge_neo4j_rebuild_resets_and_ingests_target_group_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir, source, target = _setup_data_dir(tmp_path)
    for anima_dir in (source, target):
        _write(anima_dir / "status.json", '{"enabled":true,"memory_backend":"neo4j"}\n')
    _write(source / "knowledge" / "source.md", "# Source knowledge\n")
    _write(target / "procedures" / "target.md", "# Target procedure\n")
    _write(target / "skills" / "helper" / "SKILL.md", "# Helper\n")
    _write(
        target / "state" / "conversation.json",
        '{"compressed_summary":"Target conversation summary long enough to ingest"}\n',
    )
    append_fact_records(
        source,
        [
            FactRecord(
                text="Source Neo4j fact",
                source_entity="Source",
                target_entity="Graph",
                valid_at="2026-07-15T00:00:00+00:00",
                recorded_at="2026-07-15T01:00:00+00:00",
            )
        ],
    )
    monkeypatch.setattr(
        AnimaMergeService,
        "_rebuild_vectordb",
        lambda self: {"chunks_indexed": 1, "archived_vectordb": None},
    )
    monkeypatch.setattr(AnimaMergeService, "_rebuild_entities", lambda self: {"entities": 2})
    monkeypatch.setattr(AnimaMergeService, "_rebuild_bm25", lambda self: {"documents": 2})
    monkeypatch.setattr(AnimaMergeService, "_rebuild_graph_cache", lambda self: {"rebuilt": True})
    backend = Mock()
    backend.reset = AsyncMock()
    backend.ingest_file = AsyncMock(return_value=1)
    backend.ingest_text = AsyncMock(return_value=1)
    backend.close = AsyncMock()
    get_backend = Mock(return_value=backend)
    monkeypatch.setattr("core.memory.backend.registry.get_backend", get_backend)

    result = AnimaMergeService(data_dir, "source", "target").run(execute=True)

    get_backend.assert_called_once_with("neo4j", target)
    backend.reset.assert_awaited_once_with()
    assert backend.ingest_file.await_count >= 3
    assert all(call.args[0].is_relative_to(target) for call in backend.ingest_file.await_args_list)
    fact_calls = [call for call in backend.ingest_text.await_args_list if call.kwargs["source"].startswith("fact:")]
    assert len(fact_calls) == 1
    assert fact_calls[0].args[0] == "Source Neo4j fact"
    backend.close.assert_awaited_once_with()
    journal = json.loads(result.journal_path.read_text(encoding="utf-8"))
    neo4j = journal["phases"][MergePhase.REBUILD_INDEXES.value]["substeps"]["neo4j"]
    assert neo4j["status"] == "completed"
    assert neo4j["artifacts"]["facts_ingested"] == 1


def test_anima_merge_preflight_requires_force_for_dangerous_state(tmp_path: Path) -> None:
    data_dir, source, _target = _setup_data_dir(tmp_path)
    _write(source / "state" / ".consolidation_mode", "active\n")
    _write(source / "state" / "pending" / "processing" / "task.json", "{}\n")
    _write(
        source / "shortterm" / "streaming_journal_chat.jsonl",
        '{"ev":"start","trigger":"chat"}\n{"ev":"text","t":"unfinished"}\n',
    )

    with pytest.raises(AnimaMergeError, match="--force"):
        AnimaMergeService(data_dir, "source", "target").run()

    result = AnimaMergeService(data_dir, "source", "target", force=True).run()
    manifest = json.loads(result.manifest_json.read_text(encoding="utf-8"))
    assert len(manifest["preflight_warnings"]) == 3


def test_anima_merge_rejects_backend_mismatch_and_resume_without_execute(tmp_path: Path) -> None:
    data_dir, _source, target = _setup_data_dir(tmp_path)
    _write(target / "status.json", '{"enabled":true,"memory_backend":"neo4j"}\n')

    with pytest.raises(AnimaMergeError, match="backend mismatch"):
        AnimaMergeService(data_dir, "source", "target").run()

    with pytest.raises(AnimaMergeError, match="--resume requires --execute"):
        AnimaMergeService(data_dir, "source", "target").run(resume=True)


def test_anima_merge_quiesce_disables_both_animas_via_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir, _source, _target = _setup_data_dir(tmp_path)
    service = AnimaMergeService(data_dir, "source", "target", gateway_url="http://gateway.test")
    monkeypatch.setattr(service, "_server_running", lambda: True)
    response = Mock()
    response.raise_for_status.return_value = None
    post = Mock(return_value=response)
    monkeypatch.setattr("requests.post", post)

    artifacts = service.quiesce()

    assert artifacts == {"server_running": True, "disabled_via_api": ["source", "target"]}
    assert [call.args[0] for call in post.call_args_list] == [
        "http://gateway.test/api/animas/source/disable",
        "http://gateway.test/api/animas/target/disable",
    ]
    assert all(call.kwargs["timeout"] == 10 for call in post.call_args_list)
