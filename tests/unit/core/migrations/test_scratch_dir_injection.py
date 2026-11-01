"""Migration step that points dev-engineer injections at ANIMAWORKS_SCRATCH_DIR."""

from __future__ import annotations

from pathlib import Path

from core.migrations.steps import _SCRATCH_INJECTION_OLD_LINES, step_scratch_dir_injection_20261020


def _write(data_dir: Path, name: str, text: str) -> Path:
    path = data_dir / "animas" / name / "injection.md"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_rewrites_template_lines_in_every_locale_and_backs_up(tmp_path: Path) -> None:
    paths = {
        locale: _write(tmp_path, f"a-{locale}", f"# Guide\n\n{old}\n- other\n")
        for locale, old in _SCRATCH_INJECTION_OLD_LINES.items()
    }

    result = step_scratch_dir_injection_20261020(tmp_path, dry_run=False, verbose=False)

    assert result.error is None
    assert result.changed == 3
    for locale, path in paths.items():
        text = path.read_text(encoding="utf-8")
        assert "ANIMAWORKS_SCRATCH_DIR" in text
        assert _SCRATCH_INJECTION_OLD_LINES[locale] not in text.splitlines()
        assert text.endswith("- other\n")
    backups = list((tmp_path / "backups").rglob("injection.md"))
    assert len(backups) == 3


def test_dry_run_and_customized_injections_are_untouched(tmp_path: Path) -> None:
    old = _SCRATCH_INJECTION_OLD_LINES["ja"]
    target = _write(tmp_path, "sakura", f"{old}\n")
    custom = _write(tmp_path, "rin", f"{old}（自分用の追記）\n")
    done = _write(tmp_path, "sora", f"{old}\n- worktree は $ANIMAWORKS_SCRATCH_DIR に作る\n")

    dry = step_scratch_dir_injection_20261020(tmp_path, dry_run=True, verbose=False)
    assert dry.changed == 1
    assert target.read_text(encoding="utf-8") == f"{old}\n"
    assert not (tmp_path / "backups").exists()

    step_scratch_dir_injection_20261020(tmp_path, dry_run=False, verbose=False)
    assert custom.read_text(encoding="utf-8") == f"{old}（自分用の追記）\n"
    assert done.read_text(encoding="utf-8").startswith(old)

    again = step_scratch_dir_injection_20261020(tmp_path, dry_run=False, verbose=False)
    assert again.changed == 0
