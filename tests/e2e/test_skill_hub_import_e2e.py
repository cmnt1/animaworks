from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for Skill Hub local import flow."""

from pathlib import Path

from core.skills.hub import SkillHub
from core.skills.index import SkillIndex
from core.skills.loader import load_skill_metadata


def test_local_skill_import_remove_and_quarantine_promote(tmp_path: Path) -> None:
    source = tmp_path / "source" / "release-helper"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\n"
        "name: Release Helper\n"
        "description: Import release helper safely\n"
        "use_when: [release import]\n"
        "trigger_phrases: [release import]\n"
        "domains: [software-delivery]\n"
        "---\n\n"
        "# Release Helper\n\nFollow a safe release checklist.\n",
        encoding="utf-8",
    )

    hub = SkillHub(data_dir=tmp_path)
    dry_run = hub.install(str(source), target="personal", anima="mei", dry_run=True)
    assert dry_run.status == "dry_run"
    assert not (tmp_path / "animas" / "mei" / "skills" / "release-helper").exists()

    installed = hub.install(str(source), target="personal", anima="mei")
    assert installed.status == "installed"
    installed_path = tmp_path / "animas" / "mei" / installed.installed_path
    assert installed_path.is_file()
    assert load_skill_metadata(installed_path).trust_level.value == "community"
    assert "release-helper" in {
        meta.name
        for meta in SkillIndex(
            tmp_path / "animas" / "mei" / "skills",
            tmp_path / "common_skills",
            anima_dir=tmp_path / "animas" / "mei",
        ).all_skills
    }

    hub.remove("release-helper", target="personal", anima="mei")
    quarantined = hub.install(str(source), target="personal", anima="mei", quarantine=True)
    assert quarantined.status == "quarantine"
    assert hub.list_skills(target="personal", anima="mei", quarantine=True)[0]["name"] == "release-helper"

    promoted = hub.promote_quarantine(
        "release-helper",
        target="personal",
        anima="mei",
        approval_id="approved-123",
    )
    assert promoted.status == "promoted"
    assert (tmp_path / "animas" / "mei" / promoted.installed_path).is_file()
