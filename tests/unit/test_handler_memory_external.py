"""Unit tests for external/ read support in core/tooling/handler_memory.py."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from core.tooling.handler_memory import MemoryToolsMixin


def _memory_mixin(anima_dir: Path) -> MagicMock:
    mixin = MagicMock(spec=MemoryToolsMixin)
    mixin._anima_dir = anima_dir
    mixin._superuser = True
    mixin._subordinate_activity_dirs = []
    mixin._subordinate_management_files = []
    mixin._descendant_activity_dirs = []
    mixin._descendant_state_files = []
    mixin._descendant_state_dirs = []
    mixin._read_paths = set()
    mixin._check_file_permission = lambda _path: None
    mixin._is_skill_path = MemoryToolsMixin._is_skill_path
    mixin._is_flat_personal_skill_path = MemoryToolsMixin._is_flat_personal_skill_path
    mixin._resolve_external = MemoryToolsMixin._resolve_external
    mixin._record_skill_view_if_applicable = lambda rel: MemoryToolsMixin._record_skill_view_if_applicable(
        mixin, rel
    )
    return mixin


class _FakeRoot:
    def __init__(self, path: str, engine: str, enabled: bool = True) -> None:
        self.path = path
        self.engine = engine
        self.enabled = enabled


class _FakeSkills:
    def __init__(self, roots) -> None:
        self.external_roots = roots


class _FakeConfig:
    def __init__(self, roots) -> None:
        self.skills = _FakeSkills(roots)


def _setup(tmp_path: Path, monkeypatch) -> tuple[Path, _FakeConfig]:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir(parents=True)
    root = tmp_path / "external-root"
    (root / "foo").mkdir(parents=True)
    (root / "foo" / "SKILL.md").write_text(
        "---\nname: foo\ndescription: Foo skill\n---\n\n# Foo Skill\n",
        encoding="utf-8",
    )
    (root / "foo" / "scripts").mkdir()
    (root / "foo" / "scripts" / "run.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    (root / ".system").mkdir()
    (root / ".system" / "secret.md").write_text("hidden", encoding="utf-8")

    config = _FakeConfig([_FakeRoot(str(root), "claude")])
    monkeypatch.setattr("core.config.models.load_config", lambda: config)
    return anima_dir, config


def test_read_external_skill_md(tmp_path: Path, monkeypatch) -> None:
    anima_dir, config = _setup(tmp_path, monkeypatch)
    mixin = _memory_mixin(anima_dir)

    out = MemoryToolsMixin._handle_read_memory_file(mixin, {"path": "external/claude/foo/SKILL.md"})

    assert "# Foo Skill" in out
    real_origin = str((tmp_path / "external-root" / "foo").resolve())
    assert f"> Real directory: {real_origin}" in out


def test_read_external_subfile(tmp_path: Path, monkeypatch) -> None:
    anima_dir, config = _setup(tmp_path, monkeypatch)
    mixin = _memory_mixin(anima_dir)

    out = MemoryToolsMixin._handle_read_memory_file(mixin, {"path": "external/claude/foo/scripts/run.sh"})

    assert "echo hi" in out


def test_read_external_traversal_rejected(tmp_path: Path, monkeypatch) -> None:
    anima_dir, config = _setup(tmp_path, monkeypatch)
    mixin = _memory_mixin(anima_dir)

    out = MemoryToolsMixin._handle_read_memory_file(mixin, {"path": "external/claude/foo/../../etc/passwd"})

    assert "PermissionDenied" in out


def test_read_external_unknown_engine_not_found(tmp_path: Path, monkeypatch) -> None:
    anima_dir, config = _setup(tmp_path, monkeypatch)
    mixin = _memory_mixin(anima_dir)

    out = MemoryToolsMixin._handle_read_memory_file(mixin, {"path": "external/codex/foo/SKILL.md"})

    assert "File not found" in out


def test_read_external_dot_entry_not_found(tmp_path: Path, monkeypatch) -> None:
    anima_dir, config = _setup(tmp_path, monkeypatch)
    mixin = _memory_mixin(anima_dir)

    out = MemoryToolsMixin._handle_read_memory_file(mixin, {"path": "external/claude/.system/secret.md"})

    assert "File not found" in out


def test_write_external_rejected(tmp_path: Path, monkeypatch) -> None:
    anima_dir, config = _setup(tmp_path, monkeypatch)
    mixin = _memory_mixin(anima_dir)

    out = MemoryToolsMixin._handle_write_memory_file(
        mixin, {"path": "external/claude/foo/SKILL.md", "content": "new"}
    )

    assert "external/" in out
    assert "read-only" in out
    assert "PermissionDenied" in out
