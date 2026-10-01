from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the unified migration framework."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.migrations.registry import MigrationReport, MigrationRunner, MigrationStep, StepResult
from core.migrations.tracker import MigrationState, MigrationTracker

# ── Tracker tests ───────────────────────────────────────────


class TestMigrationTracker:
    def test_load_empty(self, tmp_path: Path) -> None:
        tracker = MigrationTracker(tmp_path)
        state = tracker.load()
        assert state.applied_version == ""
        assert state.steps_applied == {}

    def test_save_and_load(self, tmp_path: Path) -> None:
        tracker = MigrationTracker(tmp_path)
        state = MigrationState(
            applied_version="0.5.4",
            steps_applied={"step_a": "2026-03-18T10:00:00"},
            last_migrated_at="2026-03-18T10:00:00",
        )
        tracker.save(state)

        tracker2 = MigrationTracker(tmp_path)
        loaded = tracker2.load()
        assert loaded.applied_version == "0.5.4"
        assert "step_a" in loaded.steps_applied

    def test_is_step_applied(self, tmp_path: Path) -> None:
        tracker = MigrationTracker(tmp_path)
        assert not tracker.is_step_applied("step_x")
        tracker.mark_applied("step_x")
        assert tracker.is_step_applied("step_x")

    def test_corrupt_state_file(self, tmp_path: Path) -> None:
        (tmp_path / "migration_state.json").write_text("not json", encoding="utf-8")
        tracker = MigrationTracker(tmp_path)
        state = tracker.load()
        assert state.applied_version == ""

    def test_mark_applied_updates_version(self, tmp_path: Path) -> None:
        tracker = MigrationTracker(tmp_path)
        with patch("core.migrations.tracker._get_package_version", return_value="1.2.3"):
            tracker.mark_applied("test_step")
        state = tracker.load()
        assert state.applied_version == "1.2.3"


# ── Runner tests ────────────────────────────────────────────


