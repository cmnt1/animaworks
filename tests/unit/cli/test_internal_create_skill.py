from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from cli.commands.internal_cmd import _cmd_create_skill


def test_internal_create_skill_writes_current_bundle_layout(tmp_path: Path, capsys) -> None:
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()

    _cmd_create_skill(Namespace(name="deploy", content="# Deploy\n"), anima_dir)

    assert (anima_dir / "skills" / "deploy" / "SKILL.md").read_text(encoding="utf-8") == "# Deploy\n"
    assert not (anima_dir / "skills" / "deploy.md").exists()
    output = json.loads(capsys.readouterr().out)
    assert output == {"created": True, "path": "skills/deploy/SKILL.md"}


def test_internal_create_skill_accepts_legacy_md_suffix_as_name(tmp_path: Path, capsys) -> None:
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()

    _cmd_create_skill(Namespace(name="legacy.md", content="# Legacy\n"), anima_dir)

    assert (anima_dir / "skills" / "legacy" / "SKILL.md").is_file()
    output = json.loads(capsys.readouterr().out)
    assert output["path"] == "skills/legacy/SKILL.md"
