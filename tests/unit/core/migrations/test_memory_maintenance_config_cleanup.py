from __future__ import annotations

import json
from pathlib import Path

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_memory_maintenance_config_cleanup_20260927


def test_cleanup_removes_retired_hygiene_setting_only(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "housekeeping": {
                    "hygiene_grace_days": 21,
                    "archive_versions_keep_per_file": 5,
                    "enabled": True,
                }
            }
        ),
        encoding="utf-8",
    )

    result = step_memory_maintenance_config_cleanup_20260927(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 1
    assert result.error is None
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["housekeeping"] == {"archive_versions_keep_per_file": 5, "enabled": True}


def test_cleanup_skips_when_setting_is_absent_or_config_missing(tmp_path: Path) -> None:
    assert step_memory_maintenance_config_cleanup_20260927(tmp_path, dry_run=False, verbose=False).skipped == 1

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"housekeeping": {"enabled": True}}), encoding="utf-8")
    result = step_memory_maintenance_config_cleanup_20260927(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 0
    assert result.skipped == 1
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"housekeeping": {"enabled": True}}


def test_cleanup_dry_run_does_not_write_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = '{"housekeeping": {"hygiene_grace_days": 21}}\n'
    config_path.write_text(original, encoding="utf-8")

    result = step_memory_maintenance_config_cleanup_20260927(tmp_path, dry_run=True, verbose=False)

    assert result.changed == 1
    assert config_path.read_text(encoding="utf-8") == original


def test_cleanup_is_registered_after_engine_timeout_cleanup_and_before_version(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    ids = [step["id"] for step in runner.list_steps()]

    assert ids.index("engine_timeout_config_cleanup") + 1 == ids.index("memory_maintenance_config_cleanup_20260927")
    assert ids.index("memory_maintenance_config_cleanup_20260927") + 1 == ids.index("update_version")
