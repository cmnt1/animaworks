# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for external engine skill roots in SkillIndex."""

from __future__ import annotations

import json
from pathlib import Path

from core.config.schemas import ExternalSkillRoot
from core.skills.index import SkillIndex


def _write_skill(base: Path, name: str, *, desc: str = "a skill", body: str = "") -> Path:
    """Write a minimal SKILL.md under *base* and return the SKILL.md path."""
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    content = (
        f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\n{body or 'Body.'}\n"
    )
    skill_md = d / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8")
    return skill_md


def _ext_root(tmp_path: Path, rel: str, *, engine: str, enabled: bool = True) -> ExternalSkillRoot:
    d = tmp_path / rel
    d.mkdir(parents=True, exist_ok=True)
    return ExternalSkillRoot(path=str(d), engine=engine, enabled=enabled)


def _index(*, skills: Path, common: Path, procs: Path | None = None, anima_dir: Path | None = None, roots: list):
    return SkillIndex(
        skills,
        common,
        procs,
        anima_dir=anima_dir,
        external_roots=roots,
    )


def _names(entries) -> list[str]:
    return [e.name for e in entries]


def test_external_root_skills_adopted(tmp_path: Path):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    skills.mkdir()
    common.mkdir()
    root = _ext_root(tmp_path, "ext", engine="claude")
    _write_skill(tmp_path / "ext", "web-search", desc="search")

    idx = _index(skills=skills, common=common, roots=[root])
    results = idx.build_index()
    ext = [m for m in results if m.is_external]
    assert len(ext) == 1
    asset = ext[0]
    assert asset.name == "web-search"
    assert asset.is_external is True
    assert asset.is_common is False
    assert asset.is_procedure is False
    assert asset.source.engine == "claude"
    assert asset.trust_level.value == "trusted"
    assert asset.source.type == "external"
    assert asset.source.origin == str((tmp_path / "ext" / "web-search").resolve())
    assert str(asset.path) == str((tmp_path / "ext" / "web-search" / "SKILL.md").resolve())


def test_dotdir_excluded(tmp_path: Path):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    skills.mkdir()
    common.mkdir()
    root = _ext_root(tmp_path, "ext", engine="claude")
    _write_skill(tmp_path / "ext", "real-skill")
    _write_skill(tmp_path / "ext", ".system")

    idx = _index(skills=skills, common=common, roots=[root])
    results = idx.build_index()
    names = _names(results)
    assert "real-skill" in names
    assert ".system" not in names
    assert not [m for m in results if m.is_external and m.name == ".system"]


def test_symlink_dir_resolved(tmp_path: Path):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    skills.mkdir()
    common.mkdir()
    real_dir = tmp_path / "real_assets" / "skill-a"
    real_dir.mkdir(parents=True)
    (real_dir / "SKILL.md").write_text(
        "---\nname: skill-a\ndescription: symlinked skill\n---\n\n# skill-a\n",
        encoding="utf-8",
    )
    root = _ext_root(tmp_path, "ext", engine="codex")
    (tmp_path / "ext" / "skill-a").symlink_to(real_dir, target_is_directory=True)

    idx = _index(skills=skills, common=common, roots=[root])
    results = idx.build_index()
    ext = [m for m in results if m.is_external]
    assert len(ext) == 1
    assert ext[0].source.origin == str(real_dir.resolve())


def test_same_name_native_wins(tmp_path: Path):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    skills.mkdir()
    common.mkdir()
    native = _write_skill(skills, "web-search", desc="native")
    root = _ext_root(tmp_path, "ext", engine="claude")
    _write_skill(tmp_path / "ext", "web-search", desc="external")

    idx = _index(skills=skills, common=common, roots=[root])
    results = idx.build_index()
    ext = [m for m in results if m.is_external]
    assert ext == []
    assert any(m.name == "web-search" and not m.is_external and str(m.path) == str(native.resolve()) for m in results)
    reasons = [s.reason for s in idx.shadowed]
    assert "shadowed_by_native" in reasons


def test_same_hash_dedup_to_one(tmp_path: Path):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    skills.mkdir()
    common.mkdir()
    root_a = _ext_root(tmp_path, "ext_a", engine="claude")
    root_b = _ext_root(tmp_path, "ext_b", engine="codex")
    _write_skill(tmp_path / "ext_a", "common-skill", desc="same")
    _write_skill(tmp_path / "ext_b", "common-skill", desc="same")

    idx = _index(skills=skills, common=common, roots=[root_a, root_b])
    results = idx.build_index()
    ext = [m for m in results if m.is_external and m.name == "common-skill"]
    assert len(ext) == 1
    assert ext[0].source.engine == "claude"  # first root wins
    assert any(s.reason == "duplicate_identical" for s in idx.shadowed)


