from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

from cli.parser import build_parser
from core.skills.ledger import SkillLedger


def _invoke(parser, argv: list[str]) -> None:
    args = parser.parse_args(argv)
    args.func(args)


def test_skills_ledger_cli_lists_and_rolls_back_personal_change(tmp_path: Path, monkeypatch, capsys) -> None:
    import cli.commands.skills as skills_cli

    data_dir = tmp_path
    anima_dir = data_dir / "animas" / "alice"
    skill_path = anima_dir / "skills" / "deploy" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    before = "# Deploy\nOriginal\n"
    after = "# Deploy\nUpdated\n"
    skill_path.write_text(after, encoding="utf-8")
    entry = SkillLedger(anima_dir, data_dir=data_dir).record_change(
        skill_path,
        before_text=before,
        after_text=after,
        before_exists=True,
        after_exists=True,
        actor="alice",
        route="write_memory_file",
    )
    monkeypatch.setattr(skills_cli, "get_data_dir", lambda: data_dir)
    parser = build_parser()

    _invoke(parser, ["skills", "ledger", "deploy", "--anima", "alice"])
    listed = json.loads(capsys.readouterr().out)
    assert listed["count"] == 1
    assert listed["entries"][0]["id"] == entry["id"]

    _invoke(parser, ["skills", "rollback", entry["id"], "--anima", "alice"])
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "rolled_back"
    assert skill_path.read_text(encoding="utf-8") == before


def test_skills_rollback_cli_can_restore_common_skill(tmp_path: Path, monkeypatch, capsys) -> None:
    import cli.commands.skills as skills_cli

    data_dir = tmp_path
    common_path = data_dir / "common_skills" / "shared" / "SKILL.md"
    common_path.parent.mkdir(parents=True)
    before = "# Shared\nBefore\n"
    after = "# Shared\nAfter\n"
    common_path.write_text(after, encoding="utf-8")
    entry = SkillLedger(data_dir=data_dir).record_change(
        common_path,
        before_text=before,
        after_text=after,
        before_exists=True,
        after_exists=True,
        actor="alice",
        route="write_memory_file",
    )
    monkeypatch.setattr(skills_cli, "get_data_dir", lambda: data_dir)

    _invoke(build_parser(), ["skills", "rollback", entry["id"], "--anima", "alice"])
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "rolled_back"
    assert common_path.read_text(encoding="utf-8") == before
