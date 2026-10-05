from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Append-only audit ledger and guarded rollback for skill document changes."""

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.memory.frontmatter import parse_frontmatter
from core.paths import get_common_skills_dir, get_data_dir
from core.platform.atomic_io import atomic_write_text

logger = logging.getLogger("animaworks.skill_ledger")

_HUMAN_ORIGINS = frozenset({"human", "user", "manual", "human-authored", "human_written", "human-written"})


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "pinned"}
    return bool(value)


def skill_is_human_or_pinned(metadata: dict[str, Any]) -> bool:
    """Return whether frontmatter marks a skill as human-authored or pinned."""
    if _truthy(metadata.get("pinned")):
        return True

    author = str(metadata.get("author") or "").strip().casefold()
    if author in _HUMAN_ORIGINS:
        return True

    origins = [metadata.get("origin")]
    source = metadata.get("source")
    if isinstance(source, dict):
        origins.append(source.get("origin"))
        origins.append(source.get("type"))
    return any(str(origin or "").strip().casefold() in _HUMAN_ORIGINS for origin in origins)


def automatic_skill_edit_allowed(path: Path) -> bool:
    """Reject automatic writes to existing human-authored or pinned skills."""
    if not path.is_file():
        return True
    try:
        metadata, _body = parse_frontmatter(path.read_text(encoding="utf-8"))
    except OSError:
        logger.warning("Unable to inspect skill before automatic edit: %s", path, exc_info=True)
        return False
    if skill_is_human_or_pinned(metadata):
        logger.info("Automatic skill edit skipped: human-authored or pinned skill path=%s", path)
        return False
    return True


def is_skill_document_path(
    path: Path,
    anima_dir: Path,
    *,
    common_skills_dir: Path | None = None,
) -> bool:
    """Return whether *path* is an actual skill body (not a skill attachment)."""
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(anima_dir.resolve())
    except ValueError:
        relative = None
    if relative is not None:
        parts = relative.parts
        if len(parts) == 2 and parts[0] == "skills" and Path(parts[1]).suffix.lower() == ".md":
            return True
        if len(parts) >= 3 and parts[0] == "skills" and parts[-1] == "SKILL.md":
            return True

    shared_root = (common_skills_dir or get_common_skills_dir()).resolve()
    try:
        shared_relative = resolved.relative_to(shared_root)
    except ValueError:
        return False
    parts = shared_relative.parts
    if len(parts) == 1 and Path(parts[0]).suffix.lower() == ".md":
        return True
    return len(parts) >= 2 and parts[-1] == "SKILL.md"


def skill_memory_pointer(
    path: Path,
    anima_dir: Path,
    *,
    common_skills_dir: Path | None = None,
) -> str | None:
    """Return the canonical read-before-write key for a skill document."""
    if not is_skill_document_path(path, anima_dir, common_skills_dir=common_skills_dir):
        return None
    resolved = path.resolve()
    try:
        return resolved.relative_to(anima_dir.resolve()).as_posix()
    except ValueError:
        shared_root = (common_skills_dir or get_common_skills_dir()).resolve()
        return (Path("common_skills") / resolved.relative_to(shared_root)).as_posix()


def _skill_name(path: Path, *, relative_path: Path, is_common: bool) -> str:
    del is_common
    parts = relative_path.parts
    if path.name == "SKILL.md":
        return parts[-2] if len(parts) >= 2 else path.parent.name
    return path.stem


class SkillLedger:
    """Read and append personal/shared skill mutation records."""

    def __init__(
        self,
        anima_dir: Path | None = None,
        *,
        data_dir: Path | None = None,
        common_skills_dir: Path | None = None,
    ) -> None:
        self.anima_dir = anima_dir.resolve() if anima_dir is not None else None
        self.data_dir = (data_dir or get_data_dir()).resolve()
        self.common_skills_dir = (common_skills_dir or (self.data_dir / "common_skills")).resolve()

    @property
    def personal_ledger_path(self) -> Path | None:
        if self.anima_dir is None:
            return None
        return self.anima_dir / "state" / "skill_ledger.jsonl"

    @property
    def common_ledger_path(self) -> Path:
        return self.data_dir / "shared" / "skill_ledger.jsonl"

    def record_change(
        self,
        path: Path,
        *,
        before_text: str,
        after_text: str | None,
        before_exists: bool,
        after_exists: bool,
        actor: str,
        route: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Record a completed write/delete and save the pre-change snapshot."""
        resolved = path.resolve()
        is_common = resolved.is_relative_to(self.common_skills_dir)
        if is_common:
            relative_path = Path("common_skills") / resolved.relative_to(self.common_skills_dir)
            ledger_path = self.common_ledger_path
            snapshot_dir = self.data_dir / "shared" / "skill_ledger"
            scope = "common"
            owner = self.anima_dir.name if self.anima_dir is not None else ""
        elif self.anima_dir is not None:
            try:
                relative_path = resolved.relative_to(self.anima_dir)
            except ValueError as exc:
                raise ValueError(f"Skill path is outside ledger roots: {path}") from exc
            ledger_path = self.personal_ledger_path
            snapshot_dir = self.anima_dir / "state" / "skill_ledger"
            scope = "personal"
            owner = self.anima_dir.name
        else:
            raise ValueError(f"Skill path is outside ledger roots: {path}")

        if ledger_path is None:
            raise ValueError("Personal skill ledger requires an anima directory")

        skill_name = _skill_name(path, relative_path=relative_path, is_common=is_common)
        entry_id = uuid.uuid4().hex
        snapshot_path = snapshot_dir / f"{entry_id}.md"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(before_text if before_exists else "", encoding="utf-8")
        snapshot_relative = (
            snapshot_path.relative_to(self.anima_dir).as_posix()
            if scope == "personal" and self.anima_dir is not None
            else snapshot_path.relative_to(self.data_dir).as_posix()
        )
        entry: dict[str, Any] = {
            "id": entry_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "skill_name": skill_name,
            "path": relative_path.as_posix(),
            "scope": scope,
            "anima": owner or None,
            "actor": actor,
            "route": route,
            "snapshot_path": snapshot_relative,
            "snapshot_sha256": _sha256(before_text if before_exists else ""),
            "before_sha256": _sha256(before_text) if before_exists else None,
            "after_sha256": _sha256(after_text) if after_exists and after_text is not None else None,
            "before_exists": before_exists,
            "after_exists": after_exists,
            "reason": reason,
        }
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        logger.info(
            "skill ledger recorded id=%s path=%s actor=%s route=%s",
            entry_id,
            entry["path"],
            actor,
            route,
        )
        return entry

    def read_entries(self, *, ledger_path: Path | None = None) -> list[dict[str, Any]]:
        """Read valid ledger rows from one ledger file."""
        selected_path = ledger_path or self.personal_ledger_path
        if selected_path is None or not selected_path.is_file():
            return []
        entries: list[dict[str, Any]] = []
        with selected_path.open(encoding="utf-8") as stream:
            for line_number, raw in enumerate(stream, start=1):
                if not raw.strip():
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed skill ledger row %s:%d", selected_path, line_number)
                    continue
                if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                    entries.append(entry)
        return entries