def _ok_step(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    return StepResult(changed=1, skipped=0, details=["did something"])


def _skip_step(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    return StepResult(changed=0, skipped=1, details=["nothing to do"])


def _error_step(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    return StepResult(changed=0, skipped=0, details=[], error="something broke")


def _crash_step(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    raise RuntimeError("unhandled crash")


def _dry_aware_step(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    if dry_run:
        return StepResult(changed=1, skipped=0, details=["would change"])
    (data_dir / "test_marker.txt").write_text("changed", encoding="utf-8")
    return StepResult(changed=1, skipped=0, details=["changed"])


class TestMigrationRunner:
    def _make_runner(self, tmp_path: Path) -> MigrationRunner:
        (tmp_path / "config.json").write_text("{}", encoding="utf-8")
        runner = MigrationRunner(tmp_path)
        runner.register(MigrationStep("s1", "Step 1", "structural", _ok_step))
        runner.register(MigrationStep("s2", "Step 2", "per_anima", _skip_step))
        runner.register(MigrationStep("s3", "Step 3", "db_sync", _error_step))
        return runner

    def test_run_all(self, tmp_path: Path) -> None:
        runner = self._make_runner(tmp_path)
        report = runner.run_all()
        assert isinstance(report, MigrationReport)
        assert len(report.steps) == 3
        assert report.total_changed == 1
        assert report.total_skipped == 1
        assert len(report.errors) == 1

    def test_run_all_skips_applied(self, tmp_path: Path) -> None:
        runner = self._make_runner(tmp_path)
        runner.tracker.mark_applied("s1")
        report = runner.run_all()
        step_results = {s.id: r for s, r in report.steps}
        assert step_results["s1"].skipped == 1
        assert step_results["s1"].changed == 0

    def test_run_all_force_reapplies(self, tmp_path: Path) -> None:
        runner = self._make_runner(tmp_path)
        runner.tracker.mark_applied("s1")
        report = runner.run_all(force=True)
        step_results = {s.id: r for s, r in report.steps}
        assert step_results["s1"].changed == 1

    def test_dry_run_no_side_effects(self, tmp_path: Path) -> None:
        runner = MigrationRunner(tmp_path)
        runner.register(MigrationStep("dry", "Dry test", "structural", _dry_aware_step))
        report = runner.run_all(dry_run=True)
        assert report.total_changed == 1
        assert not (tmp_path / "test_marker.txt").exists()
        assert not runner.tracker.is_step_applied("dry")

    def test_crash_step_handled(self, tmp_path: Path) -> None:
        runner = MigrationRunner(tmp_path)
        runner.register(MigrationStep("crash", "Crash step", "structural", _crash_step))
        report = runner.run_all()
        assert len(report.errors) == 1
        assert "unhandled crash" in report.errors[0]

    def test_list_steps(self, tmp_path: Path) -> None:
        runner = self._make_runner(tmp_path)
        runner.tracker.mark_applied("s1")
        steps = runner.list_steps()
        assert len(steps) == 3
        assert steps[0]["applied"]
        assert not steps[1]["applied"]


# ── Step function tests ─────────────────────────────────────


class TestMigrationSteps:
    @pytest.fixture()
    def data_dir(self, tmp_path: Path) -> Path:
        dd = tmp_path / ".animaworks"
        dd.mkdir()
        (dd / "config.json").write_text("{}", encoding="utf-8")
        (dd / "animas").mkdir()
        return dd

    def _make_anima(self, data_dir: Path, name: str) -> Path:
        d = data_dir / "animas" / name
        d.mkdir(parents=True)
        (d / "identity.md").write_text(f"# {name}", encoding="utf-8")
        (d / "state").mkdir()
        return d

    def test_step_trust_state_per_session_dry_run_and_removal(self, data_dir: Path) -> None:
        from core.migrations.steps import step_trust_state_per_session

        anima = self._make_anima(data_dir, "trust-state")
        legacy_state = anima / "run" / "min_trust_seen"
        legacy_state.parent.mkdir()
        legacy_state.write_text("0", encoding="utf-8")

        dry_result = step_trust_state_per_session(data_dir, dry_run=True, verbose=True)
        assert dry_result.changed == 1
        assert any("would remove run/min_trust_seen" in detail for detail in dry_result.details)
        assert legacy_state.exists()

        result = step_trust_state_per_session(data_dir, dry_run=False, verbose=True)
        assert result.changed == 1
        assert not legacy_state.exists()

    def test_step_update_version(self, data_dir: Path) -> None:
        from core.migrations.steps import step_update_version

        result = step_update_version(data_dir, dry_run=False, verbose=True)
        assert result.changed == 1

    def test_step_engine_timeout_config_cleanup_renames_and_removes_keys(self, data_dir: Path) -> None:
        from core.migrations.steps import step_engine_timeout_config_cleanup

        (data_dir / "config.json").write_text(
            json.dumps({"server": {"busy_hang_threshold": 450, "max_streaming_duration": 1800}}),
            encoding="utf-8",
        )

        result = step_engine_timeout_config_cleanup(data_dir, dry_run=False, verbose=True)

        assert result.error is None
        assert result.changed == 1
        server = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))["server"]
        assert server["runner_liveness_timeout"] == 450
        assert "busy_hang_threshold" not in server
        assert "max_streaming_duration" not in server

    def test_step_engine_timeout_config_cleanup_preserves_new_timeout_value(self, data_dir: Path) -> None:
        from core.migrations.steps import step_engine_timeout_config_cleanup

        (data_dir / "config.json").write_text(
            json.dumps({"server": {"busy_hang_threshold": 450, "runner_liveness_timeout": 600}}),
            encoding="utf-8",
        )

        result = step_engine_timeout_config_cleanup(data_dir, dry_run=False, verbose=True)

        assert result.error is None
        server = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))["server"]
        assert server["runner_liveness_timeout"] == 600
        assert "busy_hang_threshold" not in server

    def test_step_priming_config_cleanup_drops_max_graph_hops(self, data_dir: Path) -> None:
        from core.migrations.steps import step_priming_config_cleanup_20260927

        (data_dir / "config.json").write_text(
            json.dumps({"rag": {"max_graph_hops": 2, "enable_spreading_activation": True}}),
            encoding="utf-8",
        )

        result = step_priming_config_cleanup_20260927(data_dir, dry_run=False, verbose=True)

        assert result.error is None
        assert result.changed == 1
        updated = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))
        assert "max_graph_hops" not in updated["rag"]

    def test_step_priming_config_cleanup_skips_when_setting_missing(self, data_dir: Path) -> None:
        from core.migrations.steps import step_priming_config_cleanup_20260927

        (data_dir / "config.json").write_text(json.dumps({"rag": {}}), encoding="utf-8")

        result = step_priming_config_cleanup_20260927(data_dir, dry_run=False, verbose=True)

        assert result.error is None
        assert result.changed == 0
        assert result.skipped == 1

    def test_priming_config_cleanup_registered_before_version(self, tmp_path: Path) -> None:
        from core.migrations.steps import register_all_steps

        runner = MigrationRunner(tmp_path)
        register_all_steps(runner)
        ids = [item["id"] for item in runner.list_steps()]

        assert ids.index("priming_config_cleanup_20260927") < ids.index("update_version")

    def test_step_taskboard_metadata_retire(self, data_dir: Path) -> None:
        import sqlite3

        from core.migrations.steps import step_taskboard_metadata_retire

        shared = data_dir / "shared"
        shared.mkdir(parents=True, exist_ok=True)
        (data_dir / "config.json").write_text(
            json.dumps(
                {
                    "housekeeping": {
                        "taskboard_suppressed_retention_days": 30,
                        "taskboard_orphan_metadata_stale_hours": 24,
                        "tmp_retention_days": 14,
                    }
                }
            ),
            encoding="utf-8",
        )
        db_path = shared / "taskboard.sqlite3"
        db = sqlite3.connect(db_path)
        db.executescript(
            """
            CREATE TABLE tasks (anima TEXT, task_id TEXT, entry_json TEXT);
            INSERT INTO tasks VALUES ('sakura', 't1', '{"status":"pending","meta":{}}');
            INSERT INTO tasks VALUES ('sakura', 't2', '{"status":"done","meta":{"source_ref":"keep"}}');
            CREATE TABLE taskboard_metadata (
                anima_name TEXT, task_id TEXT, visibility TEXT, column TEXT, source_ref TEXT
            );
            INSERT INTO taskboard_metadata VALUES ('sakura','t1','expired','todo','hermes://x.json#0');
            INSERT INTO taskboard_metadata VALUES ('sakura','t2','archived','done',NULL);
            INSERT INTO taskboard_metadata VALUES ('sakura','t3','waiting','waiting','hermes://y.json#0');
            CREATE TABLE taskboard_events (id INTEGER);
            CREATE TABLE task_aliases (viewer TEXT, alias TEXT);
            """
        )
        db.commit()
        db.close()

        dry = step_taskboard_metadata_retire(data_dir, dry_run=True, verbose=True)
        assert dry.error is None
        assert dry.changed == 1
        db = sqlite3.connect(db_path)
        assert db.execute("SELECT name FROM sqlite_master WHERE name='taskboard_metadata'").fetchone()
        db.close()

        result = step_taskboard_metadata_retire(data_dir, dry_run=False, verbose=True)
        assert result.error is None
        assert result.changed == 1

        db = sqlite3.connect(db_path)
        row = db.execute("SELECT entry_json FROM tasks WHERE task_id='t1'").fetchone()
        assert json.loads(row[0])["meta"]["source_ref"] == "hermes://x.json#0"
        row2 = db.execute("SELECT entry_json FROM tasks WHERE task_id='t2'").fetchone()
        assert json.loads(row2[0])["meta"]["source_ref"] == "keep"
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='taskboard_metadata'"
        ).fetchone()
        assert not db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='taskboard_events'"
        ).fetchone()
        db.close()

        backups = list((shared / "backups").glob("taskboard-pre-metadata-retire-*.sqlite3"))
        assert len(backups) == 1
        # backups contain the pre-drop metadata table
        bdb = sqlite3.connect(backups[0])
        assert bdb.execute("SELECT name FROM sqlite_master WHERE name='taskboard_metadata'").fetchone()
        bdb.close()

        cfg = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))
        assert "taskboard_suppressed_retention_days" not in cfg["housekeeping"]
        assert "taskboard_orphan_metadata_stale_hours" not in cfg["housekeeping"]
        assert cfg["housekeeping"]["tmp_retention_days"] == 14

        second = step_taskboard_metadata_retire(data_dir, dry_run=False, verbose=True)
        assert second.skipped == 1

    def test_shipped_models_json_has_no_mode_b(self) -> None:
        from core.paths import TEMPLATES_DIR

        models = json.loads((TEMPLATES_DIR / "_shared" / "config_defaults" / "models.json").read_text(encoding="utf-8"))
        assert all(str(e.get("mode", "")).upper() != "B" for e in models.values() if isinstance(e, dict))

    def test_register_command_dry_run(self) -> None:
        import argparse

        from cli.commands.migrate_cmd import register_migrate_command

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        register_migrate_command(sub)
        args = parser.parse_args(["migrate", "--dry-run", "--verbose"])
        assert args.dry_run is True
        assert args.verbose is True


