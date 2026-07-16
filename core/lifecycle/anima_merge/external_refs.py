from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Rewrite references outside the two Anima memory directories.

This module deliberately works on raw JSON objects.  In addition to preserving
configuration keys unknown to the current Pydantic schema, doing so ensures
that credential values are never included in the returned journal artifacts.
"""

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config.anima_registry import read_anima_supervisor
from core.memory._io import atomic_write_text
from core.platform.locks import file_lock

from .credential_refs import discover_slack_credential_candidates


class ReferenceRewriteError(RuntimeError):
    """Raised when external references cannot be rewritten safely."""


@dataclass(frozen=True)
class OrganizationRewritePlan:
    """Validated organization graph and the status files requiring updates."""

    relationships: dict[str, str | None]
    status_updates: tuple[Path, ...]


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceRewriteError(f"Invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReferenceRewriteError(f"Expected a JSON object in {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def _replace_name(value: Any, source: str, target: str) -> tuple[Any, int]:
    if value == source:
        return target, 1
    return value, 0


def _replace_list(values: Any, source: str, target: str) -> tuple[Any, int]:
    """Replace an Anima name and stable-deduplicate a list.

    Non-list values are left untouched so an unrelated malformed optional
    section is not silently normalized by a merge.
    """

    if not isinstance(values, list):
        return values, 0
    result: list[Any] = []
    seen: set[str] = set()
    changed = 0
    for item in values:
        mapped = target if item == source else item
        if mapped != item:
            changed += 1
        if isinstance(mapped, str):
            if mapped in seen:
                changed += 1
                continue
            seen.add(mapped)
        result.append(mapped)
    return result, changed


def _cycles(relationships: dict[str, str | None]) -> list[tuple[str, ...]]:
    cycles: list[tuple[str, ...]] = []
    visited: set[str] = set()
    for start in relationships:
        if start in visited:
            continue
        path: list[str] = []
        in_path: set[str] = set()
        current: str | None = start
        while current is not None and current not in visited:
            if current in in_path:
                cycles.append(tuple(path[path.index(current) :]))
                break
            path.append(current)
            in_path.add(current)
            current = relationships.get(current)
        visited.update(in_path)
    return cycles


def _canonical_cycle(cycle: tuple[str, ...]) -> tuple[str, ...]:
    if not cycle:
        return cycle
    rotations = [cycle[index:] + cycle[:index] for index in range(len(cycle))]
    return min(rotations)


class ExternalRefsRewriter:
    """Idempotently rewrite source-Anima references outside canonical memory."""

    def __init__(self, data_dir: Path, source: str, target: str) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.source = source
        self.target = target
        self.animas_dir = self.data_dir / "animas"
        self.source_dir = self.animas_dir / source

    # ── Organization ──────────────────────────────────────────

    def plan_organization(self) -> OrganizationRewritePlan:
        """Build and validate the post-rewrite supervisor graph without writing."""

        relationships: dict[str, str | None] = {}
        status_updates: list[Path] = []
        changed_names: set[str] = set()

        if self.animas_dir.is_dir():
            for anima_dir in sorted(self.animas_dir.iterdir()):
                if not anima_dir.is_dir():
                    continue
                name = anima_dir.name
                supervisor = read_anima_supervisor(anima_dir)
                relationships[name] = supervisor
                if name != self.source and supervisor == self.source:
                    relationships[name] = self.target
                    status_updates.append(anima_dir / "status.json")
                    changed_names.add(name)

        errors: list[str] = []
        if relationships.get(self.target) == self.target:
            errors.append(f"self-reference: {self.target} -> {self.target}")

        current_relationships = {
            name: read_anima_supervisor(self.animas_dir / name)
            for name in relationships
        }
        old_cycles = {_canonical_cycle(item) for item in _cycles(current_relationships)}
        for cycle in _cycles(relationships):
            canonical = _canonical_cycle(cycle)
            if canonical in old_cycles or not (set(cycle) & changed_names):
                continue
            errors.append("cycle: " + " -> ".join((*cycle, cycle[0])))

        if errors:
            details = "\n- ".join(errors)
            raise ReferenceRewriteError(
                "Organization rewrite requires human resolution:\n- " + details
            )
        return OrganizationRewritePlan(
            relationships=relationships,
            status_updates=tuple(status_updates),
        )

    def rewrite_organization(
        self,
        plan: OrganizationRewritePlan | None = None,
    ) -> dict[str, Any]:
        """Write validated status changes first, then synchronize raw config."""

        plan = plan or self.plan_organization()
        changed_files: list[str] = []
        statuses_updated = 0

        for status_path in plan.status_updates:
            # The source Anima directory is immutable during REWRITE_REFS.
            if status_path.parent.resolve() == self.source_dir:
                continue
            status = _read_json_object(status_path) if status_path.is_file() else {}
            if status.get("supervisor") == self.target:
                continue
            status["supervisor"] = self.target
            _write_json(status_path, status)
            statuses_updated += 1
            changed_files.append(self._relative(status_path))

        # status.json is the SSoT.  This write intentionally happens only
        # after every status update has succeeded.
        config_path = self.data_dir / "config.json"
        config_updated = False
        if config_path.is_file():
            config = _read_json_object(config_path)
            animas = config.get("animas")
            if not isinstance(animas, dict):
                animas = {}
                config["animas"] = animas
            for name, supervisor in plan.relationships.items():
                if name == self.source or supervisor is None:
                    continue
                entry = animas.get(name)
                if not isinstance(entry, dict):
                    entry = {}
                    animas[name] = entry
                if entry.get("supervisor") != supervisor:
                    entry["supervisor"] = supervisor
                    config_updated = True
            if config_updated:
                _write_json(config_path, config)
                changed_files.append(self._relative(config_path))

        return {
            "supervisor_statuses_updated": statuses_updated,
            "config_synchronized": config_updated,
            "changed_files": changed_files,
        }

    # ── External messaging, ACLs, and meetings ───────────────

    def rewrite_messaging(self) -> dict[str, Any]:
        """Rewrite routing mappings while preserving historical attribution."""

        changed_files: list[str] = []
        replacements = 0

        config_path = self.data_dir / "config.json"
        if config_path.is_file():
            config = _read_json_object(config_path)
            changed = 0
            external = config.get("external_messaging")
            if isinstance(external, dict):
                for platform in ("slack", "chatwork", "discord"):
                    channel = external.get(platform)
                    if not isinstance(channel, dict):
                        continue
                    for mapping_name in ("anima_mapping", "app_id_mapping"):
                        mapping = channel.get(mapping_name)
                        if not isinstance(mapping, dict):
                            continue
                        for key, value in list(mapping.items()):
                            mapping[key], count = _replace_name(value, self.source, self.target)
                            changed += count
                    if "default_anima" in channel:
                        channel["default_anima"], count = _replace_name(
                            channel["default_anima"], self.source, self.target
                        )
                        changed += count
                    if platform == "discord":
                        members = channel.get("channel_members")
                        if isinstance(members, dict):
                            for key, values in list(members.items()):
                                members[key], count = _replace_list(values, self.source, self.target)
                                changed += count

                zoom = external.get("zoom")
                if isinstance(zoom, dict):
                    if "default_anima" in zoom:
                        zoom["default_anima"], count = _replace_name(
                            zoom["default_anima"], self.source, self.target
                        )
                        changed += count
                    meetings = zoom.get("meeting_mapping")
                    if isinstance(meetings, dict):
                        for key, value in list(meetings.items()):
                            meetings[key], count = _replace_name(value, self.source, self.target)
                            changed += count

            github = config.get("github_webhook")
            if isinstance(github, dict):
                for key in ("reviewer_anima", "dispatcher_anima"):
                    if key not in github:
                        continue
                    github[key], count = _replace_name(github[key], self.source, self.target)
                    changed += count

            if changed:
                _write_json(config_path, config)
                changed_files.append(self._relative(config_path))
                replacements += changed

        channel_files_updated = 0
        channels_dir = self.data_dir / "shared" / "channels"
        if channels_dir.is_dir():
            for path in sorted(channels_dir.glob("*.meta.json")):
                data = _read_json_object(path)
                if "members" not in data:
                    continue
                data["members"], changed = _replace_list(
                    data["members"], self.source, self.target
                )
                if not changed:
                    continue
                _write_json(path, data)
                channel_files_updated += 1
                replacements += changed
                changed_files.append(self._relative(path))

        meeting_files_updated = 0
        meetings_dir = self.data_dir / "shared" / "meetings"
        if meetings_dir.is_dir():
            for path in sorted(meetings_dir.glob("*.json")):
                data = _read_json_object(path)
                if data.get("closed", False):
                    continue
                changed = 0
                if "participants" in data:
                    data["participants"], count = _replace_list(
                        data["participants"], self.source, self.target
                    )
                    changed += count
                if "chair" in data:
                    data["chair"], count = _replace_name(
                        data["chair"], self.source, self.target
                    )
                    changed += count
                if not changed:
                    continue
                _write_json(path, data)
                meeting_files_updated += 1
                replacements += changed
                changed_files.append(self._relative(path))

        return {
            "replacements": replacements,
            "channel_acl_files_updated": channel_files_updated,
            "open_meeting_files_updated": meeting_files_updated,
            "changed_files": changed_files,
        }

    def discover_credential_candidates(self) -> list[dict[str, str]]:
        """Return source Slack credential key names, never credential values."""
        try:
            return discover_slack_credential_candidates(self.data_dir, self.source)
        except ValueError as exc:
            raise ReferenceRewriteError(str(exc)) from exc

    # ── Ancillary state ──────────────────────────────────────

    def rewrite_ancillary_state(self, *, wake_target: bool = False) -> dict[str, Any]:
        """Rewrite ephemeral routing/state and remove stale source run files."""

        changed_files: list[str] = []
        notification_updates = self._rewrite_notification_map(
            self.data_dir / "run" / "notification_map.json"
        )
        if notification_updates:
            changed_files.append("run/notification_map.json")

        discord_updates = self._rewrite_entry_anima_map(
            self.data_dir / "run" / "discord_thread_map.json"
        )
        if discord_updates:
            changed_files.append("run/discord_thread_map.json")

        usage_updated = False
        usage_path = self.data_dir / "usage_governor_state.json"
        if usage_path.is_file():
            usage = _read_json_object(usage_path)
            suspended, changed = _replace_list(
                usage.get("suspended_animas"), self.source, self.target
            )
            if changed:
                usage["suspended_animas"] = suspended
                _write_json(usage_path, usage)
                usage_updated = True
                changed_files.append(self._relative(usage_path))

        bootstrap_removed = False
        bootstrap_path = self.animas_dir / ".bootstrap_retries.json"
        if bootstrap_path.is_file():
            retries = _read_json_object(bootstrap_path)
            if self.source in retries:
                del retries[self.source]
                _write_json(bootstrap_path, retries)
                bootstrap_removed = True
                changed_files.append(self._relative(bootstrap_path))

        removed_run_paths: list[str] = []
        source_wake = self.data_dir / "run" / "inbox_wake" / self.source
        source_wake_existed = source_wake.exists()
        self._remove_path(source_wake, removed_run_paths)
        self._remove_path(
            self.data_dir / "run" / "events" / self.source,
            removed_run_paths,
        )
        for path in (
            self.data_dir / "run" / "sockets" / f"{self.source}.sock",
            self.data_dir / "run" / "animas" / f"{self.source}.pid",
            self.data_dir / "run" / "animas" / f"{self.source}.lock",
        ):
            self._remove_path(path, removed_run_paths)

        target_wake_created = False
        target_wake = self.data_dir / "run" / "inbox_wake" / self.target
        if (wake_target or source_wake_existed) and not target_wake.exists():
            atomic_write_text(target_wake, "")
            target_wake_created = True
            changed_files.append(self._relative(target_wake))

        changed_files.extend(removed_run_paths)
        return {
            "notification_mappings_updated": notification_updates,
            "discord_mappings_updated": discord_updates,
            "usage_state_updated": usage_updated,
            "bootstrap_retry_removed": bootstrap_removed,
            "removed_run_paths": removed_run_paths,
            "target_wake_created": target_wake_created,
            "changed_files": changed_files,
        }

    def _rewrite_entry_anima_map(self, path: Path) -> int:
        if not path.is_file():
            return 0
        data = _read_json_object(path)
        changed = 0
        for entry in data.values():
            if not isinstance(entry, dict) or entry.get("anima") != self.source:
                continue
            entry["anima"] = self.target
            changed += 1
        if changed:
            _write_json(path, data)
        return changed

    def _rewrite_notification_map(self, path: Path) -> int:
        """Use the same advisory lock as notification writers."""
        if not path.is_file():
            return 0
        try:
            with path.open("r+", encoding="utf-8") as handle, file_lock(handle, exclusive=True):
                data = json.load(handle)
                if not isinstance(data, dict):
                    raise ReferenceRewriteError(f"Expected a JSON object in {path}")
                changed = 0
                for entry in data.values():
                    if isinstance(entry, dict) and entry.get("anima") == self.source:
                        entry["anima"] = self.target
                        changed += 1
                if changed:
                    handle.seek(0)
                    handle.truncate()
                    json.dump(data, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                return changed
        except (OSError, json.JSONDecodeError) as exc:
            raise ReferenceRewriteError(f"Invalid notification mapping {path}: {exc}") from exc

    def _remove_path(self, path: Path, removed: list[str]) -> None:
        if not path.exists() and not path.is_symlink():
            return
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        removed.append(self._relative(path))

    def _relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.data_dir).as_posix()
        except ValueError:
            return str(path)


__all__ = [
    "ExternalRefsRewriter",
    "OrganizationRewritePlan",
    "ReferenceRewriteError",
]
