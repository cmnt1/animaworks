from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_template_sync_migration_updates_shared_files_and_direct_read_prompts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Run the consolidated sync against stale shared and Anima-read files."""
    from core.migrations.steps import step_template_sync

    data_dir = tmp_path / ".animaworks"
    data_dir.mkdir()
    (data_dir / "config.json").write_text('{"locale": "ja"}', encoding="utf-8")
    (data_dir / "animas").mkdir()
    prompts_dir = data_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "character_design_guide.md").write_text("stale character guide", encoding="utf-8")
    (prompts_dir / "behavior_rules.md").write_text("leave unrelated runtime prompt", encoding="utf-8")
    action_guide = data_dir / "common_knowledge" / "operations" / "action-rules-guide.md"
    action_guide.parent.mkdir(parents=True)
    action_guide.write_text("stale action guide", encoding="utf-8")
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))

    result = step_template_sync(data_dir, dry_run=False, verbose=True)

    assert result.error is None
    template_root = Path(__file__).resolve().parents[3] / "templates" / "ja"
    character_guide = (prompts_dir / "character_design_guide.md").read_text(encoding="utf-8")
    assert character_guide == (template_root / "prompts" / "character_design_guide.md").read_text(encoding="utf-8")
    assert (prompts_dir / "face_types.md").read_text(encoding="utf-8") == (
        template_root / "prompts" / "face_types.md"
    ).read_text(encoding="utf-8")
    assert (prompts_dir / "behavior_rules.md").read_text(encoding="utf-8") == "leave unrelated runtime prompt"
    assert "gmail_draft" in action_guide.read_text(encoding="utf-8")
    assert "trust_level" in (data_dir / "common_skills" / "skill-creator" / "SKILL.md").read_text(encoding="utf-8")


def test_cli_migrate_fresh_process_syncs_direct_read_prompt_files(tmp_path: Path) -> None:
    """CLI migration succeeds from a fresh process and refreshes runtime read prompts."""
    data_dir = tmp_path / ".animaworks"
    data_dir.mkdir()
    (data_dir / "config.json").write_text('{"locale": "ja"}', encoding="utf-8")
    (data_dir / "animas").mkdir()
    prompts_dir = data_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "character_design_guide.md").write_text("stale character guide", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["ANIMAWORKS_DATA_DIR"] = str(data_dir)
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [sys.executable, "-m", "cli", "migrate"],
        cwd=repo_root,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=60,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ERROR:" not in output
    assert "cannot import name" not in output

    character_guide = (data_dir / "prompts" / "character_design_guide.md").read_text(encoding="utf-8")
    template = repo_root / "templates" / "ja" / "prompts" / "character_design_guide.md"
    assert character_guide == template.read_text(encoding="utf-8")
    assert "stale character guide" not in character_guide
    assert (data_dir / "prompts" / "face_types.md").is_file()
