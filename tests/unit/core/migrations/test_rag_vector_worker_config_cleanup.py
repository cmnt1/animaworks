from __future__ import annotations

import json
from pathlib import Path

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_rag_vector_worker_config_cleanup

_RETIRED_KEYS = {
    "vector_worker_enabled",
    "vector_worker_host",
    "vector_worker_port",
    "vector_worker_startup_timeout_seconds",
    "vector_worker_request_timeout_seconds",
    "vector_worker_restart_backoff_seconds",
    "vector_worker_shutdown_timeout_seconds",
    "vector_worker_fallback_direct",
    "startup_repair_preflight_enabled",
    "startup_repair_window_minutes",
    "repair_stop_anima",
}


def test_removes_retired_settings_and_preserves_other_config_and_data(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = {
        "rag": {**{key: f"retired-{key}" for key in _RETIRED_KEYS}, "enabled": True},
        "server": {"port": 18500},
    }
    config_path.write_text(json.dumps(original), encoding="utf-8")
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    vector_log = logs_dir / "vector-worker.log.1"
    vector_log.write_text("keep", encoding="utf-8")
    shared_db = tmp_path / "vectordb"
    shared_db.mkdir()

    result = step_rag_vector_worker_config_cleanup(tmp_path, dry_run=False, verbose=False)

    assert result.error is None
    assert result.changed == 1
    updated = json.loads(config_path.read_text(encoding="utf-8"))
    assert updated == {"rag": {"enabled": True}, "server": {"port": 18500}}
    assert vector_log.read_text(encoding="utf-8") == "keep"
    assert shared_db.is_dir()
    assert any("Left logs/vector-worker.log* untouched" in detail for detail in result.details)
    assert any("may be removed manually" in detail for detail in result.details)


def test_dry_run_is_non_mutating_and_second_run_is_idempotent(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = json.dumps({"rag": {"vector_worker_enabled": True, "custom": 7}})
    config_path.write_text(original, encoding="utf-8")

    dry_run = step_rag_vector_worker_config_cleanup(tmp_path, dry_run=True, verbose=False)

    assert dry_run.changed == 1
    assert config_path.read_text(encoding="utf-8") == original

    applied = step_rag_vector_worker_config_cleanup(tmp_path, dry_run=False, verbose=False)
    repeated = step_rag_vector_worker_config_cleanup(tmp_path, dry_run=False, verbose=False)

    assert applied.changed == 1
    assert repeated.changed == 0
    assert repeated.skipped == 1
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"rag": {"custom": 7}}


def test_migration_is_registered_before_version_update(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    ids = [step["id"] for step in runner.list_steps()]

    assert ids.index("rag_vector_worker_config_cleanup") < ids.index("update_version")
