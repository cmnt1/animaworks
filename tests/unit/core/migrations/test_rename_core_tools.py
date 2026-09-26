"""Migration step that rewrites runtime ``core.tools`` references to ``core.integrations``."""

from __future__ import annotations

from pathlib import Path

from core.migrations.steps import step_rename_core_tools_to_integrations


def _seed(data_dir: Path) -> tuple[Path, Path, Path]:
    tool = data_dir / "common_tools" / "my_tool.py"
    tool.parent.mkdir(parents=True)
    tool.write_text("from core.tools._base import get_credential\nimport core.tools\n", encoding="utf-8")
    skill = data_dir / "animas" / "sakura" / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Put modules under core/tools and call core.tools.cli_dispatch.\n", encoding="utf-8")
    untouched = data_dir / "common_tools" / "other.py"
    untouched.write_text("from mypkg.core.tools_x import y\n", encoding="utf-8")
    return tool, skill, untouched


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    tool, skill, _ = _seed(tmp_path)
    result = step_rename_core_tools_to_integrations(tmp_path, dry_run=True, verbose=False)
    assert result.changed == 2
    assert "core.tools._base" in tool.read_text(encoding="utf-8")
    assert not (tmp_path / "backups").exists()


def test_rewrites_and_backs_up(tmp_path: Path) -> None:
    tool, skill, untouched = _seed(tmp_path)
    result = step_rename_core_tools_to_integrations(tmp_path, dry_run=False, verbose=False)
    assert result.error is None
    assert result.changed == 2
    assert tool.read_text(encoding="utf-8") == (
        "from core.integrations._base import get_credential\nimport core.integrations\n"
    )
    assert skill.read_text(encoding="utf-8") == (
        "Put modules under core/integrations and call core.integrations.cli_dispatch.\n"
    )
    assert untouched.read_text(encoding="utf-8") == "from mypkg.core.tools_x import y\n"
    backups = list((tmp_path / "backups").glob("*_tools_rename/common_tools/my_tool.py"))
    assert len(backups) == 1
    assert "core.tools._base" in backups[0].read_text(encoding="utf-8")

    again = step_rename_core_tools_to_integrations(tmp_path, dry_run=False, verbose=False)
    assert again.changed == 0
