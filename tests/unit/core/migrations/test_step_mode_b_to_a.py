"""Tests for retired Mode B configuration migration."""

from __future__ import annotations

import json
from pathlib import Path

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_retired_mode_to_a


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _create_legacy_data(data_dir: Path) -> tuple[Path, Path]:
    _write_json(
        data_dir / "config.json",
        {
            "anima_defaults": {
                "execution_mode": "b",
                "fallback_models": ["B:ollama/qwen3:14b"],
            },
            "animas": {
                "foo": {
                    "execution_mode": "basic",
                    "fallback_models": ["b:openai/gpt-4.1"],
                },
            },
            "model_modes": {"ollama/*": "B"},
        },
    )
    anima_dir = data_dir / "animas" / "foo"
    (anima_dir / "identity.md").parent.mkdir(parents=True, exist_ok=True)
    (anima_dir / "identity.md").write_text("foo", encoding="utf-8")
    status_path = anima_dir / "status.json"
    _write_json(
        status_path,
        {
            "execution_mode": "B",
            "resolved_mode": "b",
            "fallback_models": ["B:grok/grok-4.5"],
        },
    )
    return data_dir / "config.json", status_path


def test_maps_config_and_status_values_to_mode_a_and_is_idempotent(tmp_path: Path) -> None:
    config_path, status_path = _create_legacy_data(tmp_path)

    first = step_retired_mode_to_a(tmp_path, dry_run=False, verbose=False)

    assert first.error is None
    assert first.changed == 2
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["anima_defaults"]["execution_mode"] == "A"
    assert config["anima_defaults"]["fallback_models"] == ["a:ollama/qwen3:14b"]
    assert config["animas"]["foo"]["execution_mode"] == "A"
    assert config["animas"]["foo"]["fallback_models"] == ["a:openai/gpt-4.1"]
    assert config["model_modes"] == {"ollama/*": "A"}
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["execution_mode"] == "A"
    assert status["resolved_mode"] == "A"
    assert status["fallback_models"] == ["a:grok/grok-4.5"]

    second = step_retired_mode_to_a(tmp_path, dry_run=False, verbose=False)
    assert second.error is None
    assert second.changed == 0


def test_dry_run_reports_changes_without_writing(tmp_path: Path) -> None:
    config_path, status_path = _create_legacy_data(tmp_path)
    config_before = config_path.read_bytes()
    status_before = status_path.read_bytes()

    result = step_retired_mode_to_a(tmp_path, dry_run=True, verbose=False)

    assert result.error is None
    assert result.changed == 2
    assert all(detail.startswith("Would ") for detail in result.details)
    assert config_path.read_bytes() == config_before
    assert status_path.read_bytes() == status_before


def test_migration_is_registered_before_version_update(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    steps = runner.list_steps()
    ids = [step["id"] for step in steps]
    registered = next(step for step in steps if step["id"] == "retired_mode_to_a")

    assert registered["category"] == "structural"
    assert ids.index("retired_mode_to_a") < ids.index("update_version")
