from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Migration helpers for legacy flat skill files."""

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from core.migrations.registry import StepResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _LegacyFlatSkillCandidate:
    source: Path
    destination: Path
    old_pointer: str
    new_pointer: str
    owner_anima: str | None
    reference_scope: Path | None


def migrate_legacy_flat_skills(data_dir: Path, *, dry_run: bool, verbose: bool) -> StepResult:
    """Convert legacy flat local skill files to trusted SKILL.md bundles."""
    del verbose
    details: list[str] = []
    changed = 0
    try:
        candidates = _legacy_flat_skill_candidates(data_dir)
        if not candidates:
            return StepResult(changed=0, skipped=1, details=["No legacy flat skills found"])

        if dry_run:
            details.extend(
                f"Would migrate {candidate.source.relative_to(data_dir)} -> {candidate.destination.relative_to(data_dir)}"
                for candidate in candidates
            )
            return StepResult(changed=len(candidates), skipped=0, details=details)

        backup_root = (
            data_dir
            / "shared"
            / "migration_backups"
            / "legacy_flat_skills"
            / datetime.now().strftime("%Y%m%dT%H%M%S%f")
        )
        personal_maps: dict[Path, dict[str, str]] = {}
        common_map: dict[str, str] = {}

        for candidate in candidates:
            _migrate_legacy_flat_skill(candidate, data_dir, backup_root)
            changed += 1
            details.append(
                f"Migrated {candidate.source.relative_to(data_dir)} -> {candidate.destination.relative_to(data_dir)}"
            )
            if candidate.reference_scope is None:
                common_map[candidate.old_pointer] = candidate.new_pointer
            else:
                personal_maps.setdefault(candidate.reference_scope, {})[candidate.old_pointer] = candidate.new_pointer

        from core.skills.reference_rewriter import apply_skill_pointer_rewrites

        anima_dirs = set(_iter_runtime_anima_dirs(data_dir)) | set(personal_maps)
        for anima_dir in sorted(anima_dirs):
            pointer_map = {**common_map, **personal_maps.get(anima_dir, {})}
            if not pointer_map:
                continue
            for change in apply_skill_pointer_rewrites(anima_dir, pointer_map):
                changed += 1
                details.append(f"Rewrote {anima_dir.name}/{change.path}")

        return StepResult(changed=changed, skipped=0, details=details)
    except Exception as exc:
        logger.exception("migrate_legacy_flat_skills failed")
        return StepResult(changed=changed, skipped=0, details=details, error=str(exc))


def _iter_runtime_anima_dirs(data_dir: Path) -> list[Path]:
    animas_dir = data_dir / "animas"
    if not animas_dir.exists():
        return []
    return [d for d in sorted(animas_dir.iterdir()) if d.is_dir()]


def _legacy_flat_skill_candidates(data_dir: Path) -> list[_LegacyFlatSkillCandidate]:
    candidates: list[_LegacyFlatSkillCandidate] = []
    for anima_dir in _iter_runtime_anima_dirs(data_dir):
        skills_dir = anima_dir / "skills"
        if not skills_dir.is_dir():
            continue
        for source in sorted(skills_dir.glob("*.md")):
            if not _is_legacy_flat_skill_file(source):
                continue
            skill_name = source.stem
            candidates.append(
                _LegacyFlatSkillCandidate(
                    source=source,
                    destination=skills_dir / skill_name / "SKILL.md",
                    old_pointer=f"skills/{source.name}",
                    new_pointer=f"skills/{skill_name}/SKILL.md",
                    owner_anima=anima_dir.name,
                    reference_scope=anima_dir,
                )
            )

    common_skills_dir = data_dir / "common_skills"
    if common_skills_dir.is_dir():
        for source in sorted(common_skills_dir.glob("*.md")):
            if not _is_legacy_flat_skill_file(source):
                continue
            skill_name = source.stem
            candidates.append(
                _LegacyFlatSkillCandidate(
                    source=source,
                    destination=common_skills_dir / skill_name / "SKILL.md",
                    old_pointer=f"common_skills/{source.name}",
                    new_pointer=f"common_skills/{skill_name}/SKILL.md",
                    owner_anima=None,
                    reference_scope=None,
                )
            )
    return candidates


def _is_legacy_flat_skill_file(path: Path) -> bool:
    return path.is_file() and path.suffix == ".md" and path.name != "SKILL.md" and not path.name.startswith(".")


def _migrate_legacy_flat_skill(candidate: _LegacyFlatSkillCandidate, data_dir: Path, backup_root: Path) -> None:
    if not candidate.destination.is_file():
        _write_trusted_skill_bundle(candidate)
    _backup_and_remove_legacy_flat_skill(candidate.source, data_dir, backup_root)


def _write_trusted_skill_bundle(candidate: _LegacyFlatSkillCandidate) -> None:
    from core.memory.frontmatter import parse_frontmatter
    from core.skills.loader import load_skill_metadata

    text = candidate.source.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(text)
    try:
        inferred = load_skill_metadata(candidate.source)
    except Exception:
        inferred = None

    skill_name = candidate.source.stem
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        description = getattr(inferred, "description", "") if inferred is not None else ""

    normalized = dict(frontmatter)
    normalized["name"] = skill_name
    normalized["description"] = str(description or "")
    normalized["trust_level"] = "trusted"
    normalized["promotion_status"] = "trusted"
    normalized["skill_policy"] = {
        "use_mode": "primary_guidance",
        "injection": "body_allowed",
    }
    source = {
        "type": "local",
        "identifier": candidate.old_pointer,
        "origin": "legacy_flat_skill_migration",
    }
    if candidate.owner_anima:
        source["owner_anima"] = candidate.owner_anima
    normalized["source"] = source
    normalized["version"] = _coerce_legacy_skill_version(frontmatter.get("version"))
    normalized["security"] = {
        "verdict": "safe",
        "scan_status": "legacy_trusted",
        "findings": [],
    }

    rendered = yaml.dump(normalized, allow_unicode=True, default_flow_style=False, sort_keys=False).strip()
    candidate.destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = candidate.destination.with_suffix(candidate.destination.suffix + ".tmp")
    tmp.write_text(f"---\n{rendered}\n---\n\n{body.lstrip()}", encoding="utf-8")
    tmp.replace(candidate.destination)


def _coerce_legacy_skill_version(value: Any) -> int:
    try:
        version = int(value)
    except (TypeError, ValueError):
        return 1
    return version if version > 0 else 1


def _backup_and_remove_legacy_flat_skill(source: Path, data_dir: Path, backup_root: Path) -> None:
    backup_path = backup_root / source.relative_to(data_dir)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, backup_path)
    source.unlink()
