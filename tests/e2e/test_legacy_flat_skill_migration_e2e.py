from __future__ import annotations

from pathlib import Path

import pytest

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps
from core.skills.loader import load_skill_metadata
from core.skills.models import SkillTrustLevel


@pytest.mark.e2e
def test_registered_startup_migration_converts_legacy_flat_skill(tmp_path: Path) -> None:
    data_dir = tmp_path / "runtime"
    data_dir.mkdir()
    (data_dir / "config.json").write_text("{}", encoding="utf-8")
    anima_dir = data_dir / "animas" / "mei"
    (anima_dir / "skills").mkdir(parents=True)
    (anima_dir / "state").mkdir()
    (anima_dir / "identity.md").write_text("# mei\n", encoding="utf-8")
    (anima_dir / "skills" / "legacy.md").write_text(
        "---\ntrust_level: untrusted\n---\n\n# Legacy\n",
        encoding="utf-8",
    )

    runner = MigrationRunner(data_dir)
    register_all_steps(runner)
    report = runner.run_all()

    step_results = {step.id: result for step, result in report.steps}
    assert report.errors == []
    assert step_results["legacy_flat_skill_migration"].changed == 1
    assert runner.tracker.is_step_applied("legacy_flat_skill_migration")
    assert not (anima_dir / "skills" / "legacy.md").exists()
    destination = anima_dir / "skills" / "legacy" / "SKILL.md"
    assert destination.is_file()
    assert load_skill_metadata(destination).trust_level == SkillTrustLevel.trusted
