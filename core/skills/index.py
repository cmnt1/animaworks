from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Metadata index over personal skills, common skills, and procedures."""

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.company_resources import get_company_resources
from core.skills.loader import load_skill_metadata
from core.skills.models import SkillMetadata, SkillScanVerdict, SkillSource, SkillTrustLevel

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────

_EXCLUDED_TRUST_LEVELS: frozenset[SkillTrustLevel] = frozenset({SkillTrustLevel.blocked, SkillTrustLevel.quarantine})


@dataclass
class ShadowedSkill:
    """Record of an external skill dropped due to name collision."""

    dropped: SkillMetadata
    kept: SkillMetadata
    reason: str


def _default_external_roots() -> list:
    """Return external skill roots configured in animaworks config."""
    try:
        from core.config.models import load_config

        return list(load_config().skills.external_roots)
    except Exception:
        return []


def _normalize_name_key(name: str) -> str:
    """Normalize a skill name for collision detection."""
    return name.casefold().replace("_", "-")


def _content_sha256(path: Path) -> str:
    """Return the sha256 of a SKILL.md file's content, or '' when unreadable."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


# ── SkillIndex ────────────────────────────────────────────


class SkillIndex:
    """Scan skill and procedure directories and query metadata."""

    def __init__(
        self,
        skills_dir: Path,
        common_skills_dir: Path,
        procedures_dir: Path | None = None,
        *,
        anima_dir: Path | None = None,
        external_roots: list | None = None,
    ) -> None:
        """Initialize index roots.

        Args:
            skills_dir: Directory containing per-Anima skill folders with ``SKILL.md``.
            common_skills_dir: Directory containing shared skill folders (flat or nested).
            procedures_dir: Optional directory of procedure ``*.md`` files; ``None`` skips.
            anima_dir: Optional anima directory for usage stats integration.
            external_roots: Optional list of ``ExternalSkillRoot``. ``None`` reads
                from config (default). List order equals same-name precedence.
        """
        self._skills_dir = skills_dir
        self._common_skills_dir = common_skills_dir
        self._procedures_dir = procedures_dir
        self._anima_dir = anima_dir
        self._external_roots = list(external_roots) if external_roots is not None else _default_external_roots()
        self._enabled_ext: list = []  # list of (ExternalSkillRoot, resolved Path)
        self._external_root_origin: dict[str, int] = {}
        self._cached_index: list[SkillMetadata] | None = None
        self._cached_all_entries: list[SkillMetadata] | None = None
        self._curator_state_marker: tuple | None = None
        self._company_marker: str | None = None
        self.shadowed: list[ShadowedSkill] = []
        self.excluded: dict[str, str] = {}

    def _resolve_enabled_external_roots(self) -> list[tuple]:
        """Return (ExternalSkillRoot, resolved Path) for each enabled external root."""
        resolved: list[tuple] = []
        self._external_root_origin = {}
        self._enabled_ext = []
        for i, root in enumerate(self._external_roots):
            if not getattr(root, "enabled", True):
                continue
            try:
                rdir = Path(os.path.expanduser(root.path)).resolve()
            except OSError:
                continue
            resolved.append((root, rdir))
            self._external_root_origin[str(rdir)] = i
        self._enabled_ext = resolved
        return resolved

    def _denied_external_origins(self) -> list:
        """Return resolved deny roots from permissions.json for this anima (if any)."""
        if self._anima_dir is None:
            return []
        try:
            from core.config.schemas import load_permissions

            return list(load_permissions(self._anima_dir).file_roots_denied)
        except Exception:
            return []

    # ── Cache ───────────────────────────────────────────────

    def invalidate(self) -> None:
        """Drop cached scan results so the next access rebuilds from disk."""
        self._cached_index = None
        self._cached_all_entries = None
        self._curator_state_marker = None
        self._company_marker = None
        self.shadowed = []
        self.excluded = {}

    @property
    def all_skills(self) -> list[SkillMetadata]:
        """All indexed skills after trust filtering (same as :meth:`build_index`)."""
        self._invalidate_if_curator_state_changed()
        if self._cached_index is None:
            self.build_index()
        assert self._cached_index is not None
        return self._cached_index

    # ── Index build ───────────────────────────────────────────

    def build_index(self) -> list[SkillMetadata]:
        """Scan configured directories and return trusted skill metadata.

        Skips files that fail to parse. Omits ``blocked`` and ``quarantine`` trust levels.

        Returns:
            Sorted list: personal skills, then common, then procedures.
        """
        entries: list[SkillMetadata] = []
        seen_paths: set[Path] = set()
        self.shadowed = []
        self.excluded = {}
        curator_state_marker = self._read_curator_state_marker()

        def _add_metadata(meta: SkillMetadata) -> None:
            p = meta.path
            if p is None:
                return
            resolved = p.resolve()
            if resolved in seen_paths:
                return
            seen_paths.add(resolved)
            entries.append(meta)

        if self._skills_dir.exists():
            personal_skill_paths = [
                *sorted(self._skills_dir.glob("*.md")),
                *sorted(self._skills_dir.glob("*/SKILL.md")),
            ]
            for skill_path in personal_skill_paths:
                try:
                    meta = load_skill_metadata(skill_path)
                    meta = meta.model_copy(update={"is_common": False, "is_procedure": False})
                    _add_metadata(meta)
                except Exception as exc:
                    logger.warning(
                        "Failed to load skill metadata from %s: %s",
                        skill_path,
                        exc,
                    )

        if self._common_skills_dir.exists():
            for skill_path in sorted(self._common_skills_dir.glob("*/SKILL.md")):
                try:
                    meta = load_skill_metadata(skill_path)
                    meta = meta.model_copy(update={"is_common": True, "is_procedure": False})
                    _add_metadata(meta)
                except Exception as exc:
                    logger.warning(
                        "Failed to load skill metadata from %s: %s",
                        skill_path,
                        exc,
                    )
            for skill_path in sorted(self._common_skills_dir.glob("*/*/SKILL.md")):
                try:
                    meta = load_skill_metadata(skill_path)
                    meta = meta.model_copy(update={"is_common": True, "is_procedure": False})
                    _add_metadata(meta)
                except Exception as exc:
                    logger.warning(
                        "Failed to load skill metadata from %s: %s",
                        skill_path,
                        exc,
                    )

        company_resources = get_company_resources(self._anima_dir) if self._anima_dir is not None else None
        if company_resources is not None and company_resources.skills_dir.exists():
            for skill_path in sorted(company_resources.skills_dir.glob("*/SKILL.md")):
                try:
                    meta = load_skill_metadata(skill_path)
                    meta = meta.model_copy(update={"is_common": True, "is_procedure": False})
                    _add_metadata(meta)
                except Exception as exc:
                    logger.warning(
                        "Failed to load company skill metadata from %s: %s",
                        skill_path,
                        exc,
                    )

        # ── 5th system: external engine roots (read-only, direct scan) ──────
        denied_roots = self._denied_external_origins()
        for root_obj, root in self._resolve_enabled_external_roots():
            if not root.is_dir():
                continue
            for child in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
                resolved_dir = child.resolve() if child.is_symlink() else child
                origin = str(resolved_dir)
                if denied_roots and any(origin.startswith(str(d)) for d in denied_roots):
                    self.excluded.setdefault(origin, "denied")
                    continue
                skill_path = resolved_dir / "SKILL.md"
                if not skill_path.is_file():
                    continue
                try:
                    meta = load_skill_metadata(skill_path)
                except Exception as exc:
                    logger.warning(
                        "Failed to load external skill metadata from %s: %s",
                        skill_path,
                        exc,
                    )
                    continue
                # No SkillScanner here: external roots are the host user's own
                # skill dirs and their trust_level (default trusted) is the gate.
                # The regex scanner false-positives on ordinary host skills
                # (e.g. a SKILL.md that *forbids* `mkfs`) and costs ~8s/46 skills.
                root_trust = getattr(root_obj, "trust_level", "trusted")
                try:
                    trust = SkillTrustLevel(root_trust)
                except ValueError:
                    trust = SkillTrustLevel.trusted
                meta = meta.model_copy(
                    update={
                        "is_external": True,
                        "is_common": False,
                        "is_procedure": False,
                        "trust_level": trust,
                        "source": SkillSource(
                            type="external",
                            engine=getattr(root_obj, "engine", ""),
                            origin=origin,
                        ),
                        "path": skill_path.resolve(),
                    }
                )
                _add_metadata(meta)

        if self._procedures_dir is not None and self._procedures_dir.exists():
            for proc_path in sorted(self._procedures_dir.glob("*.md")):
                try:
                    meta = load_skill_metadata(proc_path)
                    meta = meta.model_copy(update={"is_procedure": True, "is_common": False})
                    _add_metadata(meta)
                except Exception as exc:
                    logger.warning(
                        "Failed to load skill metadata from %s: %s",
                        proc_path,
                        exc,
                    )

        sorted_all = sorted(entries, key=self._sort_key)
        sorted_all = self._dedup_external(sorted_all)

        # Merge usage stats from SkillUsageTracker if anima_dir is available.
        #
        # Usage frequency policy: ``usage_count`` = view_count + use_count.
        # Currently only ``view`` events are emitted (on read_memory_file).
        # The ``use`` event type is reserved for future Skill-backed Cron
        # (Issue 7) where a cron job explicitly invokes a skill.  Until then,
        # ``view_count + success_count + failure_count`` serves as the
        # effective "how often is this skill actively used?" metric for
        # promotion decisions (Issue 4).
        if self._anima_dir is not None:
            try:
                from core.skills.usage import SkillUsageTracker, usage_ref_from_path

                tracker = SkillUsageTracker(self._anima_dir)
                all_stats = tracker.get_all_stats()
                for i, meta in enumerate(sorted_all):
                    stats = all_stats.get(
                        usage_ref_from_path(
                            meta.path,
                            name=meta.name,
                            is_common=meta.is_common,
                            is_procedure=meta.is_procedure,
                        )
                    ) or all_stats.get(meta.name)
                    if stats:
                        sorted_all[i] = meta.model_copy(
                            update={
                                "usage_count": stats.view_count + stats.use_count,
                                "success_count": stats.success_count,
                                "failure_count": stats.failure_count,
                                "patch_count": stats.patch_count,
                                "last_used_at": (
                                    datetime.fromisoformat(stats.last_used_at) if stats.last_used_at else None
                                ),
                            }
                        )
            except Exception:
                logger.debug("Failed to merge usage stats into index", exc_info=True)

        if self._anima_dir is not None:
            try:
                from core.skills.curator import apply_curator_state, replay_curator_state

                replay = replay_curator_state(self._anima_dir)
                sorted_all = [apply_curator_state(meta, replay) for meta in sorted_all]
            except Exception:
                logger.debug("Failed to merge curator state into index", exc_info=True)

        self._cached_all_entries = sorted_all
        self._curator_state_marker = curator_state_marker
        self._company_marker = company_resources.name if company_resources is not None else None
        filtered = [m for m in sorted_all if self._is_catalog_visible(m)]
        self._cached_index = filtered
        return list(filtered)

    def _external_priority(self, meta: SkillMetadata) -> int:
        """Return the external-root precedence index for *meta* (larger = lower)."""
        origin = (meta.source and meta.source.origin) or (str(meta.path.parent) if meta.path is not None else "")
        if not origin:
            return len(self._enabled_ext)
        for i, (_root_obj, rdir) in enumerate(self._enabled_ext):
            try:
                if Path(origin).is_relative_to(rdir):
                    return i
            except (OSError, ValueError):
                continue
        return len(self._enabled_ext)

    def _dedup_external(self, entries: list[SkillMetadata]) -> list[SkillMetadata]:
        """Resolve name collisions across native and external entries.

        Rules (see plan): native shadows same-key externals; identical external
        copies keep the highest-priority root; differing same-key externals win
        by root priority. Native-vs-native coexistence is unchanged.
        """
        final: list[SkillMetadata] = []
        native_by_key: dict[str, SkillMetadata] = {}
        external_groups: dict[str, list[SkillMetadata]] = {}
        for meta in entries:
            key = _normalize_name_key(meta.name)
            if not meta.is_external:
                native_by_key.setdefault(key, meta)
                final.append(meta)
            else:
                external_groups.setdefault(key, []).append(meta)

        for key, ext_list in external_groups.items():
            native_kept = native_by_key.get(key)
            if native_kept is not None:
                for e in ext_list:
                    self.shadowed.append(ShadowedSkill(dropped=e, kept=native_kept, reason="shadowed_by_native"))
                continue
            ordered = sorted(ext_list, key=self._external_priority)
            kept = ordered[0]
            final.append(kept)
            kept_hash = _content_sha256(kept.path) if kept.path is not None else ""
            for e in ordered[1:]:
                e_hash = _content_sha256(e.path) if e.path is not None else ""
                reason = "duplicate_identical" if e_hash == kept_hash else "shadowed_by_priority"
                self.shadowed.append(ShadowedSkill(dropped=e, kept=kept, reason=reason))

        return sorted(final, key=self._sort_key)

    def _read_curator_state_marker(self) -> tuple | None:
        parts: list[tuple] = []
        if self._anima_dir is not None:
            state_path = self._anima_dir / "state" / "skill_curator.jsonl"
            try:
                stat = state_path.stat()
                parts.append(("anima", stat.st_mtime_ns, stat.st_size))
            except OSError:
                parts.append(("anima", 0, 0))
        for _root_obj, rdir in self._resolve_enabled_external_roots():
            # Root dir mtime only changes on add/remove; also fold in each
            # SKILL.md mtime so in-place edits invalidate the cache (~50 stats).
            try:
                mt = rdir.stat().st_mtime_ns
                for skill_md in rdir.glob("*/SKILL.md"):
                    try:
                        mt = max(mt, skill_md.stat().st_mtime_ns)
                    except OSError:
                        continue
            except OSError:
                mt = 0
            parts.append(("ext", str(rdir), mt))
        return tuple(parts)

    def _invalidate_if_curator_state_changed(self) -> None:
        if self._cached_all_entries is None:
            return
        company_marker: str | None = None
        if self._anima_dir is not None:
            company_resources = get_company_resources(self._anima_dir)
            company_marker = company_resources.name if company_resources is not None else None
        if self._read_curator_state_marker() != self._curator_state_marker or company_marker != self._company_marker:
            self.invalidate()

    @staticmethod
    def _is_catalog_visible(meta: SkillMetadata) -> bool:
        if meta.trust_level in _EXCLUDED_TRUST_LEVELS:
            return False
        if meta.security.verdict == SkillScanVerdict.dangerous:
            return False
        try:
            from core.skills.curator import is_unloadable_lifecycle_state

            return not is_unloadable_lifecycle_state(meta.lifecycle_state)
        except Exception:
            return True

    @staticmethod
    def _sort_key(meta: SkillMetadata) -> tuple[int, str, str]:
        """Personal (0), common (1), external (2), procedures (3); then name, path."""
        if meta.is_procedure:
            tier = 3
        elif meta.is_common:
            tier = 1
        elif meta.is_external:
            tier = 2
        else:
            tier = 0
        path_s = str(meta.path) if meta.path is not None else ""
        return (tier, meta.name.casefold(), path_s)

    # ── Reference Resolution ───────────────────────────────────

    def resolve_skill_reference(self, ref: str) -> SkillMetadata | None:
        """Resolve a cron skill reference to metadata.

        Supported refs are exact skill/procedure names and safe ``SKILL.md``
        pointers under ``skills/``, ``common_skills/``, or the assigned
        ``companies/<name>/skills/`` root.  Name matches use the index order,
        so personal skills win over shared skills, which win over procedures.
        """
        value = str(ref).strip()
        if not self._is_safe_reference(value):
            return None

        entries = self.search("", include_blocked=True)
        pointer_path = self._path_from_pointer(value)
        if pointer_path is not None:
            existing = self._entry_for_path(entries, pointer_path)
            if existing is not None:
                return existing
            if not pointer_path.is_file():
                return None
            try:
                meta = load_skill_metadata(pointer_path)
            except Exception as exc:
                logger.warning("Failed to load skill reference metadata from %s: %s", pointer_path, exc)
                return None
            return meta.model_copy(
                update={
                    "is_common": self._is_shared_skill_path(pointer_path),
                    "is_procedure": False,
                }
            )

        matches = [
            meta for meta in entries if meta.name == value or (meta.path is not None and meta.path.parent.name == value)
        ]
        if len(matches) > 1:
            logger.warning(
                "Multiple skill references matched %r; using %s by deterministic priority",
                value,
                matches[0].path,
            )
        return matches[0] if matches else None

    @staticmethod
    def _is_safe_reference(ref: str) -> bool:
        if not ref or "\\" in ref:
            return False
        path = Path(ref)
        if path.is_absolute() or ".." in path.parts:
            return False
        if ref.startswith("external/"):
            return len(path.parts) == 4 and path.name == "SKILL.md" and not path.parts[2].startswith(".")
        if ref.startswith(("skills/", "common_skills/", "companies/")):
            return len(path.parts) >= 3 and path.name == "SKILL.md"
        return "/" not in ref

    def _path_from_pointer(self, ref: str) -> Path | None:
        path = Path(ref)
        if ref.startswith("skills/"):
            return self._safe_child_path(self._skills_dir.parent, path)
        if ref.startswith("common_skills/"):
            return self._safe_child_path(self._common_skills_dir.parent, path)
        if ref.startswith("companies/") and self._anima_dir is not None:
            resources = get_company_resources(self._anima_dir)
            if resources is None:
                return None
            expected_prefix = ("companies", resources.name, "skills")
            if path.parts[:3] != expected_prefix:
                return None
            return self._safe_child_path(resources.root.parent.parent, path)
        if ref.startswith("external/"):
            # external/<engine>/<name>/SKILL.md -> <root>/<name>/SKILL.md (symlink resolved)
            _engine, name = path.parts[1], path.parts[2]
            for root_obj, rdir in self._resolve_enabled_external_roots():
                if getattr(root_obj, "engine", "") != _engine:
                    continue
                candidate = (rdir / name).resolve(strict=False) / "SKILL.md"
                return candidate if candidate.is_file() else None
            return None
        return None

    @staticmethod
    def _safe_child_path(root: Path, relative: Path) -> Path | None:
        if relative.name != "SKILL.md" or ".." in relative.parts:
            return None
        try:
            root_resolved = root.resolve(strict=False)
            candidate = (root / relative).resolve(strict=False)
            candidate.relative_to(root_resolved)
            return candidate
        except (OSError, ValueError):
            return None

    @staticmethod
    def _entry_for_path(entries: list[SkillMetadata], path: Path) -> SkillMetadata | None:
        try:
            resolved = path.resolve(strict=False)
        except OSError:
            return None
        for meta in entries:
            if meta.path is None:
                continue
            try:
                if meta.path.resolve(strict=False) == resolved:
                    return meta
            except OSError:
                continue
        return None

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve(strict=False).relative_to(root.resolve(strict=False))
            return True
        except (OSError, ValueError):
            return False

    def _is_shared_skill_path(self, path: Path) -> bool:
        if self._is_under(path, self._common_skills_dir):
            return True
        if self._anima_dir is None:
            return False
        resources = get_company_resources(self._anima_dir)
        return resources is not None and self._is_under(path, resources.skills_dir)

    # ── Search ────────────────────────────────────────────────

    def search(self, query: str, *, include_blocked: bool = False) -> list[SkillMetadata]:
        """Return metadata entries matching *query* as a case-insensitive substring.

        Matches against ``name``, ``description``, and ``category`` (when set).

        Args:
            query: Substring to match.
            include_blocked: When ``False``, exclude ``blocked`` / ``quarantine`` entries.

        Returns:
            Filtered list in personal → common → procedure order.
        """
        self._invalidate_if_curator_state_changed()
        if self._cached_all_entries is None:
            self.build_index()
        assert self._cached_all_entries is not None
        base = self._cached_all_entries if include_blocked else self.all_skills
        if not query:
            return list(base)
        q = query.casefold()

        def _matches(meta: SkillMetadata) -> bool:
            cat = meta.category
            return (
                q in meta.name.casefold()
                or q in meta.description.casefold()
                or (cat is not None and q in cat.casefold())
            )

        return [m for m in base if _matches(m)]