# ── Integration: register_all_steps ─────────────────────────


class TestRegisterAllSteps:
    def test_register_all_steps_count(self, tmp_path: Path) -> None:
        from core.migrations.steps import register_all_steps

        runner = MigrationRunner(tmp_path)
        register_all_steps(runner)
        steps = runner.list_steps()
        assert len(steps) >= 15

    def test_0140_runtime_startup_ignores_retired_migration_ids(self, tmp_path: Path) -> None:
        from core.migrations.steps import register_all_steps
        from core.migrations.tracker import assert_supported_runtime_version

        (tmp_path / "config.json").write_text("{}", encoding="utf-8")
        retired_ids = {
            "person_to_anima",
            "config_md_to_json",
            "model_config_to_status",
            "cron_format",
            "split_board_by_company_20260720",
            "channel_company_defaults_20260723",
            "tool_prompts_db_to_md",
            "legacy_flat_skill_migration",
            "v060_resync",
        }
        (tmp_path / "migration_state.json").write_text(
            json.dumps(
                {
                    "applied_version": "0.14.0",
                    "steps_applied": {step_id: "2026-09-29T00:00:00" for step_id in retired_ids},
                    "last_migrated_at": "2026-09-29T00:00:00",
                }
            ),
            encoding="utf-8",
        )
        assert_supported_runtime_version(tmp_path)
        runner = MigrationRunner(tmp_path)
        register_all_steps(runner)
        registered_ids = {step["id"] for step in runner.list_steps()}

        assert retired_ids.isdisjoint(registered_ids)
        report = runner.run_all()
        assert report.errors == []
        assert retired_ids.issubset(runner.tracker.load().steps_applied)

    def test_all_step_ids_unique(self, tmp_path: Path) -> None:
        from core.migrations.steps import register_all_steps

        runner = MigrationRunner(tmp_path)
        register_all_steps(runner)
        ids = [s["id"] for s in runner.list_steps()]
        assert len(ids) == len(set(ids))

    def test_all_categories_present(self, tmp_path: Path) -> None:
        from core.migrations.steps import register_all_steps

        runner = MigrationRunner(tmp_path)
        register_all_steps(runner)
        categories = {s["category"] for s in runner.list_steps()}
        assert "structural" in categories
        assert "per_anima" in categories
        assert "template_sync" in categories
        assert "version" in categories

    def test_engine_timeout_cleanup_registered_after_tools_rename_and_before_version(self, tmp_path: Path) -> None:
        from core.migrations.steps import register_all_steps

        runner = MigrationRunner(tmp_path)
        register_all_steps(runner)
        ids = [item["id"] for item in runner.list_steps()]
        assert ids.index("rename_core_tools_to_integrations") < ids.index("engine_timeout_config_cleanup")
        assert ids.index("engine_timeout_config_cleanup") < ids.index("memory_maintenance_config_cleanup_20260927")
        assert ids.index("memory_maintenance_config_cleanup_20260927") < ids.index("priming_config_cleanup_20260927")
        assert ids.index("priming_config_cleanup_20260927") < ids.index("update_version")
        assert ids.index("engine_timeout_config_cleanup") < ids.index("taskboard_metadata_retire")
        assert ids.index("taskboard_metadata_retire") < ids.index("update_version")
