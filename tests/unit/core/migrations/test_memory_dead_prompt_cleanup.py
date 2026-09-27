from __future__ import annotations

from pathlib import Path

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_memory_dead_prompt_cleanup_20260927


def test_cleanup_removes_retired_classification_prompt(tmp_path: Path) -> None:
    stale_prompt = tmp_path / "prompts" / "memory" / "classification.md"
    stale_prompt.parent.mkdir(parents=True)
    stale_prompt.write_text("retired prompt", encoding="utf-8")

    result = step_memory_dead_prompt_cleanup_20260927(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 1
    assert result.skipped == 0
    assert result.error is None
    assert not stale_prompt.exists()


def test_cleanup_dry_run_preserves_prompt_and_missing_prompt_is_skipped(tmp_path: Path) -> None:
    stale_prompt = tmp_path / "prompts" / "memory" / "classification.md"
    stale_prompt.parent.mkdir(parents=True)
    stale_prompt.write_text("retired prompt", encoding="utf-8")

    dry_run_result = step_memory_dead_prompt_cleanup_20260927(tmp_path, dry_run=True, verbose=False)
    assert dry_run_result.changed == 1
    assert stale_prompt.read_text(encoding="utf-8") == "retired prompt"

    stale_prompt.unlink()
    missing_result = step_memory_dead_prompt_cleanup_20260927(tmp_path, dry_run=False, verbose=False)
    assert missing_result.changed == 0
    assert missing_result.skipped == 1


def test_cleanup_is_registered_before_version_update(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    ids = [step["id"] for step in runner.list_steps()]

    assert ids.index("memory_dead_prompt_cleanup_20260927") < ids.index("update_version")
