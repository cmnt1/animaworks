"""Unit tests for facts-backed entity connection data."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

from core.memory.facts.connections import build_connections, classify_entity, entity_detail
from core.time_utils import now_local


def _write_fact(
    anima_dir: Path,
    fact_id: str,
    entities: list[str],
    *,
    days_ago: int = 0,
    valid_until: str = "",
    text: str | None = None,
) -> Path:
    facts_dir = anima_dir / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now_local() - timedelta(days=days_ago)).isoformat()
    record = {
        "fact_id": fact_id,
        "text": text or f"Fact {fact_id} about " + "、".join(entities),
        "entities": entities,
        "recorded_at": timestamp,
        "valid_at": timestamp,
        "valid_until": valid_until,
    }
    path = facts_dir / f"{timestamp[:10]}.jsonl"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def test_classify_entity_covers_all_kinds() -> None:
    anima_names = {"alice"}
    user_names = {"taka"}

    assert classify_entity("alice", anima_names, user_names) == "anima"
    assert classify_entity("taka", anima_names, user_names) == "user"
    assert classify_entity("佐藤さん", anima_names, user_names) == "person"
    assert classify_entity("青空クリニック", anima_names, user_names) == "place"
    assert classify_entity("sLaCk", anima_names, user_names) == "service"
    assert classify_entity("旅行計画", anima_names, user_names) == "topic"


def test_build_connections_normalizes_representative_and_filters_files_and_self(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    for index, entity in enumerate(("taka（代表）", "代表", "taka")):
        _write_fact(anima_dir, f"f{index}", [entity, "alice", "current_state.md"])

    data = build_connections(
        anima_dir,
        anima_names={"alice", "bob"},
        user_names={"taka", "zoe"},
        days=None,
    )

    assert data["anima"] == "alice"
    assert data["nodes"] == [
        {"id": "taka", "label": "taka", "kind": "user", "count": 3, "last_seen": now_local().date().isoformat()},
    ]
    assert data["links"] == []
    assert data["totals"] == {"facts": 3, "entities": 1}


def test_build_connections_orders_limits_links_and_filters_expired_and_old_facts(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    _write_fact(anima_dir, "f1", ["Alpha", "Beta"])
    _write_fact(anima_dir, "f2", ["Alpha", "Beta"])
    _write_fact(anima_dir, "f3", ["Alpha", "Gamma"])
    _write_fact(
        anima_dir,
        "expired",
        ["Alpha", "Expired"],
        valid_until=(now_local() - timedelta(minutes=1)).isoformat(),
    )
    _write_fact(anima_dir, "old", ["Old"], days_ago=60)

    data = build_connections(
        anima_dir,
        anima_names={"alice"},
        user_names=set(),
        days=30,
        limit=2,
    )

    assert [(node["label"], node["count"]) for node in data["nodes"]] == [("Alpha", 3), ("Beta", 2)]
    assert data["links"] == [{"source": "Alpha", "target": "Beta", "weight": 2}]
    assert data["totals"] == {"facts": 3, "entities": 3}


def test_entity_detail_returns_recent_facts_related_entities_and_memory_files(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    _write_fact(anima_dir, "older", ["Alpha", "Beta"], days_ago=2)
    _write_fact(anima_dir, "other", ["Alpha", "Gamma"])
    _write_fact(anima_dir, "newer", ["Alpha", "Beta"], text="Newest Alpha fact with Beta")

    knowledge = anima_dir / "knowledge"
    procedures = anima_dir / "procedures"
    (knowledge / "archive").mkdir(parents=True)
    procedures.mkdir()
    (knowledge / "profile.md").write_text(
        "---\ntitle: Alpha profile\n---\n\nAlpha appears here.",
        encoding="utf-8",
    )
    (knowledge / "archive" / "old.md").write_text("Alpha archived", encoding="utf-8")
    (procedures / "alpha-process.md").write_text("# Process\nAlpha steps", encoding="utf-8")

    detail = entity_detail(
        anima_dir,
        "Alpha",
        anima_names={"alice"},
        user_names=set(),
    )

    assert detail["entity"] == "Alpha"
    assert detail["kind"] == "topic"
    assert detail["count"] == 3
    assert [fact["fact_id"] for fact in detail["facts"]] == ["newer", "other", "older"]
    assert detail["facts"][0]["text"] == "Newest Alpha fact with Beta"
    assert {(item["id"], item["weight"]) for item in detail["related"]} == {("Beta", 2), ("Gamma", 1)}
    assert {item["file"] for item in detail["files"]} == {"knowledge/profile.md", "procedures/alpha-process.md"}
    assert next(item for item in detail["files"] if item["file"] == "knowledge/profile.md")["title"] == "Alpha profile"


def test_fact_cache_skips_jsonl_reads_until_signature_changes(tmp_path: Path, monkeypatch) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    first_file = _write_fact(anima_dir, "first", ["Alpha"])
    new_file = _write_fact(anima_dir, "second", ["Beta"], days_ago=1)
    registry_path = anima_dir / "state" / "entity_registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps({"entities": {"alpha": {"canonical": "Alpha", "aliases": ["alpha"]}}}),
        encoding="utf-8",
    )
    original_open = Path.open
    reads: list[Path] = []

    def counted_open(path: Path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if path.suffix == ".jsonl" and "r" in mode:
            reads.append(path)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counted_open)
    kwargs = {"anima_names": {"alice"}, "user_names": set(), "days": None}
    build_connections(anima_dir, **kwargs)
    assert len(reads) == 2

    build_connections(anima_dir, **kwargs)
    assert len(reads) == 2

    _write_fact(anima_dir, "third", ["Gamma"], days_ago=2)
    build_connections(anima_dir, **kwargs)
    assert len(reads) == 5
    assert reads.count(first_file) == 2
    assert reads.count(new_file) == 2

    previous_mtime = registry_path.stat().st_mtime_ns
    registry_path.write_text(
        json.dumps({"entities": {"alpha": {"canonical": "Alpha Prime", "aliases": ["alpha"]}}}),
        encoding="utf-8",
    )
    os.utime(registry_path, ns=(previous_mtime + 1_000_000, previous_mtime + 1_000_000))
    refreshed = build_connections(anima_dir, **kwargs)
    assert len(reads) == 8
    assert reads.count(first_file) == 3
    assert "Alpha Prime" in {node["label"] for node in refreshed["nodes"]}


def test_entity_registry_aliases_are_merged_into_canonical_name(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    _write_fact(anima_dir, "alias", ["Acme Co."])
    registry_path = anima_dir / "state" / "entity_registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "entities": {
                    "acme": {
                        "canonical": "Acme Corporation",
                        "aliases": ["Acme Co.", "ACME"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    data = build_connections(anima_dir, anima_names={"alice"}, user_names=set(), days=None)
    detail = entity_detail(anima_dir, "ACME", anima_names={"alice"}, user_names=set())

    assert [(node["label"], node["count"]) for node in data["nodes"]] == [("Acme Corporation", 1)]
    assert detail["entity"] == "Acme Corporation"
    assert detail["count"] == 1


def test_batch_entities_not_in_the_fact_are_not_counted(tmp_path: Path) -> None:
    anima_dir = tmp_path / "mei"
    # The extractor attaches the whole batch's entities to every fact; only the mentioned ones count.
    _write_fact(anima_dir, "f1", ["Kraken", "Chatwork", "Zoom"], text="Kraken の残高が 0 になった")
    _write_fact(anima_dir, "f2", ["Kraken", "Chatwork", "Zoom"], text="Chatwork で報告した")

    result = build_connections(anima_dir, anima_names={"mei"}, user_names=set(), days=None)

    counts = {node["id"]: node["count"] for node in result["nodes"]}
    assert counts == {"Kraken": 1, "Chatwork": 1}
    assert result["links"] == []
