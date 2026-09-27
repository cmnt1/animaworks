from __future__ import annotations

import json
from pathlib import Path

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_retire_chain_timeout_keys


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def test_removes_retired_keys_from_config_and_status(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    _write_json(
        config_path,
        {
            "anima_defaults": {"max_chains": 2, "llm_timeout": 600, "model": "claude"},
            "animas": {
                "alpha": {"max_chains": 3, "llm_timeout": 300, "enabled": True},
                "beta": {"model": "gpt"},
            },
        },
    )
    alpha = tmp_path / "animas" / "alpha"
    (alpha / "identity.md").parent.mkdir(parents=True)
    (alpha / "identity.md").write_text("alpha", encoding="utf-8")
    status_path = alpha / "status.json"
    _write_json(status_path, {"max_chains": 4, "llm_timeout": 200, "role": "engineer"})

    result = step_retire_chain_timeout_keys(tmp_path, dry_run=False, verbose=False)

    assert result.error is None
    assert result.changed == 2
    assert json.loads(config_path.read_text(encoding="utf-8")) == {
        "anima_defaults": {"model": "claude"},
        "animas": {"alpha": {"enabled": True}, "beta": {"model": "gpt"}},
    }
    assert json.loads(status_path.read_text(encoding="utf-8")) == {"role": "engineer"}


def test_dry_run_does_not_write_and_repeat_run_is_idempotent(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = '{"anima_defaults": {"max_chains": 2, "llm_timeout": 600}}\n'
    config_path.write_text(original, encoding="utf-8")

    dry_run = step_retire_chain_timeout_keys(tmp_path, dry_run=True, verbose=False)

    assert dry_run.changed == 1
    assert config_path.read_text(encoding="utf-8") == original

    applied = step_retire_chain_timeout_keys(tmp_path, dry_run=False, verbose=False)
    repeated = step_retire_chain_timeout_keys(tmp_path, dry_run=False, verbose=False)

    assert applied.changed == 1
    assert repeated.changed == 0
    assert repeated.skipped == 1
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"anima_defaults": {}}


def test_migration_is_registered_before_version_update(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    ids = [step["id"] for step in runner.list_steps()]

    assert ids.index("retire_chain_timeout_keys") < ids.index("update_version")