def test_diff_hash_priority_wins(tmp_path: Path):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    skills.mkdir()
    common.mkdir()
    root_a = _ext_root(tmp_path, "ext_a", engine="claude")
    root_b = _ext_root(tmp_path, "ext_b", engine="codex")
    _write_skill(tmp_path / "ext_a", "common-skill", desc="A", body="alpha")
    _write_skill(tmp_path / "ext_b", "common-skill", desc="B", body="beta")

    idx = _index(skills=skills, common=common, roots=[root_a, root_b])
    results = idx.build_index()
    ext = [m for m in results if m.is_external and m.name == "common-skill"]
    assert len(ext) == 1
    assert ext[0].source.engine == "claude"
    assert any(s.reason == "shadowed_by_priority" for s in idx.shadowed)


def test_name_underscore_normalized(tmp_path: Path):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    skills.mkdir()
    common.mkdir()
    _write_skill(skills, "skill_creator", desc="native")
    root = _ext_root(tmp_path, "ext", engine="claude")
    _write_skill(tmp_path / "ext", "skill-creator", desc="external")

    idx = _index(skills=skills, common=common, roots=[root])
    results = idx.build_index()
    ext = [m for m in results if m.is_external]
    assert ext == []
    assert any(s.reason == "shadowed_by_native" for s in idx.shadowed)


def test_invalid_frontmatter_skipped(tmp_path: Path, caplog):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    skills.mkdir()
    common.mkdir()
    root = _ext_root(tmp_path, "ext", engine="claude")
    d = tmp_path / "ext" / "broken"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: broken\ntrust_level: no-such-level\n---\n# broken\n",
        encoding="utf-8",
    )

    idx = _index(skills=skills, common=common, roots=[root])
    results = idx.build_index()
    assert not any(m.is_external and m.name == "broken" for m in results)


def test_denied_origin_excluded(tmp_path: Path):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    anima = tmp_path / "anima"
    skills.mkdir()
    common.mkdir()
    anima.mkdir()
    root = _ext_root(tmp_path, "ext", engine="claude")
    _write_skill(tmp_path / "ext", "blocked-skill", desc="blocked")
    (anima / "permissions.json").write_text(
        json.dumps({"version": 1, "file_roots_denied": [str(tmp_path.resolve())]}),
        encoding="utf-8",
    )

    idx = _index(skills=skills, common=common, anima_dir=anima, roots=[root])
    results = idx.build_index()
    assert not any(m.is_external for m in results)
    assert "denied" in idx.excluded.values()


def test_sort_key_order(tmp_path: Path):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    procs = tmp_path / "procedures"
    skills.mkdir()
    common.mkdir()
    procs.mkdir()
    _write_skill(skills, "personal-z")
    _write_skill(common, "common-skill")
    _write_skill(tmp_path / "ext", "external-skill")
    (procs / "proc.md").write_text(
        "---\ndescription: a procedure\n---\n\n# Steps\n",
        encoding="utf-8",
    )
    root = _ext_root(tmp_path, "ext", engine="claude")

    idx = _index(skills=skills, common=common, procs=procs, roots=[root])
    results = idx.build_index()
    tiers = []
    for m in results:
        if m.is_procedure:
            tiers.append(3)
        elif m.is_common:
            tiers.append(1)
        elif m.is_external:
            tiers.append(2)
        else:
            tiers.append(0)
    assert tiers == sorted(tiers)


def test_missing_root_ignored(tmp_path: Path):
    skills = tmp_path / "skills"
    common = tmp_path / "common"
    skills.mkdir()
    common.mkdir()
    missing = tmp_path / "does_not_exist"
    root = ExternalSkillRoot(path=str(missing), engine="claude")

    idx = _index(skills=skills, common=common, roots=[root])
    results = idx.build_index()  # must not raise
    assert not any(m.is_external for m in results)


def test_external_pointer_roundtrip(tmp_path, monkeypatch):
    """external/<engine>/<name>/SKILL.md refs resolve via SkillIndex and list_skill_catalog."""
    from core.config.schemas import ExternalSkillRoot
    from core.skills import activation
    from core.skills.index import SkillIndex

    root = tmp_path / "claude_skills"
    (root / "foo").mkdir(parents=True)
    (root / "foo" / "SKILL.md").write_text("---\nname: foo\ndescription: d\n---\nbody\n", encoding="utf-8")
    anima = tmp_path / "anima"
    (anima / "skills").mkdir(parents=True)
    (anima / "state").mkdir()
    roots = [ExternalSkillRoot(path=str(root), engine="claude")]
    idx = SkillIndex(anima / "skills", tmp_path / "common_skills", anima_dir=anima, external_roots=roots)
    meta = idx.resolve_skill_reference("external/claude/foo/SKILL.md")
    assert meta is not None and meta.is_external and meta.name == "foo"
    assert idx.resolve_skill_reference("external/claude/../foo/SKILL.md") is None
    assert idx.resolve_skill_reference("external/claude/.hidden/SKILL.md") is None

    monkeypatch.setattr(activation, "_build_index", lambda ad, cs: idx)
    monkeypatch.setattr(activation, "_get_common_skills_dir", lambda: tmp_path / "common_skills")
    items = activation.list_skill_catalog(anima, thread_id="default")
    ext = [i for i in items if i["name"] == "foo"]
    assert ext and ext[0]["ref"] == "external/claude/foo/SKILL.md" and ext[0]["path"] == "external/claude/foo/SKILL.md"