def capture_skill_document(
    path: Path, anima_dir: Path, *, common_skills_dir: Path | None = None
) -> tuple[bool, str] | None:
    """Capture a skill document before a possible mutation; None for other files."""
    if not is_skill_document_path(path, anima_dir, common_skills_dir=common_skills_dir):
        return None
    exists = path.is_file()
    return (exists, path.read_text(encoding="utf-8") if exists else "")


def record_skill_change(
    path: Path,
    captured: tuple[bool, str] | None,
    *,
    anima_dir: Path,
    after_text: str | None,
    after_exists: bool,
    actor: str,
    route: str,
    reason: str | None = None,
    data_dir: Path | None = None,
    common_skills_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Append a ledger row when the captured path is a skill document."""
    if captured is None:
        return None
    before_exists, before_text = captured
    return SkillLedger(
        anima_dir,
        data_dir=data_dir,
        common_skills_dir=common_skills_dir or get_common_skills_dir(),
    ).record_change(
        path,
        before_text=before_text,
        after_text=after_text,
        before_exists=before_exists,
        after_exists=after_exists,
        actor=actor,
        route=route,
        reason=reason,
    )


def ledger_files(data_dir: Path, *, anima: str | None = None) -> list[tuple[Path, Path | None]]:
    """Return (ledger path, owner anima directory) pairs for CLI listing."""
    data_dir = data_dir.resolve()
    candidates: list[tuple[Path, Path | None]] = []
    if anima:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", anima):
            raise ValueError("Invalid anima name for skill ledger")
        owner_dir = data_dir / "animas" / anima
        candidates.append((owner_dir / "state" / "skill_ledger.jsonl", owner_dir))
    else:
        animas_dir = data_dir / "animas"
        if animas_dir.is_dir():
            candidates.extend(
                (owner_dir / "state" / "skill_ledger.jsonl", owner_dir)
                for owner_dir in sorted(animas_dir.iterdir())
                if owner_dir.is_dir()
            )
    candidates.append((data_dir / "shared" / "skill_ledger.jsonl", None))
    return candidates


def rollback_skill_change(
    entry: dict[str, Any],
    *,
    data_dir: Path,
    anima_dir: Path | None,
    actor: str = "cli",
) -> tuple[bool, str]:
    """Restore one ledger row only if the current file still matches its after hash."""
    data_dir = data_dir.resolve()
    scope = entry.get("scope")
    relative = Path(str(entry.get("path") or ""))
    if relative.is_absolute() or ".." in relative.parts:
        return False, "Ledger path is invalid; rollback refused."

    if scope == "personal":
        owner = str(entry.get("anima") or (anima_dir.name if anima_dir else ""))
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", owner):
            return False, "Personal ledger entry has an invalid anima owner."
        root = (data_dir / "animas" / owner).resolve()
        if anima_dir is not None and root != anima_dir.resolve():
            return False, "Ledger entry belongs to a different anima."
        target = (root / relative).resolve()
        snapshot_root = root
        active_anima_dir = root
    elif scope == "common":
        root = (data_dir / "common_skills").resolve()
        if relative.parts and relative.parts[0] == "common_skills":
            relative = Path(*relative.parts[1:])
        target = (root / relative).resolve()
        snapshot_root = data_dir
        active_anima_dir = anima_dir
    else:
        return False, "Unknown ledger scope; rollback refused."

    allowed_root = root
    if not target.is_relative_to(allowed_root):
        return False, "Ledger path escapes the skill root; rollback refused."
    if scope == "personal":
        is_skill_document = is_skill_document_path(
            target,
            root,
            common_skills_dir=data_dir / "common_skills",
        )
    else:
        is_skill_document = is_skill_document_path(
            target,
            data_dir / "animas" / (anima_dir.name if anima_dir else "__none__"),
            common_skills_dir=root,
        )
    if not is_skill_document:
        return False, "Ledger path is not a skill document; rollback refused."

    expected_after = entry.get("after_sha256")
    currently_exists = target.is_file()
    if bool(entry.get("after_exists")) != currently_exists:
        return False, "The skill file existence changed after this ledger entry; rollback refused."
    current_text = target.read_text(encoding="utf-8") if currently_exists else ""
    current_hash = _sha256(current_text) if currently_exists else None
    if current_hash != expected_after:
        return False, "The skill was changed later; current SHA-256 does not match this entry's after hash."

    snapshot_relative = Path(str(entry.get("snapshot_path") or ""))
    if snapshot_relative.is_absolute() or ".." in snapshot_relative.parts:
        return False, "Ledger snapshot path is invalid; rollback refused."
    snapshot = (snapshot_root / snapshot_relative).resolve()
    if not snapshot.is_relative_to(snapshot_root.resolve()) or not snapshot.is_file():
        return False, "Ledger snapshot is missing or outside its state directory."
    before_text = snapshot.read_text(encoding="utf-8")
    if _sha256(before_text) != entry.get("snapshot_sha256"):
        return False, "Ledger snapshot SHA-256 does not match; rollback refused."

    before_change = (currently_exists, current_text)
    if entry.get("before_exists"):
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, before_text)
        restored_text: str | None = before_text
        restored_exists = True
    else:
        target.unlink(missing_ok=True)
        restored_text = None
        restored_exists = False

    ledger = SkillLedger(
        active_anima_dir,
        data_dir=data_dir,
        common_skills_dir=root if scope == "common" else data_dir / "common_skills",
    )
    ledger.record_change(
        target,
        before_text=before_change[1],
        after_text=restored_text,
        before_exists=before_change[0],
        after_exists=restored_exists,
        actor=actor,
        route="rollback",
        reason=f"rollback of {entry.get('id', 'unknown')}",
    )
    return True, f"Rolled back skill change {entry.get('id')} at {entry.get('path')}."
