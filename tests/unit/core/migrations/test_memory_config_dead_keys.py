from __future__ import annotations

import json
from pathlib import Path

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_memory_config_dead_keys_20260927


def test_cleanup_removes_retired_memory_config_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "consolidation": {"duplicate_threshold": 0.85, "daily_enabled": True},
                "rag": {"enable_file_watcher": True, "embedding_model": "model-x"},
                "unrelated": {"preserved": True},
            }
        ),
        encoding="utf-8",
    )

    result = step_memory_config_dead_keys_20260927(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 2
    assert result.skipped == 0
    assert result.error is None
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["consolidation"] == {"daily_enabled": True}
    assert config["rag"] == {"embedding_model": "model-x"}
    assert config["unrelated"] == {"preserved": True}


def test_cleanup_skips_when_keys_are_absent_or_config_is_missing(tmp_path: Path) -> None:
    missing = step_memory_config_dead_keys_20260927(tmp_path, dry_run=False, verbose=False)
    assert missing.changed == 0
    assert missing.skipped == 1

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"consolidation": {}, "rag": {}}), encoding="utf-8")
    result = step_memory_config_dead_keys_20260927(tmp_path, dry_run=False, verbose=False)
    assert result.changed == 0
    assert result.skipped == 1
    assert result.error is None


def test_cleanup_dry_run_does_not_write_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = '{"consolidation": {"duplicate_threshold": 0.85}, "rag": {"enable_file_watcher": true}}\n'
    config_path.write_text(original, encoding="utf-8")

    result = step_memory_config_dead_keys_20260927(tmp_path, dry_run=True, verbose=False)

    assert result.changed == 2
    assert config_path.read_text(encoding="utf-8") == original


def test_cleanup_is_registered_before_update_version(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    ids = [step["id"] for step in runner.list_steps()]

    assert ids.index("memory_config_dead_keys_20260927") < ids.index("update_version")
