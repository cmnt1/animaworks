from __future__ import annotations

from pathlib import Path

import pytest

from core.migrations.registry import MigrationRunner


@pytest.fixture(autouse=True)
def isolate_runtime_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / ".animaworks"))


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_resolve_template_sources_uses_file_level_locale_fallback(tmp_path: Path, monkeypatch) -> None:
    import core.migrations.template_sync as template_sync

    templates = tmp_path / "templates"
    ko_character = _write(templates / "ko/prompts/character_design_guide.md", "ko character")
    en_face = _write(templates / "en/prompts/face_types.md", "en faces")
    _write(templates / "ko/prompts/environment.md", "not copied")
    linked_file = _write(tmp_path / "outside.md", "symlink target")
    symlink = templates / "ko/common_knowledge/linked.md"
    symlink.parent.mkdir(parents=True, exist_ok=True)
    symlink.symlink_to(linked_file)
    monkeypatch.setattr(template_sync, "TEMPLATES_DIR", templates)

    sources = template_sync.resolve_template_sources("ko")

    assert sources["prompts/character_design_guide.md"] == ko_character
    assert sources["prompts/face_types.md"] == en_face
    assert "prompts/environment.md" not in sources
    assert "common_knowledge/linked.md" not in sources


def test_template_fingerprint_tracks_locale_and_relevant_content_only(tmp_path: Path, monkeypatch) -> None:
    import core.migrations.template_sync as template_sync

    templates = tmp_path / "templates"
    content = _write(templates / "ja/common_knowledge/guide.md", "same")
    _write(templates / "en/common_knowledge/guide.md", "same")
    hidden = _write(templates / "ja/common_knowledge/.hidden.md", "ignored")
    package_init = _write(templates / "ja/common_knowledge/__init__.py", "ignored")
    pycache = _write(templates / "ja/common_knowledge/__pycache__/cached.py", "ignored")
    bytecode = _write(templates / "ja/common_knowledge/cached.pyc", "ignored")
    monkeypatch.setattr(template_sync, "TEMPLATES_DIR", templates)

    ja_fingerprint = template_sync.template_fingerprint("ja")
    assert template_sync.template_fingerprint("ja") == ja_fingerprint
    assert template_sync.template_fingerprint("en") != ja_fingerprint

    hidden.write_text("changed ignored file", encoding="utf-8")
    package_init.write_text("changed ignored file", encoding="utf-8")
    pycache.write_text("changed ignored file", encoding="utf-8")
    bytecode.write_text("changed ignored file", encoding="utf-8")
    assert template_sync.template_fingerprint("ja") == ja_fingerprint

    content.write_text("samf", encoding="utf-8")
    assert template_sync.template_fingerprint("ja") != ja_fingerprint


def test_sync_runtime_templates_overwrites_skips_removes_and_supports_dry_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.migrations.template_sync as template_sync

    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / "runtime"))
    templates = tmp_path / "templates"
    _write(templates / "en/common_knowledge/x.md", "fresh")
    _write(templates / "en/common_skills/y.md", "same")
    _write(templates / "en/prompts/character_design_guide.md", "character")
    _write(templates / "en/prompts/face_types.md", "faces")
    _write(templates / "en/prompts/environment.md", "not a runtime prompt")
    monkeypatch.setattr(template_sync, "TEMPLATES_DIR", templates)

    data_dir = tmp_path / "runtime"
    _write(data_dir / "common_knowledge/x.md", "old")
    _write(data_dir / "common_skills/y.md", "same")
    stale = _write(data_dir / "prompts/task_delegation_rules.md", "retired")
    _write(data_dir / "prompts/environment.md", "keep existing unrelated prompt")

    dry = template_sync.sync_runtime_templates(data_dir, locale="en", dry_run=True)
    assert dry.error is None
    assert dry.changed == 4
    assert dry.skipped == 1
    assert (data_dir / "common_knowledge/x.md").read_text(encoding="utf-8") == "old"
    assert not (data_dir / "prompts/character_design_guide.md").exists()
    assert stale.exists()

    result = template_sync.sync_runtime_templates(data_dir, locale="en", dry_run=False)
    assert result.error is None
    assert result.changed == 4
    assert result.skipped == 1
    assert (data_dir / "common_knowledge/x.md").read_text(encoding="utf-8") == "fresh"
    assert (data_dir / "common_skills/y.md").read_text(encoding="utf-8") == "same"
    assert not stale.exists()
    assert (data_dir / "prompts/character_design_guide.md").read_text(encoding="utf-8") == "character"
    assert (data_dir / "prompts/face_types.md").read_text(encoding="utf-8") == "faces"
    assert (data_dir / "prompts/environment.md").read_text(encoding="utf-8") == "keep existing unrelated prompt"
    assert any("Copied 3 file(s)" in detail for detail in result.details)
    assert any("task_delegation_rules.md" in detail for detail in result.details)


