from __future__ import annotations

import json
from pathlib import Path

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_remove_process_model_fields


def _create_anima(data_dir: Path, status_text: str | None = None) -> Path:
    anima_dir = data_dir / "animas" / "sakura"
    anima_dir.mkdir(parents=True)
    (anima_dir / "identity.md").write_text("# Sakura\n", encoding="utf-8")
    if status_text is not None:
        (anima_dir / "status.json").write_text(status_text, encoding="utf-8")
    return anima_dir


def test_remove_process_model_fields_preserves_other_status_fields(tmp_path: Path) -> None:
    anima_dir = _create_anima(
        tmp_path,
        json.dumps(
            {
                "process_model": "legacy",
                "task_process_isolation": {"task": False},
                "model": "claude-sonnet-4-6",
                "enabled": True,
            }
        ),
    )

    result = step_remove_process_model_fields(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 1
    assert result.error is None
    assert json.loads((anima_dir / "status.json").read_text(encoding="utf-8")) == {
        "model": "claude-sonnet-4-6",
        "enabled": True,
    }
    assert any("process_model=legacy removed (now phase3)" in detail for detail in result.details)


def test_remove_process_model_fields_leaves_status_without_retired_keys_untouched(tmp_path: Path) -> None:
    anima_dir = _create_anima(tmp_path, '{"model": "claude", "enabled": true}\n')
    status_path = anima_dir / "status.json"
    original = status_path.read_text(encoding="utf-8")
    original_mtime = status_path.stat().st_mtime_ns

    result = step_remove_process_model_fields(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 0
    assert status_path.read_text(encoding="utf-8") == original
    assert status_path.stat().st_mtime_ns == original_mtime


def test_remove_process_model_fields_dry_run_does_not_write(tmp_path: Path) -> None:
    anima_dir = _create_anima(tmp_path, '{"process_model": "phase2", "model": "claude"}\n')
    status_path = anima_dir / "status.json"
    original = status_path.read_text(encoding="utf-8")

    result = step_remove_process_model_fields(tmp_path, dry_run=True, verbose=False)

    assert result.changed == 1
    assert status_path.read_text(encoding="utf-8") == original
    assert any("would" in detail.lower() for detail in result.details)
    assert any("process_model=phase2 removed (now phase3)" in detail for detail in result.details)


def test_remove_process_model_fields_removes_unexpected_process_model_values(tmp_path: Path) -> None:
    anima_dir = _create_anima(tmp_path, '{"process_model": {"unexpected": true}, "enabled": true}\n')

    result = step_remove_process_model_fields(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 1
    assert result.error is None
    assert json.loads((anima_dir / "status.json").read_text(encoding="utf-8")) == {"enabled": True}


def test_remove_process_model_fields_skips_corrupt_json(tmp_path: Path) -> None:
    _create_anima(tmp_path, "{broken json")

    result = step_remove_process_model_fields(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 0
    assert result.error is None
    assert result.skipped == 1
    assert any("skipped invalid status.json" in detail for detail in result.details)


def test_remove_process_model_fields_is_idempotent(tmp_path: Path) -> None:
    anima_dir = _create_anima(tmp_path, '{"process_model": "phase3", "model": "claude"}\n')

    first = step_remove_process_model_fields(tmp_path, dry_run=False, verbose=False)
    second = step_remove_process_model_fields(tmp_path, dry_run=False, verbose=False)

    assert first.changed == 1
    assert second.changed == 0
    assert json.loads((anima_dir / "status.json").read_text(encoding="utf-8")) == {"model": "claude"}


def test_remove_process_model_fields_is_registered_before_update_version(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    ids = [step["id"] for step in runner.list_steps()]

    assert ids.index("remove_process_model_fields") < ids.index("update_version")
