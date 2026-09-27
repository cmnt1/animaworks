from __future__ import annotations

import json
from pathlib import Path

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_phase_b_removal_20260927


def _write_runtime_config(path: Path) -> str:
    original = (
        json.dumps(
            {
                "consolidation": {
                    "knowledge_mutation_enabled": False,
                    "ipc_timeout_per_carryover_item_seconds": 600,
                    "daily_enabled": True,
                }
            },
            indent=2,
        )
        + "\n"
    )
    path.write_text(original, encoding="utf-8")
    return original


def test_phase_b_removal_deletes_retired_settings_and_state_files(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    _write_runtime_config(config_path)
    state_dir = tmp_path / "animas" / "librarian" / "state"
    state_dir.mkdir(parents=True)
    default_state = state_dir / "consolidation_phase_b_carryover.json"
    project_state = state_dir / "consolidation_phase_b_carryover_project-a.json"
    default_state.write_text("{}", encoding="utf-8")
    project_state.write_text("{}", encoding="utf-8")

    result = step_phase_b_removal_20260927(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 3
    assert result.error is None
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"consolidation": {"daily_enabled": True}}
    assert not default_state.exists()
    assert not project_state.exists()


def test_phase_b_removal_skips_when_settings_and_state_are_absent(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"consolidation": {"daily_enabled": True}}), encoding="utf-8")

    result = step_phase_b_removal_20260927(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 0
    assert result.skipped == 2
    assert result.error is None
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"consolidation": {"daily_enabled": True}}


def test_phase_b_removal_dry_run_reports_counts_without_changes(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = _write_runtime_config(config_path)
    state_dir = tmp_path / "animas" / "librarian" / "state"
    state_dir.mkdir(parents=True)
    state_files = [
        state_dir / "consolidation_phase_b_carryover.json",
        state_dir / "consolidation_phase_b_carryover_project-a.json",
    ]
    for path in state_files:
        path.write_text("{}", encoding="utf-8")

    result = step_phase_b_removal_20260927(tmp_path, dry_run=True, verbose=False)

    assert result.changed == 3
    assert any("2 retired consolidation setting(s)" in detail for detail in result.details)
    assert any("2 carryover state file(s)" in detail for detail in result.details)
    assert config_path.read_text(encoding="utf-8") == original
    assert all(path.exists() for path in state_files)


def test_phase_b_removal_is_registered_after_r14_1_and_before_version(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    ids = [step["id"] for step in runner.list_steps()]

    assert ids.index("memory_maintenance_config_cleanup_20260927") + 1 == ids.index("phase_b_removal_20260927")
    assert ids.index("phase_b_removal_20260927") + 1 == ids.index("update_version")