def test_register_all_steps_has_one_fingerprinted_template_sync(tmp_path: Path, monkeypatch) -> None:
    import core.migrations.steps as migration_steps
    import core.migrations.template_sync as template_sync
    import core.paths

    _write(tmp_path / "templates/ko/common_knowledge/guide.md", "guide")
    monkeypatch.setattr(template_sync, "TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr(core.paths, "_get_locale", lambda: "ko")

    runner = MigrationRunner(tmp_path / "runtime")
    migration_steps.register_all_steps(runner)
    ids = [item["id"] for item in runner.list_steps()]
    sync_ids = [step_id for step_id in ids if step_id.startswith("template_sync_")]

    assert len(sync_ids) == 1
    template_step = next(step for step in runner._steps if step.id == sync_ids[0])
    assert template_step.category == "template_sync"
    assert "v056_resync" not in ids
    assert "v063_behavior_rules_action_rules_skill_sync" not in ids
    assert "v0145_prompt_diet4_resync" not in ids
    assert "v060_resync" in ids
    assert "v0140_harness_diet_resync" in ids
    assert ids.index("global_permissions_create") < ids.index(sync_ids[0])
    assert ids.index(sync_ids[0]) < ids.index("update_version")


def test_template_sync_uses_unknown_id_when_fingerprint_fails(tmp_path: Path, monkeypatch) -> None:
    import core.migrations.steps as migration_steps
    import core.migrations.template_sync as template_sync

    def fail_fingerprint(locale: str) -> str:
        raise OSError(f"cannot read templates for {locale}")

    monkeypatch.setattr(template_sync, "template_fingerprint", fail_fingerprint)
    runner = MigrationRunner(tmp_path / "runtime")
    runner.data_dir.mkdir()
    migration_steps.register_all_steps(runner)
    ids = [item["id"] for item in runner.list_steps()]

    assert ids.count("template_sync_unknown") == 1


def test_successful_noop_template_sync_is_recorded_as_applied(tmp_path: Path, monkeypatch) -> None:
    import core.migrations.steps as migration_steps
    import core.migrations.template_sync as template_sync
    import core.paths

    templates = tmp_path / "templates"
    _write(templates / "ja/common_knowledge/guide.md", "already synced")
    monkeypatch.setattr(template_sync, "TEMPLATES_DIR", templates)
    monkeypatch.setattr(core.paths, "_get_locale", lambda: "ja")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    _write(runtime / "common_knowledge/guide.md", "already synced")
    runner = MigrationRunner(runtime)
    migration_steps.register_all_steps(runner)
    template_step = next(step for step in runner._steps if step.id.startswith("template_sync_"))
    for step in runner._steps:
        if step.id != template_step.id:
            runner.tracker.mark_applied(step.id)

    first = runner.run_all()
    first_result = next(result for step, result in first.steps if step.id == template_step.id)
    assert first_result.changed == 1
    assert first_result.skipped == 1
    assert first_result.details[-1] == "No runtime template changes required; migration marked applied"

    second = runner.run_all()
    second_result = next(result for step, result in second.steps if step.id == template_step.id)
    assert second_result.details == ["already applied"]


def test_old_applied_resync_ids_do_not_block_new_template_sync(tmp_path: Path, monkeypatch) -> None:
    import core.migrations.steps as migration_steps
    import core.migrations.template_sync as template_sync
    import core.paths

    templates = tmp_path / "templates"
    _write(templates / "ja/common_knowledge/new.md", "bundled")
    monkeypatch.setattr(template_sync, "TEMPLATES_DIR", templates)
    monkeypatch.setattr(core.paths, "_get_locale", lambda: "ja")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    runner = MigrationRunner(runtime)
    migration_steps.register_all_steps(runner)
    template_step = next(step for step in runner._steps if step.id.startswith("template_sync_"))
    runner.tracker.mark_applied("prompt_resync")
    runner.tracker.mark_applied("v063_behavior_rules_action_rules_skill_sync")
    for step in runner._steps:
        if step.id != template_step.id:
            runner.tracker.mark_applied(step.id)

    first = runner.run_all()
    first_result = next(result for step, result in first.steps if step.id == template_step.id)
    assert first_result.changed == 1
    assert (runtime / "common_knowledge/new.md").read_text(encoding="utf-8") == "bundled"

    second = runner.run_all()
    second_result = next(result for step, result in second.steps if step.id == template_step.id)
    assert second_result.changed == 0
    assert second_result.skipped == 1
    assert second_result.details == ["already applied"]
