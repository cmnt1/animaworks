from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Skill context builders for background execution."""

from dataclasses import dataclass
from pathlib import Path

from core.skills.index import SkillIndex
from core.skills.loader import load_skill_body, load_skill_metadata, skill_access_decision
from core.skills.models import SkillMetadata


@dataclass(slots=True)
class SkillContextAttachment:
    name: str
    path: str
    body: str


@dataclass(slots=True)
class SkillContextRejection:
    ref: str
    reason: str


@dataclass(slots=True)
class SkillContextResult:
    attachments: list[SkillContextAttachment]
    rejections: list[SkillContextRejection]

    def render(self) -> str:
        if not self.attachments and not self.rejections:
            return ""
        sections: list[str] = []
        if self.attachments:
            sections.append("## Cron Skills")
            for item in self.attachments:
                sections.extend(
                    [
                        f"### {item.name}",
                        f"path: {item.path}",
                        "",
                        item.body.strip(),
                        "",
                    ]
                )
        if self.rejections:
            sections.append("## Rejected Cron Skills")
            sections.extend(f"- {item.ref}: {item.reason}" for item in self.rejections)
        return "\n".join(sections).strip()


def build_cron_skill_context(anima_dir: Path, skill_refs: list[str] | None) -> SkillContextResult:
    """Resolve cron ``skills:`` references and return loadable bodies plus rejects."""
    refs = _dedupe_refs(skill_refs or [])
    if not refs:
        return SkillContextResult([], [])

    from core.paths import get_common_skills_dir

    index = SkillIndex(
        anima_dir / "skills",
        get_common_skills_dir(),
        anima_dir / "procedures",
        anima_dir=anima_dir,
    )
    all_entries = index.search("", include_blocked=True)
    attachments: list[SkillContextAttachment] = []
    rejections: list[SkillContextRejection] = []

    for ref in refs:
        resolved = _resolve_skill_ref(anima_dir, ref, all_entries)
        if resolved is None:
            rejections.append(SkillContextRejection(ref, "not_found"))
            continue
        meta, path, pointer = resolved
        allowed, reason = skill_access_decision(meta, anima_dir=anima_dir)
        if not allowed:
            rejections.append(SkillContextRejection(ref, reason))
            continue
        try:
            body = load_skill_body(path)
        except Exception:
            rejections.append(SkillContextRejection(ref, "read_failed"))
            continue
        attachments.append(SkillContextAttachment(meta.name, pointer, body))

    return SkillContextResult(attachments, rejections)


def _resolve_skill_ref(
    anima_dir: Path,
    ref: str,
    entries: list[SkillMetadata],
) -> tuple[SkillMetadata, Path, str] | None:
    if not _is_safe_ref(ref):
        return None
    path = _path_from_pointer(anima_dir, ref)
    if path is not None and path.is_file():
        meta = load_skill_metadata(path)
        return meta, path, _pointer_for_path(anima_dir, path)

    for meta in entries:
        if meta.name == ref or (meta.path is not None and meta.path.parent.name == ref):
            if meta.path is None:
                return None
            return meta, meta.path, _pointer_for_path(anima_dir, meta.path)
    return None


def _path_from_pointer(anima_dir: Path, ref: str) -> Path | None:
    pointer = ref.strip()
    if not pointer:
        return None
    path = Path(pointer)
    if path.is_absolute():
        return None
    if pointer.startswith("skills/"):
        return _safe_child_path(anima_dir, path)
    if pointer.startswith("common_skills/"):
        from core.paths import get_data_dir

        return _safe_child_path(get_data_dir(), path)
    return None


def _pointer_for_path(anima_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(anima_dir))
    except ValueError:
        pass
    try:
        from core.paths import get_data_dir

        return str(path.relative_to(get_data_dir()))
    except ValueError:
        return str(path)


def _dedupe_refs(skill_refs: list[str]) -> list[str]:
    result: list[str] = []
    for ref in skill_refs:
        value = str(ref).strip()
        if value and value not in result:
            result.append(value)
    return result


def _is_safe_ref(ref: str) -> bool:
    value = ref.strip()
    if not value:
        return False
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return False
    if value.startswith(("skills/", "common_skills/")):
        return len(path.parts) >= 3 and path.name == "SKILL.md"
    return not ("/" in value or "\\" in value)


def _safe_child_path(root: Path, relative: Path) -> Path | None:
    if relative.name != "SKILL.md" or ".." in relative.parts:
        return None
    try:
        candidate = (root / relative).resolve(strict=False)
        root_resolved = root.resolve(strict=False)
        candidate.relative_to(root_resolved)
        return candidate
    except (OSError, ValueError):
        return None
