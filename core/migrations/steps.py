# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Migration step implementations for AnimaWorks runtime data."""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.migrations.registry import MigrationStep, StepResult
from core.platform.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

_MEMORY_ARCHIVE_ROOTS = ("knowledge", "episodes", "procedures")
_LEGACY_ARCHIVE_DIRS = ("archived", "_archived", ".archive")
_RAGIGNORE_ARCHIVE_COMMENT = "# Archived memory files (unified)"
_RAGIGNORE_ARCHIVE_PATTERNS = tuple(
    f"*/{memory_root}/{archive_dir}/*"
    for memory_root in _MEMORY_ARCHIVE_ROOTS
    for archive_dir in ("archive", "archived")
)


# ── Category 1: Structural migrations ────────────────────────────


def step_person_to_anima(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Person → Anima rename. Call migrate_person_to_anima if persons/ exists."""
    details: list[str] = []
    try:
        persons_dir = data_dir / "persons"
        if not persons_dir.exists():
            return StepResult(changed=0, skipped=1, details=["persons/ not found; skip"])
        if dry_run:
            details.append("Would run migrate_person_to_anima (persons/ exists)")
            return StepResult(changed=1, skipped=0, details=details)
        from core.config.migrate import migrate_person_to_anima

        migrate_person_to_anima(data_dir)
        details.append("Person → Anima rename complete")
        return StepResult(changed=1, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_person_to_anima failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_config_md_to_json(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Migrate legacy config.md files to config.json."""
    details: list[str] = []
    try:
        animas_dir = data_dir / "animas"
        if not animas_dir.exists():
            return StepResult(changed=0, skipped=1, details=["animas/ not found"])
        has_legacy = any((d / "config.md").exists() for d in animas_dir.iterdir() if d.is_dir())
        if not has_legacy:
            return StepResult(changed=0, skipped=1, details=["No config.md files found"])
        if dry_run:
            details.append("Would migrate config.md → config.json")
            return StepResult(changed=1, skipped=0, details=details)
        from core.config.migrate import migrate_to_config_json

        migrate_to_config_json(data_dir)
        details.append("config.md → config.json migration complete")
        return StepResult(changed=1, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_config_md_to_json failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_model_config_to_status(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Migrate model config from config.json animas to status.json."""
    details: list[str] = []
    try:
        config_path = data_dir / "config.json"
        if not config_path.is_file():
            return StepResult(changed=0, skipped=1, details=["config.json not found"])
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        animas_section = raw.get("animas", {})
        if not animas_section:
            return StepResult(changed=0, skipped=1, details=["No animas in config.json"])
        _model_keys = {"model", "fallback_model", "max_tokens", "credential"}
        has_model_fields = any(
            isinstance(cfg, dict) and bool(_model_keys & set(cfg.keys())) for cfg in animas_section.values()
        )
        if not has_model_fields:
            return StepResult(changed=0, skipped=1, details=["No model fields in config.json animas"])
        from core.config.migrate import migrate_model_config_to_status

        results = migrate_model_config_to_status(data_dir, dry_run=dry_run)
        migrated = sum(1 for v in results.values() if v)
        details.extend([f"{k}: {v}" for k, v in results.items() if v])
        return StepResult(changed=migrated, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_model_config_to_status failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_credentials_migration(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Migrate shared/credentials.json to vault.json."""
    details: list[str] = []
    try:
        try:
            from core.config.vault import VaultManager
        except ImportError:
            return StepResult(changed=0, skipped=1, details=["core.config.vault not importable"])
        shared_creds = data_dir / "shared" / "credentials.json"
        if not shared_creds.is_file():
            return StepResult(changed=0, skipped=1, details=["shared/credentials.json not found"])
        if dry_run:
            details.append("Would migrate shared/credentials.json → vault.json")
            return StepResult(changed=1, skipped=0, details=details)
        vault = VaultManager(data_dir)
        count = vault.migrate_shared_credentials()
        details.append(f"Migrated {count} credential entries")
        return StepResult(changed=1 if count else 0, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_credentials_migration failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_vault_reencrypt(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Back up and re-encrypt every vault entry, rolling back on failure."""
    vault_path = data_dir / "vault.json"
    key_path = data_dir / "vault.key"
    if not vault_path.is_file():
        return StepResult(changed=0, skipped=1, details=["vault.json not found"])
    if dry_run:
        return StepResult(
            changed=1,
            skipped=0,
            details=["Would back up vault files and re-encrypt all entries"],
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    vault_backup = vault_path.with_name(f"{vault_path.name}.bak-{timestamp}")
    key_backup = key_path.with_name(f"{key_path.name}.bak-{timestamp}")
    key_existed = key_path.is_file()
    details: list[str] = []

    shutil.copy2(vault_path, vault_backup)
    details.append(f"Backed up {vault_path.name} to {vault_backup.name}")
    if key_existed:
        shutil.copy2(key_path, key_backup)
        details.append(f"Backed up {key_path.name} to {key_backup.name}")

    try:
        from core.config.vault import VaultError, VaultManager

        original = json.loads(vault_path.read_text(encoding="utf-8"))
        if not isinstance(original, dict):
            raise VaultError("vault.json root must be an object")

        vault = VaultManager(data_dir)
        if not key_existed:
            if not vault.generate_key():
                raise VaultError("Vault key generation is unavailable")
        elif vault._load_key() is None:
            raise VaultError("Existing vault key could not be loaded")

        encrypted: dict[str, dict[str, str]] = {}
        entry_count = 0
        for section, entries in original.items():
            if not isinstance(entries, dict):
                raise VaultError(f"Vault section {section!r} must be an object")
            encrypted_section: dict[str, str] = {}
            for key, value in entries.items():
                if not isinstance(value, str):
                    raise VaultError(f"Vault entry {section!r}/{key!r} must be a string")
                encrypted_section[key] = vault.encrypt(value)
                entry_count += 1
            encrypted[section] = encrypted_section

        vault.save_vault(encrypted)
        persisted = json.loads(vault_path.read_text(encoding="utf-8"))
        if persisted != encrypted:
            raise VaultError("Persisted vault content did not match encrypted data")
        for section, entries in persisted.items():
            for key, ciphertext in entries.items():
                if vault.decrypt(ciphertext) != original[section][key]:
                    raise VaultError(f"Round-trip verification failed for {section!r}/{key!r}")

        details.append(f"Re-encrypted and verified {entry_count} vault entries")
        return StepResult(changed=1, skipped=0, details=details)
    except Exception as exc:
        shutil.copy2(vault_backup, vault_path)
        if key_existed:
            shutil.copy2(key_backup, key_path)
        else:
            key_path.unlink(missing_ok=True)
        details.append("Rolled back vault.json and vault.key")
        logger.exception("step_vault_reencrypt failed; rollback complete")
        return StepResult(changed=0, skipped=0, details=details, error=str(exc))


def step_enable_skill_catalog_router(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Enable skill catalog routing in existing config.json files.

    The feature was introduced behind a default-off flag in commit 8f8b37a3.
    Current runtime defaults should route the skill catalog by message, so
    existing runtime configs are migrated to the new default explicitly.
    """
    details: list[str] = []
    try:
        config_path = data_dir / "config.json"
        if not config_path.is_file():
            return StepResult(changed=0, skipped=1, details=["config.json not found"])

        raw = json.loads(config_path.read_text(encoding="utf-8") or "{}")
        prompt = raw.get("prompt")
        if prompt is None:
            prompt = {}
        if not isinstance(prompt, dict):
            return StepResult(changed=0, skipped=1, details=["config.json prompt section is not an object"])

        defaults = {
            "skill_catalog_router_top_k": 5,
            "skill_catalog_router_min_score": 1.15,
            "skill_catalog_router_include_body": True,
        }
        changed_fields = []
        if prompt.get("skill_catalog_router_enabled") is not True:
            changed_fields.append("skill_catalog_router_enabled")
        changed_fields.extend(key for key in defaults if key not in prompt)
        if not changed_fields:
            return StepResult(changed=0, skipped=1, details=["skill catalog router already enabled"])

        if dry_run:
            details.append(f"Would update prompt fields: {', '.join(changed_fields)}")
            return StepResult(changed=1, skipped=0, details=details)

        prompt["skill_catalog_router_enabled"] = True
        for key, value in defaults.items():
            prompt.setdefault(key, value)
        raw["prompt"] = prompt
        atomic_write_json(config_path, raw, indent=2, ensure_ascii=False)
        try:
            from core.config import invalidate_cache

            invalidate_cache()
        except Exception:
            logger.debug("Failed to invalidate config cache after skill router migration", exc_info=True)
        details.append(f"Updated prompt fields: {', '.join(changed_fields)}")
        return StepResult(changed=1, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_enable_skill_catalog_router failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


# ── Category 2: Per-anima file migrations ───────────────────────


def _iter_anima_dirs(data_dir: Path) -> list[Path]:
    """Return anima directories that have identity.md."""
    animas_dir = data_dir / "animas"
    if not animas_dir.exists():
        return []
    return [d for d in sorted(animas_dir.iterdir()) if d.is_dir() and (d / "identity.md").exists()]


def _archive_destination(
    relative_path: Path,
    legacy_dir_name: str,
    occupied_files: set[Path],
    occupied_dirs: set[Path],
) -> tuple[Path | None, bool]:
    """Return an unused compatible archive-relative destination."""
    if relative_path in occupied_dirs or any(parent in occupied_files for parent in relative_path.parents):
        return None, False
    if relative_path not in occupied_files:
        return relative_path, False

    stem = relative_path.stem
    suffix = relative_path.suffix
    parent = relative_path.parent
    base_name = f"{stem}__from_{legacy_dir_name}"
    candidate = parent / f"{base_name}{suffix}"
    sequence = 2
    while candidate in occupied_files:
        candidate = parent / f"{base_name}_{sequence}{suffix}"
        sequence += 1
    if candidate in occupied_dirs:
        return None, False
    return candidate, True


def step_knowledge_archive_unify(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Move legacy per-memory archive directories into ``archive/``."""
    del verbose
    moved = 0
    collision_renames = 0
    details: list[str] = []
    try:
        for anima_dir in _iter_anima_dirs(data_dir):
            if anima_dir.is_symlink():
                logger.warning("Skipping symlinked anima directory during archive migration: %s", anima_dir)
                continue
            for memory_root_name in _MEMORY_ARCHIVE_ROOTS:
                memory_root = anima_dir / memory_root_name
                if memory_root.is_symlink():
                    logger.warning("Skipping symlinked memory root during archive migration: %s", memory_root)
                    continue
                archive_dir = memory_root / "archive"
                if archive_dir.is_symlink():
                    logger.warning("Skipping symlinked canonical archive during migration: %s", archive_dir)
                    continue
                archive_entries = list(archive_dir.rglob("*")) if archive_dir.is_dir() else []
                occupied_files = {
                    path.relative_to(archive_dir) for path in archive_entries if path.is_file() or path.is_symlink()
                }
                occupied_dirs = {
                    path.relative_to(archive_dir) for path in archive_entries if path.is_dir() and not path.is_symlink()
                }

                for legacy_dir_name in _LEGACY_ARCHIVE_DIRS:
                    legacy_dir = memory_root / legacy_dir_name
                    if legacy_dir.is_symlink():
                        logger.warning("Skipping symlinked legacy archive during migration: %s", legacy_dir)
                        continue
                    if not legacy_dir.is_dir():
                        continue
                    legacy_files = sorted(
                        (path for path in legacy_dir.rglob("*") if path.is_file() or path.is_symlink()),
                        key=lambda path: str(path.relative_to(legacy_dir)),
                    )
                    for source in legacy_files:
                        relative_path = source.relative_to(legacy_dir)
                        destination_relative, renamed = _archive_destination(
                            relative_path,
                            legacy_dir_name,
                            occupied_files,
                            occupied_dirs,
                        )
                        if destination_relative is None:
                            logger.warning(
                                "Skipping archive migration due to file/directory collision: %s",
                                source,
                            )
                            details.append(f"Skipped destination type conflict: {source}")
                            continue
                        occupied_files.add(destination_relative)
                        occupied_dirs.update(destination_relative.parents)
                        moved += 1
                        collision_renames += int(renamed)
                        if not dry_run:
                            destination = archive_dir / destination_relative
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(source), str(destination))

                    if not dry_run:
                        for child_dir in sorted(
                            (path for path in legacy_dir.rglob("*") if path.is_dir()),
                            key=lambda path: len(path.parts),
                            reverse=True,
                        ):
                            try:
                                child_dir.rmdir()
                            except OSError:
                                pass
                        try:
                            legacy_dir.rmdir()
                        except OSError:
                            pass

        action = "Would move" if dry_run else "Moved"
        details.append(f"{action} {moved} archived memory files")
        details.append(f"Collision-renamed files: {collision_renames}")
        return StepResult(changed=moved, skipped=int(moved == 0), details=details)
    except Exception as exc:
        logger.exception("step_knowledge_archive_unify failed")
        return StepResult(changed=0, skipped=0, details=details, error=str(exc))


def step_ragignore_archive_patterns(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Add unified archive exclusions to an existing ``.ragignore`` file."""
    del verbose
    ragignore_path = data_dir / ".ragignore"
    if ragignore_path.is_symlink():
        logger.warning("Skipping symlinked .ragignore during migration: %s", ragignore_path)
        return StepResult(changed=0, skipped=1, details=[".ragignore is a symlink; skip"])
    if not ragignore_path.is_file():
        return StepResult(changed=0, skipped=1, details=[".ragignore not found; skip"])

    try:
        content = ragignore_path.read_text(encoding="utf-8")
        existing_lines = {line.strip() for line in content.splitlines()}
        missing_patterns = [pattern for pattern in _RAGIGNORE_ARCHIVE_PATTERNS if pattern not in existing_lines]
        if not missing_patterns:
            return StepResult(changed=0, skipped=1, details=["Archive patterns already present"])

        details = [f"Added .ragignore pattern: {pattern}" for pattern in missing_patterns]
        if dry_run:
            return StepResult(
                changed=1, skipped=0, details=[detail.replace("Added", "Would add") for detail in details]
            )

        additions: list[str] = []
        if _RAGIGNORE_ARCHIVE_COMMENT not in existing_lines:
            additions.append(_RAGIGNORE_ARCHIVE_COMMENT)
        additions.extend(missing_patterns)
        base_content = content.rstrip("\n")
        separator = "\n\n" if base_content else ""
        ragignore_path.write_text(
            base_content + separator + "\n".join(additions) + "\n",
            encoding="utf-8",
        )
        return StepResult(changed=1, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_ragignore_archive_patterns failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


_TOOLS_RENAME_RE = re.compile(r"(?<![\w.])core([./])tools(?![\w])")
_TOOLS_RENAME_GLOBS = (
    "common_tools/*.py",
    "animas/*/tools/*.py",
    "common_skills/**/*.md",
    "animas/*/skills/**/*.md",
    "common_knowledge/**/*.md",
    "reference/**/*.md",
)


def step_rename_core_tools_to_integrations(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Rewrite ``core.tools`` references in runtime tools and skills to ``core.integrations``.

    The ``core.tools`` alias keeps old files working; this keeps the runtime copies on the canonical name.
    Originals are copied to ``backups/<timestamp>_tools_rename/`` before rewriting.
    """
    del verbose
    try:
        targets: list[Path] = []
        for pattern in _TOOLS_RENAME_GLOBS:
            for path in sorted(data_dir.glob(pattern)):
                if not path.is_file() or path.is_symlink():
                    continue
                if _TOOLS_RENAME_RE.search(path.read_text(encoding="utf-8", errors="replace")):
                    targets.append(path)
        if not targets:
            return StepResult(changed=0, skipped=1, details=["No core.tools references found"])
        details = [str(path.relative_to(data_dir)) for path in targets]
        if dry_run:
            return StepResult(changed=len(targets), skipped=0, details=[f"Would rewrite: {d}" for d in details])
        backup_root = data_dir / "backups" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_tools_rename"
        for path, rel in zip(targets, details, strict=True):
            backup = backup_root / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            text = path.read_text(encoding="utf-8")
            path.write_text(
                _TOOLS_RENAME_RE.sub(lambda m: f"core{m.group(1)}integrations", text),
                encoding="utf-8",
            )
        return StepResult(changed=len(targets), skipped=0, details=[f"Rewrote: {d}" for d in details])
    except Exception as exc:
        logger.exception("step_rename_core_tools_to_integrations failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_split_board_by_company(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Split the legacy ``board`` channel into company-scoped channels.

    Company membership is deliberately resolved from every board member's
    ``status.json`` during each invocation.  The legacy board history is never
    copied or removed: only its metadata is closed after all successor channel
    files and metadata have been written.
    """
    del verbose
    channels_dir = data_dir / "shared" / "channels"
    legacy_meta_path = channels_dir / "board.meta.json"
    if not legacy_meta_path.is_file():
        return StepResult(changed=0, skipped=1, details=["board.meta.json not found; skip"])

    try:
        from core.config.models import read_anima_company
        from core.exceptions import RecipientNotFoundError
        from core.messaging.messenger import _validate_name

        legacy_meta = json.loads(legacy_meta_path.read_text(encoding="utf-8"))
        if not isinstance(legacy_meta, dict):
            raise ValueError("board.meta.json root must be an object")
        raw_members = legacy_meta.get("members")
        if not isinstance(raw_members, list) or not all(isinstance(member, str) for member in raw_members):
            raise ValueError("board.meta.json members must be a list of strings")
        if not raw_members:
            return StepResult(changed=0, skipped=1, details=["Legacy board is already closed"])

        members_by_company: dict[str, list[str]] = {}
        unassigned_members: list[str] = []
        for member in raw_members:
            try:
                _validate_name(member, "anima name")
            except RecipientNotFoundError:
                unassigned_members.append(member)
                continue
            company = read_anima_company(data_dir / "animas" / member)
            if company is None:
                unassigned_members.append(member)
                continue
            channel = f"board-{company}"
            try:
                _validate_name(channel, "channel name")
            except RecipientNotFoundError as exc:
                raise ValueError(f"Company {company!r} cannot be mapped to a board channel") from exc
            members_by_company.setdefault(company, []).append(member)

        if not members_by_company:
            return StepResult(
                changed=0,
                skipped=1,
                details=["No company-assigned legacy board members found; board left unchanged"],
            )

        # Preflight all existing successor metadata before making any changes.
        successor_meta: dict[str, dict[str, Any]] = {}
        for company, members in sorted(members_by_company.items()):
            channel = f"board-{company}"
            meta_path = channels_dir / f"{channel}.meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if not isinstance(meta, dict):
                    raise ValueError(f"{meta_path.name} root must be an object")
            else:
                meta = dict(legacy_meta)
            meta["members"] = members
            meta["closed"] = False
            successor_meta[channel] = meta

        details: list[str] = []
        changed = 0
        for channel, meta in successor_meta.items():
            channel_path = channels_dir / f"{channel}.jsonl"
            meta_path = channels_dir / f"{channel}.meta.json"
            if not channel_path.exists():
                changed += 1
                details.append(f"{'Would create' if dry_run else 'Created'} #{channel} channel")
                if not dry_run:
                    channel_path.write_text("", encoding="utf-8")

            current_meta: dict[str, Any] | None = None
            if meta_path.exists():
                current_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if current_meta != meta:
                changed += 1
                details.append(f"{'Would update' if dry_run else 'Updated'} #{channel} metadata")
                if not dry_run:
                    atomic_write_json(meta_path, meta, indent=2, ensure_ascii=False, trailing_newline=False)

        closed_legacy_meta = dict(legacy_meta)
        closed_legacy_meta["members"] = []
        closed_legacy_meta["closed"] = True
        if closed_legacy_meta != legacy_meta:
            changed += 1
            details.append(f"{'Would close' if dry_run else 'Closed'} legacy #board")
            if not dry_run:
                atomic_write_json(
                    legacy_meta_path,
                    closed_legacy_meta,
                    indent=2,
                    ensure_ascii=False,
                    trailing_newline=False,
                )

        if unassigned_members:
            details.append(
                "Legacy board members without company assignment were not added to successor channels: "
                + ", ".join(unassigned_members)
            )
        return StepResult(changed=changed, skipped=int(changed == 0), details=details)
    except Exception as exc:
        logger.exception("step_split_board_by_company failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_channel_company_defaults(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Ensure open-channel meta exists and apply ``channel_company_defaults``.

    For every open channel (empty members, not closed — including meta-less
    legacy channels such as general/ops/legal):

    * create/update ``*.meta.json`` so the channel is explicit
    * set ``company`` from ``config.json`` → ``channel_company_defaults`` when
      present; otherwise leave company empty (no auto-inference)
    * skip when company is already set (idempotent)
    * never touch restricted (non-empty members) or closed channels
    * never modify jsonl history
    """
    del verbose
    channels_dir = data_dir / "shared" / "channels"
    if not channels_dir.is_dir():
        return StepResult(changed=0, skipped=1, details=["shared/channels/ not found; skip"])

    try:
        defaults: dict[str, str] = {}
        config_path = data_dir / "config.json"
        if config_path.is_file():
            raw_config = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(raw_config, dict):
                raw_defaults = raw_config.get("channel_company_defaults") or {}
                if isinstance(raw_defaults, dict):
                    defaults = {
                        str(k): str(v).strip()
                        for k, v in raw_defaults.items()
                        if isinstance(k, str) and isinstance(v, str) and str(v).strip()
                    }

        channel_names: set[str] = set()
        for path in channels_dir.iterdir():
            if not path.is_file():
                continue
            if path.name.endswith(".jsonl"):
                channel_names.add(path.name[: -len(".jsonl")])
            elif path.name.endswith(".meta.json"):
                channel_names.add(path.name[: -len(".meta.json")])

        details: list[str] = []
        changed = 0
        skipped = 0

        for channel in sorted(channel_names):
            meta_path = channels_dir / f"{channel}.meta.json"
            desired_company = defaults.get(channel, "")

            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if not isinstance(meta, dict):
                    details.append(f"#{channel}: invalid meta root; skip")
                    skipped += 1
                    continue
                members = meta.get("members", [])
                closed = bool(meta.get("closed", False))
                # Preserve malformed metadata rather than risking a destructive
                # rewrite.  Only an actual empty list is an open channel.
                if not isinstance(members, list):
                    details.append(f"#{channel}: invalid members field; skip")
                    skipped += 1
                    continue
                # Restricted or closed channels: never touch.
                if members or closed:
                    skipped += 1
                    continue
                existing_company = (meta.get("company") or "").strip() if isinstance(meta.get("company"), str) else ""
                if existing_company:
                    skipped += 1
                    continue
                new_meta = dict(meta)
                new_meta["company"] = desired_company
                if "members" not in new_meta:
                    new_meta["members"] = []
                if new_meta == meta:
                    skipped += 1
                    continue
                changed += 1
                if desired_company:
                    details.append(f"{'Would set' if dry_run else 'Set'} #{channel} company={desired_company!r}")
                else:
                    details.append(f"{'Would update' if dry_run else 'Updated'} #{channel} meta (company unset)")
                if not dry_run:
                    atomic_write_json(meta_path, new_meta, indent=2, ensure_ascii=False, trailing_newline=False)
            else:
                # meta-less open channel (legacy): create meta (company from defaults or empty).
                new_meta = {
                    "members": [],
                    "created_by": "",
                    "created_at": "",
                    "description": "",
                    "closed": False,
                    "company": desired_company,
                }
                changed += 1
                if desired_company:
                    details.append(
                        f"{'Would create' if dry_run else 'Created'} #{channel} meta with company={desired_company!r}"
                    )
                else:
                    details.append(f"{'Would create' if dry_run else 'Created'} #{channel} meta (company unset)")
                if not dry_run:
                    atomic_write_json(meta_path, new_meta, indent=2, ensure_ascii=False, trailing_newline=False)

        if changed == 0 and not details:
            details.append("No open channels needed company defaults")
        return StepResult(changed=changed, skipped=skipped, details=details)
    except Exception as exc:
        logger.exception("step_channel_company_defaults failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_legacy_flat_skill_migration(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Convert legacy flat local skill files to trusted SKILL.md bundles."""
    from core.migrations.legacy_flat_skills import migrate_legacy_flat_skills

    return migrate_legacy_flat_skills(data_dir, dry_run=dry_run, verbose=verbose)


def step_current_task_rename(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Rename current_task.md to current_state.md for each anima."""
    details: list[str] = []
    changed = 0
    try:
        for anima_dir in _iter_anima_dirs(data_dir):
            state_dir = anima_dir / "state"
            old_task = state_dir / "current_task.md"
            new_state = state_dir / "current_state.md"
            root_task = anima_dir / "current_task.md"
            if root_task.exists():
                if dry_run:
                    details.append(f"{anima_dir.name}: would migrate root current_task.md")
                else:
                    try:
                        if not new_state.exists():
                            state_dir.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(root_task), str(new_state))
                            details.append(f"{anima_dir.name}: root current_task.md → state/")
                        else:
                            root_task.unlink()
                            details.append(f"{anima_dir.name}: removed duplicate root current_task.md")
                        changed += 1
                    except OSError as exc:
                        details.append(f"{anima_dir.name}: failed - {exc}")
                continue
            if old_task.exists() and not new_state.exists():
                if dry_run:
                    details.append(f"{anima_dir.name}: would rename current_task.md → current_state.md")
                else:
                    try:
                        old_task.rename(new_state)
                        details.append(f"{anima_dir.name}: current_task.md → current_state.md")
                        changed += 1
                    except OSError as exc:
                        details.append(f"{anima_dir.name}: failed - {exc}")
        return StepResult(changed=changed, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_current_task_rename failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_trust_state_per_session(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Remove the legacy anima-wide trust state file."""
    details: list[str] = []
    changed = 0
    try:
        for anima_dir in _iter_anima_dirs(data_dir):
            legacy_state = anima_dir / "run" / "min_trust_seen"
            if not legacy_state.is_file():
                continue
            changed += 1
            if dry_run:
                details.append(f"{anima_dir.name}: would remove run/min_trust_seen")
                continue
            try:
                legacy_state.unlink()
                details.append(f"{anima_dir.name}: removed run/min_trust_seen")
            except OSError as exc:
                changed -= 1
                details.append(f"{anima_dir.name}: failed to remove run/min_trust_seen - {exc}")
        if not details:
            details.append("No shared run/min_trust_seen files found")
        return StepResult(changed=changed, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_trust_state_per_session failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_pending_merge(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Merge pending.md into current_state.md for each anima."""
    details: list[str] = []
    changed = 0
    try:
        for anima_dir in _iter_anima_dirs(data_dir):
            pending = anima_dir / "state" / "pending.md"
            if not pending.exists():
                continue
            content = pending.read_text(encoding="utf-8").strip()
            if not content:
                if dry_run:
                    details.append(f"{anima_dir.name}: would remove empty pending.md")
                else:
                    pending.unlink()
                    details.append(f"{anima_dir.name}: removed empty pending.md")
                changed += 1
                continue
            current = anima_dir / "state" / "current_state.md"
            if dry_run:
                details.append(f"{anima_dir.name}: would merge pending.md into current_state.md")
                changed += 1
                continue
            existing = current.read_text(encoding="utf-8") if current.exists() else ""
            merged = existing.rstrip() + "\n\n## Migrated from pending.md\n\n" + content
            current.parent.mkdir(parents=True, exist_ok=True)
            current.write_text(merged, encoding="utf-8")
            pending.unlink()
            details.append(f"{anima_dir.name}: merged pending.md into current_state.md")
            changed += 1
        return StepResult(changed=changed, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_pending_merge failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_permissions_migration(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Migrate permissions.md to permissions.json for each anima."""
    details: list[str] = []
    changed = 0
    try:
        from core.config.migrate import migrate_permissions_md_to_json

        for anima_dir in _iter_anima_dirs(data_dir):
            md_path = anima_dir / "permissions.md"
            json_path = anima_dir / "permissions.json"
            if not md_path.exists() or json_path.exists():
                continue
            if dry_run:
                details.append(f"{anima_dir.name}: would migrate permissions.md → permissions.json")
                changed += 1
                continue
            try:
                migrate_permissions_md_to_json(anima_dir)
                details.append(f"{anima_dir.name}: permissions.md → permissions.json")
                changed += 1
            except Exception as exc:
                details.append(f"{anima_dir.name}: failed - {exc}")
        return StepResult(changed=changed, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_permissions_migration failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_shortterm_layout(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Move shortterm/session_state.json to shortterm/chat/ for each anima."""
    details: list[str] = []
    changed = 0
    try:
        for anima_dir in _iter_anima_dirs(data_dir):
            shortterm = anima_dir / "shortterm"
            root_session = shortterm / "session_state.json"
            chat_dir = shortterm / "chat"
            if not root_session.exists():
                continue
            if (chat_dir / "session_state.json").exists():
                if dry_run:
                    details.append(f"{anima_dir.name}: would remove root session_state.json (chat/ has one)")
                else:
                    root_session.unlink()
                changed += 1
                continue
            if dry_run:
                details.append(f"{anima_dir.name}: would move session_state.json → shortterm/chat/")
            else:
                chat_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(root_session), str(chat_dir / "session_state.json"))
                details.append(f"{anima_dir.name}: session_state.json → shortterm/chat/")
            changed += 1
        return StepResult(changed=changed, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_shortterm_layout failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_cron_format(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Migrate cron.md from Japanese schedules to cron expressions."""
    details: list[str] = []
    try:
        animas_dir = data_dir / "animas"
        if not animas_dir.exists():
            return StepResult(changed=0, skipped=1, details=["animas/ not found"])
        if dry_run:
            count = sum(1 for d in animas_dir.iterdir() if d.is_dir() and (d / "cron.md").exists())
            if count:
                details.append(f"Would migrate cron.md for {count} anima(s)")
            return StepResult(changed=count, skipped=0, details=details)
        from core.config.migrate import migrate_all_cron

        count = migrate_all_cron(animas_dir)  # takes animas/ dir, not data_dir
        details.append(f"Migrated cron.md for {count} anima(s)")
        return StepResult(changed=count, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_cron_format failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_knowledge_frontmatter(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Repair knowledge frontmatter for each anima."""
    details: list[str] = []
    changed = 0
    try:
        try:
            from core.memory.frontmatter import FrontmatterService
        except ImportError:
            return StepResult(changed=0, skipped=1, details=["FrontmatterService not importable"])
        for anima_dir in _iter_anima_dirs(data_dir):
            knowledge_dir = anima_dir / "knowledge"
            if not knowledge_dir.exists():
                continue
            svc = FrontmatterService(anima_dir, knowledge_dir, anima_dir / "procedures")
            if dry_run:
                md_count = len(list(knowledge_dir.glob("*.md")))
                if md_count:
                    details.append(f"{anima_dir.name}: would repair {md_count} knowledge file(s)")
                    changed += 1
                continue
            try:
                n = svc.repair_knowledge_frontmatter()
                if n:
                    details.append(f"{anima_dir.name}: repaired {n} knowledge file(s)")
                    changed += n
            except Exception as exc:
                details.append(f"{anima_dir.name}: failed - {exc}")
        return StepResult(changed=changed, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_knowledge_frontmatter failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_procedure_frontmatter(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Ensure procedure frontmatter for each anima."""
    details: list[str] = []
    changed = 0
    try:
        try:
            from core.memory.frontmatter import FrontmatterService
        except ImportError:
            return StepResult(changed=0, skipped=1, details=["FrontmatterService not importable"])
        for anima_dir in _iter_anima_dirs(data_dir):
            procedures_dir = anima_dir / "procedures"
            if not procedures_dir.exists():
                continue
            svc = FrontmatterService(anima_dir, anima_dir / "knowledge", procedures_dir)
            if dry_run:
                md_count = len(list(procedures_dir.glob("*.md")))
                if md_count:
                    details.append(f"{anima_dir.name}: would ensure frontmatter for {md_count} procedure(s)")
                    changed += 1
                continue
            try:
                n = svc.ensure_procedure_frontmatter()
                if n:
                    details.append(f"{anima_dir.name}: added frontmatter to {n} procedure(s)")
                    changed += n
            except Exception as exc:
                details.append(f"{anima_dir.name}: failed - {exc}")
        return StepResult(changed=changed, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_procedure_frontmatter failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_current_task_references(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Replace current_task references with current_state in anima config files."""
    details: list[str] = []
    changed = 0
    files_to_scan = ["heartbeat.md", "cron.md", "injection.md"]
    patterns = [
        (re.compile(r"current_task\.md", re.IGNORECASE), "current_state.md"),
        (re.compile(r"\bcurrent_task\b"), "current_state"),
    ]
    try:
        for anima_dir in _iter_anima_dirs(data_dir):
            for fname in files_to_scan:
                path = anima_dir / fname
                if not path.exists():
                    continue
                content = path.read_text(encoding="utf-8")
                new_content = content
                for pat, repl in patterns:
                    new_content = pat.sub(repl, new_content)
                if new_content != content:
                    if dry_run:
                        details.append(f"{anima_dir.name}/{fname}: would replace current_task refs")
                    else:
                        path.write_text(new_content, encoding="utf-8")
                        details.append(f"{anima_dir.name}/{fname}: replaced current_task refs")
                    changed += 1
        return StepResult(changed=changed, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_current_task_references failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


# ── Category 3: Framework template sync ──────────────────────────


def step_template_sync(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Sync bundled shared templates into runtime data."""
    del verbose
    from core.migrations.template_sync import sync_runtime_templates
    from core.paths import _get_locale

    result = sync_runtime_templates(data_dir, locale=_get_locale(), dry_run=dry_run)
    if not dry_run and result.error is None and result.changed == 0:
        return StepResult(
            changed=1,
            skipped=result.skipped,
            details=[*result.details, "No runtime template changes required; migration marked applied"],
        )
    return result


def step_models_json_add_cursor_gemini(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Add the legacy cursor and Gemini model entries to runtime models.json."""
    del verbose
    models_path = data_dir / "models.json"
    if not models_path.is_file():
        return StepResult(changed=0, skipped=1, details=["models.json not found"])

    try:
        raw = json.loads(models_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return StepResult(changed=0, skipped=1, details=["models.json is not an object"])
        new_entries = {
            "cursor/*": {"mode": "D", "context_window": 1000000},
            "gemini/*": {"mode": "G", "context_window": 1000000},
        }
        added = [key for key in new_entries if key not in raw]
        if not added:
            return StepResult(changed=0, skipped=1, details=["models.json already has cursor/*/gemini/* entries"])
        if not dry_run:
            for key in added:
                raw[key] = new_entries[key]
            atomic_write_json(models_path, raw, indent=2, ensure_ascii=False)
        action = "Would add" if dry_run else "Added"
        return StepResult(changed=len(added), skipped=0, details=[f"{action} models.json entries: {', '.join(added)}"])
    except (json.JSONDecodeError, OSError) as exc:
        return StepResult(changed=0, skipped=1, details=[f"models.json update skipped: {exc}"])


def step_models_json_mode_b_to_a(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Map retired Mode B models.json entries to Mode A."""
    del verbose
    models_path = data_dir / "models.json"
    if not models_path.is_file():
        return StepResult(changed=0, skipped=1, details=["models.json not found"])

    try:
        models = json.loads(models_path.read_text(encoding="utf-8"))
        if not isinstance(models, dict):
            return StepResult(changed=0, skipped=1, details=["models.json is not an object"])
        patched = [
            pattern
            for pattern, entry in models.items()
            if isinstance(entry, dict) and str(entry.get("mode", "")).upper() == "B"
        ]
        if not patched:
            return StepResult(changed=0, skipped=1, details=["No Mode B entries found in models.json"])
        if dry_run:
            details = [f"Would map Mode B to A in models.json: {', '.join(patched)}"]
        else:
            for pattern in patched:
                models[pattern]["mode"] = "A"
            atomic_write_json(models_path, models, indent=2, ensure_ascii=False)
            details = [f"Mapped Mode B to A in models.json: {', '.join(patched)}"]
        return StepResult(changed=len(patched), skipped=0, details=details)
    except (OSError, ValueError, AttributeError) as exc:
        return StepResult(changed=0, skipped=0, details=[], error=f"models.json: {exc}")


def step_models_json_create(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Create models.json from template if missing."""
    details: list[str] = []
    try:
        from core.paths import TEMPLATES_DIR

        dst = data_dir / "models.json"
        if dst.exists():
            return StepResult(changed=0, skipped=1, details=["models.json already exists"])
        src = TEMPLATES_DIR / "_shared" / "config_defaults" / "models.json"
        if not src.is_file():
            return StepResult(changed=0, skipped=1, details=["models.json template not found"])
        if dry_run:
            details.append("Would copy models.json from template")
            return StepResult(changed=1, skipped=0, details=details)
        shutil.copy2(src, dst)
        details.append("Created models.json from template")
        return StepResult(changed=1, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_models_json_create failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_global_permissions_create(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Create permissions.global.json from template if missing."""
    details: list[str] = []
    try:
        from core.paths import TEMPLATES_DIR

        dst = data_dir / "permissions.global.json"
        if dst.exists():
            return StepResult(changed=0, skipped=1, details=["permissions.global.json already exists"])
        src = TEMPLATES_DIR / "_shared" / "config_defaults" / "permissions.global.json"
        if not src.is_file():
            return StepResult(changed=0, skipped=1, details=["permissions.global.json template not found"])
        if dry_run:
            details.append("Would copy permissions.global.json from template")
            return StepResult(changed=1, skipped=0, details=details)
        shutil.copy2(src, dst)
        details.append("Created permissions.global.json from template")
        return StepResult(changed=1, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_global_permissions_create failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_grok_models_json(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Add Mode X Grok Build entries to an existing runtime models.json."""
    models_path = data_dir / "models.json"
    if not models_path.exists():
        return StepResult(changed=0, skipped=1, details=["models.json not found"])

    try:
        raw = json.loads(models_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return StepResult(changed=0, skipped=1, details=["models.json is not an object"])

        new_entries = {
            "grok/grok-4.5": {"mode": "X", "context_window": 500000},
            "grok/*": {"mode": "X", "context_window": 500000},
        }
        added = [key for key in new_entries if key not in raw]
        if not added:
            return StepResult(changed=0, skipped=1, details=["models.json already has Grok entries"])

        if not dry_run:
            for key in added:
                raw[key] = new_entries[key]
            atomic_write_json(models_path, raw, indent=2, ensure_ascii=False)

        action = "Would add" if dry_run else "Added"
        return StepResult(
            changed=len(added),
            skipped=0,
            details=[f"{action} models.json entries: {', '.join(added)}"],
        )
    except (json.JSONDecodeError, OSError) as exc:
        return StepResult(changed=0, skipped=1, details=[f"models.json update skipped: {exc}"])


# ── Category 4: Database sync ────────────────────────────────────


def step_tool_prompts_db_to_md(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Write legacy tool prompt DB customizations to active templates."""
    db_path = data_dir / "tool_prompts.sqlite3"
    if not db_path.is_file():
        return StepResult(changed=0, skipped=1, details=["tool_prompts.sqlite3 not found; skip"])

    details: list[str] = []
    try:
        from core.migrations.tool_prompts import migrate_tool_prompts
        from core.paths import TEMPLATES_DIR

        written, skipped = migrate_tool_prompts(
            db_path,
            TEMPLATES_DIR,
            dry_run=dry_run,
            output=details.append,
        )
        if written == 0 and skipped == 0:
            details.append("No tool prompt rows found; skip")
            return StepResult(changed=0, skipped=1, details=details)
        return StepResult(changed=written, skipped=skipped, details=details)
    except Exception as exc:
        logger.exception("step_tool_prompts_db_to_md failed")
        return StepResult(changed=0, skipped=0, details=details, error=str(exc))


# ── Category 5: Version tracking ────────────────────────────────


def step_engine_timeout_config_cleanup(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Drop supervisor stream-kill settings and rename runner liveness timeout."""
    del verbose
    config_path = data_dir / "config.json"
    if not config_path.is_file():
        return StepResult(changed=0, skipped=1, details=["config.json not found; skip"])

    try:
        config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
        if not isinstance(config, dict):
            return StepResult(changed=0, skipped=1, details=["config.json root is not an object"])
        server = config.get("server")
        if server is None:
            server = {}
            config["server"] = server
        if not isinstance(server, dict):
            return StepResult(changed=0, skipped=1, details=["config.json server section is not an object"])

        details: list[str] = []
        if "busy_hang_threshold" in server:
            if "runner_liveness_timeout" not in server:
                server["runner_liveness_timeout"] = server["busy_hang_threshold"]
                details.append("Moved server.busy_hang_threshold to server.runner_liveness_timeout")
            else:
                details.append("Preserved server.runner_liveness_timeout")
            del server["busy_hang_threshold"]
        if "max_streaming_duration" in server:
            del server["max_streaming_duration"]
            details.append("Removed server.max_streaming_duration")

        if not details:
            return StepResult(changed=0, skipped=1, details=["No retired engine timeout settings found"])
        if dry_run:
            return StepResult(changed=1, skipped=0, details=[f"Would {detail.lower()}" for detail in details])

        atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
        return StepResult(changed=1, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_engine_timeout_config_cleanup failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_rag_vector_worker_config_cleanup(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Remove retired RAG vector-worker settings without deleting stored data."""
    del verbose
    config_path = data_dir / "config.json"
    retired_keys = (
        "vector_worker_enabled",
        "vector_worker_host",
        "vector_worker_port",
        "vector_worker_startup_timeout_seconds",
        "vector_worker_request_timeout_seconds",
        "vector_worker_restart_backoff_seconds",
        "vector_worker_shutdown_timeout_seconds",
        "vector_worker_fallback_direct",
        "startup_repair_preflight_enabled",
        "startup_repair_window_minutes",
        "repair_stop_anima",
    )
    details: list[str] = []
    changed = 0

    if not config_path.is_file():
        details.append("config.json not found; skip settings cleanup")
    else:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
            if not isinstance(config, dict):
                details.append("config.json root is not an object; settings cleanup skipped")
            else:
                rag = config.get("rag")
                if rag is not None and not isinstance(rag, dict):
                    details.append("config.json rag section is not an object; settings cleanup skipped")
                else:
                    removed = [key for key in retired_keys if isinstance(rag, dict) and key in rag]
                    details.extend(
                        f"{'Would remove' if dry_run else 'Removed'} rag.{key} from config.json" for key in removed
                    )
                    if removed:
                        changed = 1
                        if not dry_run:
                            for key in removed:
                                del rag[key]
                            atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
                    else:
                        details.append("No retired RAG vector-worker settings found")
        except Exception as exc:
            logger.exception("step_rag_vector_worker_config_cleanup failed")
            return StepResult(changed=0, skipped=0, details=details, error=str(exc))

    if any((data_dir / "logs").glob("vector-worker.log*")):
        details.append("Left logs/vector-worker.log* untouched; these logs are no longer rotated")
    if (data_dir / "vectordb").is_dir():
        details.append("data_dir/vectordb is unused; it was left in place and may be removed manually")
    return StepResult(changed=changed, skipped=0 if changed else 1, details=details)


def step_retire_chain_timeout_keys(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Remove retired model keys (max_turns/max_chains/llm_timeout) from runtime config."""
    del verbose
    retired_keys = {"max_turns", "max_chains", "llm_timeout"}
    changed_files = 0
    details: list[str] = []

    def _remove_keys(record: dict[str, Any]) -> list[str]:
        removed = sorted(retired_keys.intersection(record))
        for key in removed:
            del record[key]
        return removed

    try:
        config_path = data_dir / "config.json"
        if config_path.is_file():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
            except (ValueError, OSError):
                details.append("config.json is not valid JSON; skip")
                return StepResult(changed=0, skipped=1, details=details)
            if not isinstance(config, dict):
                return StepResult(changed=0, skipped=1, details=["config.json root is not an object"])

            config_changed = False
            defaults = config.get("anima_defaults")
            if isinstance(defaults, dict):
                removed = _remove_keys(defaults)
                if removed:
                    config_changed = True
                    action = "Would remove" if dry_run else "Removed"
                    details.append(f"{action} retired settings from anima_defaults: {', '.join(removed)}")

            animas = config.get("animas")
            if isinstance(animas, dict):
                for name, record in animas.items():
                    if isinstance(record, dict):
                        removed = _remove_keys(record)
                        if removed:
                            config_changed = True
                            action = "Would remove" if dry_run else "Removed"
                            details.append(f"{action} retired settings from animas.{name}: {', '.join(removed)}")

            if config_changed:
                changed_files += 1
                if not dry_run:
                    atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
        else:
            details.append("config.json not found; skip")

        for anima_dir in _iter_anima_dirs(data_dir):
            status_path = anima_dir / "status.json"
            if not status_path.is_file():
                continue
            status = json.loads(status_path.read_text(encoding="utf-8") or "{}")
            if not isinstance(status, dict):
                continue
            removed = _remove_keys(status)
            if not removed:
                continue
            changed_files += 1
            relative_path = status_path.relative_to(data_dir)
            action = "Would remove" if dry_run else "Removed"
            details.append(f"{action} retired settings from {relative_path}: {', '.join(removed)}")
            if not dry_run:
                atomic_write_json(status_path, status, indent=2, ensure_ascii=False)

        if not changed_files:
            details.append("No retired model keys found")
        return StepResult(changed=changed_files, skipped=0 if changed_files else 1, details=details)
    except Exception as exc:
        logger.exception("step_retire_chain_timeout_keys failed")
        return StepResult(changed=0, skipped=0, details=details, error=str(exc))


def step_memory_maintenance_config_cleanup_20260927(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Remove the retired housekeeping hygiene grace-period setting."""
    del verbose
    config_path = data_dir / "config.json"
    if not config_path.is_file():
        return StepResult(changed=0, skipped=1, details=["config.json not found; skip"])

    try:
        config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
        if not isinstance(config, dict):
            return StepResult(changed=0, skipped=1, details=["config.json root is not an object"])
        housekeeping = config.get("housekeeping")
        if housekeeping is None:
            return StepResult(changed=0, skipped=1, details=["housekeeping section not found; skip"])
        if not isinstance(housekeeping, dict):
            return StepResult(changed=0, skipped=1, details=["housekeeping section is not an object"])
        retired_setting = "hygiene_grace_days"
        if retired_setting not in housekeeping:
            return StepResult(changed=0, skipped=1, details=["No retired memory maintenance settings found"])

        del housekeeping[retired_setting]
        detail = "Removed housekeeping.hygiene_grace_days"
        if dry_run:
            return StepResult(changed=1, skipped=0, details=[f"Would {detail.lower()}"])

        atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
        return StepResult(changed=1, skipped=0, details=[detail])
    except Exception as exc:
        logger.exception("step_memory_maintenance_config_cleanup_20260927 failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_priming_config_cleanup_20260927(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Drop the retired rag.max_graph_hops setting from config.json."""
    del verbose
    config_path = data_dir / "config.json"
    if not config_path.is_file():
        return StepResult(changed=0, skipped=1, details=["config.json not found; skip"])

    try:
        config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
        if not isinstance(config, dict):
            return StepResult(changed=0, skipped=1, details=["config.json root is not an object"])
        rag = config.get("rag")
        if rag is None:
            return StepResult(changed=0, skipped=1, details=["No rag section; skip"])
        if not isinstance(rag, dict):
            return StepResult(changed=0, skipped=1, details=["config.json rag section is not an object"])
        if "max_graph_hops" not in rag:
            return StepResult(changed=0, skipped=1, details=["rag.max_graph_hops not found; skip"])
        if dry_run:
            return StepResult(changed=1, skipped=0, details=["Would drop rag.max_graph_hops"])

        del rag["max_graph_hops"]
        atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
        return StepResult(changed=1, skipped=0, details=["Dropped rag.max_graph_hops"])
    except Exception as exc:
        logger.exception("step_priming_config_cleanup_20260927 failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_remove_process_model_fields(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Remove retired process topology fields from each anima's status.json."""
    del verbose
    from core.memory._io import atomic_write_text

    details: list[str] = []
    errors: list[str] = []
    changed = 0
    skipped = 0

    for anima_dir in _iter_anima_dirs(data_dir):
        status_path = anima_dir / "status.json"
        if not status_path.is_file():
            skipped += 1
            continue
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            skipped += 1
            details.append(f"{anima_dir.name}: skipped invalid status.json ({exc})")
            continue
        if not isinstance(status, dict):
            skipped += 1
            details.append(f"{anima_dir.name}: skipped status.json because it is not an object")
            continue

        removed_fields = [key for key in ("process_model", "task_process_isolation") if key in status]
        if not removed_fields:
            skipped += 1
            continue

        old_process_model = status.get("process_model")
        for key in removed_fields:
            del status[key]
        relative_path = status_path.relative_to(data_dir)
        action = "Would remove" if dry_run else "Removed"
        details.append(f"{action} {', '.join(removed_fields)} from {relative_path}")
        if old_process_model in ("legacy", "phase2"):
            details.append(f"{anima_dir.name}: process_model={old_process_model} removed (now phase3)")

        if dry_run:
            changed += 1
            continue
        try:
            atomic_write_text(status_path, json.dumps(status, ensure_ascii=False, indent=2) + "\n")
        except Exception as exc:
            skipped += 1
            error = f"{anima_dir.name}: failed to update status.json: {exc}"
            errors.append(error)
            details.append(error)
            logger.exception("step_remove_process_model_fields failed for %s", status_path)
            continue
        changed += 1

    return StepResult(
        changed=changed,
        skipped=skipped,
        details=details,
        error="; ".join(errors) if errors else None,
    )


def step_update_version(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """No-op step for display; version update is handled by runner."""
    return StepResult(changed=1, skipped=0, details=["migration_state.json"])


# ── Registration ──────────────────────────────────────────────────


def step_phase_b_removal_20260927(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Remove retired daily knowledge-mutation settings and state files."""
    del verbose
    details: list[str] = []
    changed = 0
    skipped = 0
    config_path = data_dir / "config.json"

    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
            if not isinstance(config, dict):
                skipped += 1
                details.append("config.json root is not an object")
            else:
                consolidation = config.get("consolidation")
                if consolidation is None:
                    skipped += 1
                elif not isinstance(consolidation, dict):
                    skipped += 1
                    details.append("config.json consolidation section is not an object")
                else:
                    retired_settings = (
                        "knowledge_mutation_enabled",
                        "ipc_timeout_per_carryover_item_seconds",
                    )
                    removed_settings = [key for key in retired_settings if key in consolidation]
                    if removed_settings:
                        for key in removed_settings:
                            del consolidation[key]
                        changed += 1
                        if dry_run:
                            details.append(f"Would remove {len(removed_settings)} retired consolidation setting(s)")
                        else:
                            atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
                            details.append(f"Removed {len(removed_settings)} retired consolidation setting(s)")
                    else:
                        skipped += 1
        except Exception as exc:
            logger.exception("step_phase_b_removal_20260927 failed while updating config.json")
            return StepResult(changed=0, skipped=skipped, details=details, error=str(exc))
    else:
        skipped += 1
        details.append("config.json not found; skip settings cleanup")

    animas_dir = data_dir / "animas"
    state_files = sorted(
        {
            *animas_dir.glob("*/state/consolidation_phase_b_carryover.json"),
            *animas_dir.glob("*/state/consolidation_phase_b_carryover_*.json"),
        }
    )
    state_files = [path for path in state_files if path.is_file()]
    if state_files:
        changed += len(state_files)
        if dry_run:
            details.append(f"Would remove {len(state_files)} carryover state file(s)")
        else:
            for path in state_files:
                path.unlink()
            details.append(f"Removed {len(state_files)} carryover state file(s)")
    else:
        skipped += 1
        details.append("No carryover state files found")

    return StepResult(changed=changed, skipped=skipped, details=details)


def step_retired_mode_to_a(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Map retired Mode B values to canonical Mode A in config and status files."""
    del verbose
    details: list[str] = []
    changed_files = 0

    def _map_record(record: dict[str, Any]) -> bool:
        changed = False
        for key in ("execution_mode", "resolved_mode"):
            value = record.get(key)
            if isinstance(value, str) and value.strip().lower() in {"b", "basic"}:
                record[key] = "A"
                changed = True

        fallback_models = record.get("fallback_models")
        if isinstance(fallback_models, list):
            for index, fallback in enumerate(fallback_models):
                if not isinstance(fallback, str):
                    continue
                leading = len(fallback) - len(fallback.lstrip())
                value = fallback[leading:]
                if value[:2].lower() == "b:":
                    fallback_models[index] = f"{fallback[:leading]}a:{value[2:]}"
                    changed = True
        return changed

    try:
        config_path = data_dir / "config.json"
        if config_path.is_file():
            config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
            if isinstance(config, dict):
                config_changed = False
                for key in ("anima_defaults", "animas"):
                    section = config.get(key)
                    if isinstance(section, dict):
                        records = section.values() if key == "animas" else (section,)
                        for record in records:
                            if isinstance(record, dict):
                                config_changed = _map_record(record) or config_changed
                model_modes = config.get("model_modes")
                if isinstance(model_modes, dict):
                    for pattern, mode in model_modes.items():
                        if isinstance(mode, str) and mode.strip().lower() in {"b", "basic"}:
                            model_modes[pattern] = "A"
                            config_changed = True
                if config_changed:
                    if dry_run:
                        details.append("Would map retired Mode B values to A in config.json")
                    else:
                        atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
                        details.append("Mapped retired Mode B values to A in config.json")
                    changed_files += 1

        for anima_dir in _iter_anima_dirs(data_dir):
            status_path = anima_dir / "status.json"
            if not status_path.is_file():
                continue
            status = json.loads(status_path.read_text(encoding="utf-8") or "{}")
            if not isinstance(status, dict) or not _map_record(status):
                continue
            if dry_run:
                details.append(f"Would map retired Mode B values to A in {status_path.relative_to(data_dir)}")
            else:
                atomic_write_json(status_path, status, indent=2, ensure_ascii=False)
                details.append(f"Mapped retired Mode B values to A in {status_path.relative_to(data_dir)}")
            changed_files += 1

        if not details:
            details.append("No retired Mode B values found")
        return StepResult(changed=changed_files, skipped=0 if changed_files else 1, details=details)
    except Exception as exc:
        logger.exception("step_retired_mode_to_a failed")
        return StepResult(changed=changed_files, skipped=0, details=details, error=str(exc))


def step_taskboard_metadata_retire(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Retire TaskBoard presentation metadata; tasks are the only board source.

    Backs up the shared DB, transfers ``source_ref`` into canonical task meta,
    reports active-but-archived / orphan WAITING cards, then drops the metadata
    and event tables, and removes the retired housekeeping settings.
    """
    del verbose
    import os
    import sqlite3

    db_path = data_dir / "shared" / "taskboard.sqlite3"
    details: list[str] = []
    if not db_path.is_file():
        return StepResult(changed=0, skipped=1, details=["shared/taskboard.sqlite3 not found; skip"])

    try:
        conn = sqlite3.connect(db_path)
        try:
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='taskboard_metadata'"
            ).fetchone():
                return StepResult(changed=0, skipped=1, details=["taskboard_metadata table not present; skip"])

            rows = conn.execute(
                "SELECT anima_name, task_id, visibility, column, source_ref FROM taskboard_metadata"
            ).fetchall()
            inconsistent: list[str] = []
            orphans = 0
            source_ref_candidates: list[tuple[str, str, str]] = []
            for anima, tid, visibility, column, source_ref in rows:
                canon = conn.execute(
                    "SELECT entry_json FROM tasks WHERE anima=? AND task_id=?", (anima, tid)
                ).fetchone()
                if canon is None:
                    if column == "waiting":
                        alias_exists = conn.execute(
                            "SELECT 1 FROM task_aliases WHERE viewer=? AND alias=?", (anima, tid)
                        ).fetchone()
                        if not alias_exists:
                            orphans += 1
                    continue
                status = json.loads(canon[0]).get("status")
                if visibility in ("expired", "archived", "tombstoned") and status in ("pending", "in_progress"):
                    inconsistent.append(f"{anima}/{tid}")
                existing_ref = json.loads(canon[0]).get("meta", {}).get("source_ref")
                if source_ref and not source_ref.startswith("task_queue:") and not existing_ref:
                    source_ref_candidates.append((anima, tid, source_ref))

            details.append(f"visible-but-archived cards: {len(inconsistent)}")
            details.extend(f"visible-but-archived: {ref}" for ref in inconsistent)
            details.append(f"orphan WAITING cards: {orphans}")
            details.append(f"source_ref transfers: {len(source_ref_candidates)}")

            changed = bool(inconsistent or orphans or source_ref_candidates)
            if dry_run:
                return StepResult(changed=1 if changed else 0, skipped=0, details=details)

            # Pre-backup (no overwrite)
            backups_dir = data_dir / "shared" / "backups"
            backups_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            backup_path = backups_dir / f"taskboard-pre-metadata-retire-{stamp}.sqlite3"
            fd = os.open(backup_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            dest = sqlite3.connect(backup_path)
            try:
                conn.backup(dest)
            finally:
                dest.close()
            details.append(f"backup: {backup_path.name}")

            for anima, tid, source_ref in source_ref_candidates:
                conn.execute(
                    "UPDATE tasks SET entry_json=json_set(entry_json,'$.meta.source_ref',?) "
                    "WHERE anima=? AND task_id=?",
                    (source_ref, anima, tid),
                )

            conn.execute("DROP TABLE taskboard_metadata")
            conn.execute("DROP TABLE taskboard_events")
            conn.commit()

            config_path = data_dir / "config.json"
            if config_path.is_file():
                try:
                    config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
                    hk = config.get("housekeeping") if isinstance(config, dict) else None
                    removed = False
                    if isinstance(hk, dict):
                        for key in (
                            "taskboard_suppressed_retention_days",
                            "taskboard_orphan_metadata_stale_hours",
                        ):
                            if key in hk:
                                del hk[key]
                                removed = True
                    if removed:
                        atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
                        details.append("removed retired housekeeping settings")
                except Exception:
                    logger.warning("Failed to clean retired housekeeping settings", exc_info=True)

            return StepResult(changed=1, skipped=0, details=details)
        finally:
            conn.close()
    except Exception as exc:
        logger.exception("step_taskboard_metadata_retire failed")
        return StepResult(changed=0, skipped=0, details=details, error=str(exc))


def step_neo4j_config_cleanup(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Remove retired Neo4j settings and preserve configured fact edge types."""
    del verbose
    from core.memory._io import atomic_write_text

    details: list[str] = []
    errors: list[str] = []
    changed = 0
    skipped = 0

    config_path = data_dir / "config.json"
    if not config_path.is_file():
        skipped += 1
        details.append("config.json not found; skip")
    else:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
            if not isinstance(config, dict):
                skipped += 1
                details.append("config.json root is not an object")
            else:
                memory = config.get("memory")
                if not isinstance(memory, dict):
                    skipped += 1
                    details.append("config.json memory section is not an object; skip")
                else:
                    config_changed = False
                    old_edge_types = memory.get("neo4j_edge_types")
                    if old_edge_types and "fact_edge_types" not in memory:
                        memory["fact_edge_types"] = old_edge_types
                        config_changed = True
                        action = "Would move" if dry_run else "Moved"
                        details.append(f"{action} memory.neo4j_edge_types to memory.fact_edge_types")
                    for key in ("backend", "neo4j", "neo4j_realtime_ingest", "neo4j_edge_types"):
                        if key in memory:
                            del memory[key]
                            config_changed = True
                            action = "Would remove" if dry_run else "Removed"
                            details.append(f"{action} memory.{key}")
                    if config_changed:
                        changed += 1
                        if not dry_run:
                            atomic_write_text(
                                config_path,
                                json.dumps(config, ensure_ascii=False, indent=2) + "\n",
                            )
                    else:
                        skipped += 1
                        details.append("No retired memory settings found in config.json")
        except Exception as exc:
            errors.append(f"config.json: {exc}")
            details.append(f"config.json: failed to update: {exc}")
            logger.exception("step_neo4j_config_cleanup failed for %s", config_path)

    animas_dir = data_dir / "animas"
    anima_dirs = sorted(path for path in animas_dir.iterdir() if path.is_dir()) if animas_dir.is_dir() else []
    for anima_dir in anima_dirs:
        status_path = anima_dir / "status.json"
        if not status_path.is_file():
            continue
        try:
            status = json.loads(status_path.read_text(encoding="utf-8") or "{}")
            if not isinstance(status, dict):
                skipped += 1
                details.append(f"{anima_dir.name}: status.json root is not an object")
                continue

            legacy_backend = status.get("memory_backend")
            status_changed = False
            old_edge_types = status.get("neo4j_edge_types")
            if old_edge_types and "fact_edge_types" not in status:
                status["fact_edge_types"] = old_edge_types
                status_changed = True
                action = "would move" if dry_run else "moved"
                details.append(f"{anima_dir.name}: {action} neo4j_edge_types to fact_edge_types")
            if "memory_backend" in status:
                del status["memory_backend"]
                status_changed = True
                action = "would remove" if dry_run else "removed"
                details.append(f"{anima_dir.name}: {action} memory_backend")
            if "neo4j_edge_types" in status:
                del status["neo4j_edge_types"]
                status_changed = True
                action = "would remove" if dry_run else "removed"
                details.append(f"{anima_dir.name}: {action} neo4j_edge_types")
            if legacy_backend == "neo4j":
                details.append(f"{anima_dir.name}: Neo4j data is no longer used (legacy RAG continues)")

            if status_changed:
                changed += 1
                if not dry_run:
                    atomic_write_text(
                        status_path,
                        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
                    )
            else:
                skipped += 1
        except Exception as exc:
            error = f"{anima_dir.name}: failed to update status.json: {exc}"
            errors.append(error)
            details.append(error)
            logger.exception("step_neo4j_config_cleanup failed for %s", status_path)

    return StepResult(changed=changed, skipped=skipped, details=details, error="; ".join(errors) if errors else None)


def step_usage_governor_cleanup(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Remove retired Usage Governor config and archive its runtime state."""
    del verbose
    details: list[str] = []
    config_path = data_dir / "config.json"
    config: dict[str, Any] | None = None
    config_changed = False
    skipped = 0

    if config_path.is_file():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return StepResult(
                changed=0, skipped=0, details=["config.json is not valid JSON; skip cleanup"], error=str(exc)
            )
        if not isinstance(loaded, dict):
            return StepResult(
                changed=0, skipped=0, details=["config.json root is not an object"], error="Invalid config root"
            )
        config = loaded
        server = config.get("server")
        if server is not None and not isinstance(server, dict):
            return StepResult(
                changed=0,
                skipped=0,
                details=["config.json server section is not an object"],
                error="Invalid server section",
            )
        if isinstance(server, dict) and "usage_governor" in server:
            del server["usage_governor"]
            config_changed = True
            details.append(
                "Would remove server.usage_governor from config.json"
                if dry_run
                else "Removed server.usage_governor from config.json"
            )
        else:
            skipped += 1
            details.append("No retired Usage Governor setting found")
    else:
        skipped += 1
        details.append("config.json not found; skip settings cleanup")

    retired_files = ("usage_governor_state.json", "usage_policy.json")
    archive_dir = data_dir / "archive" / "retired"
    sources = [data_dir / name for name in retired_files if (data_dir / name).exists()]
    if archive_dir.exists() and not archive_dir.is_dir():
        return StepResult(
            changed=0,
            skipped=skipped,
            details=details + ["archive/retired exists and is not a directory"],
            error="Archive destination is not a directory",
        )
    for source in sources:
        destination = archive_dir / source.name
        if not source.is_file():
            return StepResult(
                changed=0,
                skipped=skipped,
                details=details + [f"{source.name} is not a regular file"],
                error=f"Cannot archive non-file {source}",
            )
        if destination.exists():
            return StepResult(
                changed=0,
                skipped=skipped,
                details=details + [f"Archive target already exists: {destination}"],
                error=f"Archive target already exists: {destination}",
            )
        details.append(
            f"Would archive {source.name} to archive/retired/"
            if dry_run
            else f"Archived {source.name} to archive/retired/"
        )

    missing_files = [name for name in retired_files if not (data_dir / name).exists()]
    skipped += len(missing_files)
    details.extend(f"{name} not found; skip" for name in missing_files)
    if dry_run:
        return StepResult(changed=int(config_changed) + len(sources), skipped=skipped, details=details)

    changed = 0
    try:
        if sources:
            archive_dir.mkdir(parents=True, exist_ok=True)
            for source in sources:
                shutil.move(str(source), str(archive_dir / source.name))
                changed += 1
        if config_changed and config is not None:
            atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
            changed += 1
        return StepResult(changed=changed, skipped=skipped, details=details)
    except Exception as exc:
        logger.exception("step_usage_governor_cleanup failed")
        return StepResult(changed=changed, skipped=skipped, details=details, error=str(exc))


_MEMORY_DEAD_STALE_PROMPTS = ("memory/classification.md",)


def step_memory_dead_prompt_cleanup_20260927(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Remove runtime prompts retired with classify_and_distill."""
    details: list[str] = []
    changed = 0
    skipped = 0
    for name in _MEMORY_DEAD_STALE_PROMPTS:
        stale = data_dir / "prompts" / name
        if not stale.is_file():
            skipped += 1
            continue
        if dry_run:
            details.append(f"Would remove stale prompts/{name}")
        else:
            stale.unlink()
            details.append(f"Removed stale prompts/{name}")
        changed += 1
    return StepResult(changed=changed, skipped=skipped, details=details)


# ── Category 4: Database sync ────────────────────────────────────


def step_retired_config_keys_cleanup(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Remove retired config.json keys that no longer have runtime behavior."""
    del verbose
    config_path = data_dir / "config.json"
    if not config_path.is_file():
        return StepResult(changed=0, skipped=1, details=["config.json not found; skip"])

    try:
        config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
        if not isinstance(config, dict):
            return StepResult(changed=0, skipped=1, details=["config.json root is not an object"])

        retired_keys = {
            "heartbeat": ("orphan_grace_multiplier", "orphan_grace_min_seconds"),
            "background_task": ("max_parallel_llm_tasks",),
            "rag": ("enable_file_watcher",),
            "interaction": ("ttl_days",),
            "system": ("gateway", "worker"),
        }
        removed: list[str] = []
        for section_name, keys in retired_keys.items():
            section = config.get(section_name)
            if not isinstance(section, dict):
                continue
            for key in keys:
                if key in section:
                    del section[key]
                    removed.append(f"{section_name}.{key}")

        if not removed:
            return StepResult(changed=0, skipped=1, details=["No retired config keys found"])

        action = "Would remove" if dry_run else "Removed"
        details = [f"{action} retired config keys: {', '.join(removed)}"]
        if not dry_run:
            atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
        return StepResult(changed=1, skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_retired_config_keys_cleanup failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def step_memory_config_dead_keys_20260927(data_dir: Path, dry_run: bool, verbose: bool) -> StepResult:
    """Drop retired consolidation and RAG configuration keys."""
    del verbose
    config_path = data_dir / "config.json"
    if not config_path.is_file():
        return StepResult(changed=0, skipped=1, details=["config.json not found; skip"])

    try:
        config = json.loads(config_path.read_text(encoding="utf-8") or "{}")
        if not isinstance(config, dict):
            return StepResult(changed=0, skipped=1, details=["config.json root is not an object"])

        retired_keys = (
            ("consolidation", "duplicate_threshold"),
            ("rag", "enable_file_watcher"),
        )
        found: list[tuple[str, str]] = []
        for section_name, key in retired_keys:
            section = config.get(section_name)
            if isinstance(section, dict) and key in section:
                found.append((section_name, key))

        if not found:
            return StepResult(changed=0, skipped=1, details=["No retired memory config keys found"])
        if dry_run:
            details = [f"Would remove {section}.{key}" for section, key in found]
            return StepResult(changed=len(found), skipped=0, details=details)

        for section_name, key in found:
            del config[section_name][key]
        details = [f"Removed {section}.{key}" for section, key in found]
        atomic_write_json(config_path, config, indent=2, ensure_ascii=False)
        return StepResult(changed=len(found), skipped=0, details=details)
    except Exception as exc:
        logger.exception("step_memory_config_dead_keys_20260927 failed")
        return StepResult(changed=0, skipped=0, details=[], error=str(exc))


def register_all_steps(runner: Any) -> None:
    """Register all migration steps in execution order."""
    from core.migrations.template_sync import template_fingerprint
    from core.paths import _get_locale

    try:
        template_sync_id = f"template_sync_{template_fingerprint(_get_locale())}"
    except Exception:
        logger.exception("Could not fingerprint bundled templates; using fallback migration ID")
        template_sync_id = "template_sync_unknown"

    steps = [
        MigrationStep("person_to_anima", "Person → Anima rename", "structural", step_person_to_anima),
        MigrationStep("config_md_to_json", "config.md → config.json", "structural", step_config_md_to_json),
        MigrationStep(
            "model_config_to_status", "Model config → status.json", "structural", step_model_config_to_status
        ),
        MigrationStep("credentials_migration", "Credentials → vault", "structural", step_credentials_migration),
        MigrationStep(
            "vault_reencrypt_20260715",
            "Re-encrypt vault entries with a verified key",
            "structural",
            step_vault_reencrypt,
        ),
        MigrationStep(
            "enable_skill_catalog_router",
            "Enable skill catalog router in config",
            "structural",
            step_enable_skill_catalog_router,
        ),
        MigrationStep("current_task_rename", "current_task → current_state", "per_anima", step_current_task_rename),
        MigrationStep("pending_merge", "Merge pending.md into current_state", "per_anima", step_pending_merge),
        MigrationStep(
            "permissions_migration", "permissions.md → permissions.json", "per_anima", step_permissions_migration
        ),
        MigrationStep("shortterm_layout", "shortterm/session_state → chat/", "per_anima", step_shortterm_layout),
        MigrationStep("cron_format", "cron.md Japanese → cron expressions", "per_anima", step_cron_format),
        MigrationStep("knowledge_frontmatter", "Repair knowledge frontmatter", "per_anima", step_knowledge_frontmatter),
        MigrationStep(
            "trust_state_per_session",
            "Remove shared run/min_trust_seen (now per tool session)",
            "per_anima",
            step_trust_state_per_session,
        ),
        MigrationStep("procedure_frontmatter", "Ensure procedure frontmatter", "per_anima", step_procedure_frontmatter),
        MigrationStep(
            "current_task_references", "Replace current_task refs in config", "per_anima", step_current_task_references
        ),
        MigrationStep("models_json_create", "Create models.json if missing", "template_sync", step_models_json_create),
        MigrationStep(
            "global_permissions_create",
            "Create permissions.global.json if missing",
            "template_sync",
            step_global_permissions_create,
        ),
        MigrationStep(
            template_sync_id,
            "Sync common_knowledge/common_skills/reference and Anima-read prompts from bundled templates",
            "template_sync",
            step_template_sync,
        ),
        MigrationStep(
            "v060_resync",
            "Add cursor/* and gemini/* entries to models.json",
            "template_sync",
            step_models_json_add_cursor_gemini,
        ),
        MigrationStep(
            "grok_models_json",
            "Add Mode X Grok Build models.json entries",
            "template_sync",
            step_grok_models_json,
        ),
        MigrationStep(
            "legacy_flat_skill_migration",
            "Convert legacy flat skills to trusted SKILL.md bundles",
            "structural",
            step_legacy_flat_skill_migration,
        ),
        MigrationStep(
            "knowledge_archive_unify_20260718",
            "Unify memory archive directory names",
            "per_anima",
            step_knowledge_archive_unify,
        ),
        MigrationStep(
            "ragignore_archive_patterns_20260718",
            "Add unified archive patterns to .ragignore",
            "structural",
            step_ragignore_archive_patterns,
        ),
        MigrationStep(
            "split_board_by_company_20260720",
            "Split legacy board into company channels",
            "structural",
            step_split_board_by_company,
        ),
        MigrationStep(
            "channel_company_defaults_20260723",
            "Apply channel_company_defaults to open channels",
            "structural",
            step_channel_company_defaults,
        ),
        MigrationStep(
            "tool_prompts_db_to_md",
            "Write legacy tool prompt DB to Markdown templates",
            "db_sync",
            step_tool_prompts_db_to_md,
        ),
        MigrationStep(
            "v0140_harness_diet_resync",
            "Map retired Mode B models.json entries to Mode A",
            "template_sync",
            step_models_json_mode_b_to_a,
        ),
        MigrationStep(
            "rename_core_tools_to_integrations",
            "Rewrite core.tools references in runtime tools/skills to core.integrations",
            "structural",
            step_rename_core_tools_to_integrations,
        ),
        MigrationStep(
            "engine_timeout_config_cleanup",
            "Remove retired engine timeout settings and rename runner liveness timeout",
            "structural",
            step_engine_timeout_config_cleanup,
        ),
        MigrationStep(
            "memory_maintenance_config_cleanup_20260927",
            "Drop housekeeping.hygiene_grace_days and hygiene first_seen state",
            "structural",
            step_memory_maintenance_config_cleanup_20260927,
        ),
        MigrationStep(
            "priming_config_cleanup_20260927",
            "Drop rag.max_graph_hops",
            "structural",
            step_priming_config_cleanup_20260927,
        ),
        MigrationStep(
            "phase_b_removal_20260927",
            "Drop Phase B knowledge mutation settings and carryover state",
            "structural",
            step_phase_b_removal_20260927,
        ),
        MigrationStep(
            "retired_mode_to_a",
            "Map retired execution mode B to A in config.json and status.json",
            "structural",
            step_retired_mode_to_a,
        ),
        MigrationStep(
            "remove_process_model_fields",
            "Remove retired process_model/task_process_isolation from status.json",
            "per_anima",
            step_remove_process_model_fields,
        ),
        MigrationStep(
            "retire_chain_timeout_keys",
            "Remove retired model keys (max_turns/max_chains/llm_timeout)",
            "structural",
            step_retire_chain_timeout_keys,
        ),
        MigrationStep(
            "rag_vector_worker_config_cleanup",
            "Remove retired RAG vector-worker config without deleting data",
            "structural",
            step_rag_vector_worker_config_cleanup,
        ),
        MigrationStep(
            "taskboard_metadata_retire",
            "Retire TaskBoard presentation metadata (tasks are the only board source)",
            "db_sync",
            step_taskboard_metadata_retire,
        ),
        MigrationStep(
            "neo4j_config_cleanup",
            "Remove retired Neo4j configuration keys",
            "structural",
            step_neo4j_config_cleanup,
        ),
        MigrationStep(
            "usage_governor_cleanup_20260927",
            "Remove Usage Governor state and config",
            "structural",
            step_usage_governor_cleanup,
        ),
        MigrationStep(
            "memory_dead_prompt_cleanup_20260927",
            "Remove runtime prompts retired with classify_and_distill",
            "template_sync",
            step_memory_dead_prompt_cleanup_20260927,
        ),
        MigrationStep(
            "retired_config_keys_cleanup_20260927",
            "Remove retired config.json keys",
            "structural",
            step_retired_config_keys_cleanup,
        ),
        MigrationStep(
            "memory_config_dead_keys_20260927",
            "Drop consolidation.duplicate_threshold and rag.enable_file_watcher",
            "structural",
            step_memory_config_dead_keys_20260927,
        ),
        MigrationStep("update_version", "Update migration_state.json", "version", step_update_version),
    ]
    for s in steps:
        runner.register(s)
