from __future__ import annotations

import json
from pathlib import Path

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_neo4j_config_cleanup


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_cleanup_removes_retired_config_and_status_keys_and_moves_edge_types(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "memory": {
                "backend": "neo4j",
                "neo4j": {"uri": "bolt://localhost:7687"},
                "neo4j_realtime_ingest": True,
                "neo4j_edge_types": [{"name": "MENTORS", "description": "Mentorship"}],
            },
            "system": {"locale": "ja"},
        },
    )
    alice_status = tmp_path / "animas" / "alice" / "status.json"
    _write_json(
        alice_status,
        {
            "enabled": True,
            "memory_backend": "neo4j",
            "neo4j_edge_types": [{"name": "REPORTS_TO", "description": "Reporting line"}],
        },
    )
    bob_status = tmp_path / "animas" / "bob" / "status.json"
    _write_json(
        bob_status,
        {
            "memory_backend": "legacy",
            "fact_edge_types": [{"name": "MENTORS", "description": "Preserve current value"}],
            "neo4j_edge_types": [{"name": "REPORTS_TO", "description": "Old value"}],
        },
    )

    result = step_neo4j_config_cleanup(tmp_path, dry_run=False, verbose=False)

    assert result.error is None
    assert result.changed == 3
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["memory"] == {
        "fact_edge_types": [{"name": "MENTORS", "description": "Mentorship"}],
    }
    assert config["system"] == {"locale": "ja"}
    alice = json.loads(alice_status.read_text(encoding="utf-8"))
    assert "memory_backend" not in alice
    assert "neo4j_edge_types" not in alice
    assert alice["fact_edge_types"] == [{"name": "REPORTS_TO", "description": "Reporting line"}]
    bob = json.loads(bob_status.read_text(encoding="utf-8"))
    assert "memory_backend" not in bob
    assert "neo4j_edge_types" not in bob
    assert bob["fact_edge_types"] == [{"name": "MENTORS", "description": "Preserve current value"}]
    assert any("alice" in detail and "Neo4j data is no longer used" in detail for detail in result.details)

    repeated = step_neo4j_config_cleanup(tmp_path, dry_run=False, verbose=False)
    assert repeated.changed == 0


def test_cleanup_dry_run_leaves_config_and_status_unchanged(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_before = '{"memory":{"backend":"neo4j","neo4j_edge_types":[{"name":"MENTORS","description":"Old"}]}}\n'
    config_path.write_text(config_before, encoding="utf-8")
    status_path = tmp_path / "animas" / "alice" / "status.json"
    status_before = '{"memory_backend":"neo4j","neo4j_edge_types":[{"name":"MENTORS","description":"Old"}]}\n'
    status_path.parent.mkdir(parents=True)
    status_path.write_text(status_before, encoding="utf-8")

    result = step_neo4j_config_cleanup(tmp_path, dry_run=True, verbose=False)

    assert result.error is None
    assert result.changed == 2
    assert config_path.read_text(encoding="utf-8") == config_before
    assert status_path.read_text(encoding="utf-8") == status_before
    assert any("Would move memory.neo4j_edge_types" in detail for detail in result.details)
    assert any("would remove memory_backend" in detail for detail in result.details)


def test_cleanup_is_registered_before_version_update(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    ids = [step["id"] for step in runner.list_steps()]

    assert ids.index("neo4j_config_cleanup") < ids.index("update_version")
