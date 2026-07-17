from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Reference rewrites for merged memory and undelivered inbox messages."""

import json
from pathlib import Path
from typing import Any

from core.memory._io import atomic_write_text
from core.memory.facts import FactRecord


def _json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _message_for_destination(
    payload: dict[str, Any],
    *,
    source: str,
    target: str,
    destination_stem: str,
    id_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    rewritten = dict(payload)
    if rewritten.get("to_person") == source:
        rewritten["to_person"] = target
    if rewritten.get("to") == source:
        rewritten["to"] = target
    original_id = rewritten.get("id")
    if isinstance(original_id, str) and original_id != destination_stem:
        rewritten["id"] = destination_stem
    for key in ("thread_id", "reply_to"):
        value = rewritten.get(key)
        if isinstance(value, str):
            if id_mapping and value in id_mapping:
                rewritten[key] = id_mapping[value]
            elif isinstance(original_id, str) and value == original_id:
                rewritten[key] = destination_stem
    return rewritten


def plan_inbox(data_dir: Path, source: str, target: str) -> dict[str, Any]:
    """Build a non-secret, deterministic inbox move plan without writing."""
    source_dir = Path(data_dir) / "shared" / "inbox" / source
    target_dir = Path(data_dir) / "shared" / "inbox" / target
    entries: list[dict[str, str]] = []
    id_mapping: dict[str, str] = {}
    if not source_dir.is_dir():
        return {"entries": entries, "message_id_mapping": id_mapping}

    for source_path in sorted(source_dir.glob("*.json")):
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid inbox message {source_path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Expected a JSON object in inbox message {source_path}")

        original_id = str(payload.get("id", source_path.stem))
        candidate = target_dir / source_path.name
        index = 1
        while True:
            preliminary = _message_for_destination(
                payload,
                source=source,
                target=target,
                destination_stem=candidate.stem,
            )
            if not candidate.exists():
                break
            if candidate.is_file() and candidate.read_text(encoding="utf-8") == _json_text(preliminary):
                break
            index += 1
            suffix = f"__from_{source}" if index == 2 else f"__from_{source}_{index}"
            candidate = target_dir / f"{source_path.stem}{suffix}{source_path.suffix}"
        entries.append({"source_name": source_path.name, "target_name": candidate.name})
        if original_id != candidate.stem:
            if original_id in id_mapping and id_mapping[original_id] != candidate.stem:
                raise ValueError(f"Duplicate inbox message ID requires two targets: {original_id}")
            id_mapping[original_id] = candidate.stem
    return {"entries": entries, "message_id_mapping": id_mapping}


def rewrite_inbox(
    data_dir: Path,
    source: str,
    target: str,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a journaled move plan for unprocessed source inbox JSON files.

    Processed/expired/quarantine subdirectories are intentionally left alone.
    All transformed target files are durable before any source file is removed.
    """
    source_dir = Path(data_dir) / "shared" / "inbox" / source
    target_dir = Path(data_dir) / "shared" / "inbox" / target
    target_dir.mkdir(parents=True, exist_ok=True)
    plan = plan or plan_inbox(data_dir, source, target)
    entries = plan.get("entries", [])
    id_mapping = plan.get("message_id_mapping", {})
    if not isinstance(entries, list) or not isinstance(id_mapping, dict):
        raise ValueError("Invalid journaled inbox move plan")
    moved: list[dict[str, str]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid inbox move plan entry")
        source_path = source_dir / str(entry.get("source_name", ""))
        destination = target_dir / str(entry.get("target_name", ""))
        if source_path.parent != source_dir or destination.parent != target_dir:
            raise ValueError("Inbox move plan contains an unsafe path")
        if not source_path.is_file():
            if destination.is_file():
                moved.append(
                    {
                        "source": f"shared/inbox/{source}/{source_path.name}",
                        "target": f"shared/inbox/{target}/{destination.name}",
                    }
                )
                continue
            raise ValueError(f"Inbox move source and target are both missing: {source_path}")
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid inbox message {source_path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Expected a JSON object in inbox message {source_path}")

        rewritten = _message_for_destination(
            payload,
            source=source,
            target=target,
            destination_stem=destination.stem,
            id_mapping={str(key): str(value) for key, value in id_mapping.items()},
        )
        content = _json_text(rewritten)
        if destination.exists() and destination.read_text(encoding="utf-8") != content:
            raise ValueError(f"Conflicting target inbox message: {destination}")
        if not destination.exists():
            atomic_write_text(destination, content)
        moved.append(
            {
                "source": f"shared/inbox/{source}/{source_path.name}",
                "target": f"shared/inbox/{target}/{destination.name}",
            }
        )

    for entry in entries:
        source_path = source_dir / str(entry["source_name"])
        source_path.unlink(missing_ok=True)

    return {
        "messages_moved": len(entries),
        "message_mapping": moved,
        "message_id_mapping": dict(sorted((str(key), str(value)) for key, value in id_mapping.items())),
    }


def _rewrite_task_ids(value: Any, mapping: dict[str, str], *, key: str = "") -> tuple[Any, int]:
    if isinstance(value, dict):
        changed = 0
        result: dict[str, Any] = {}
        for child_key, child in value.items():
            result[child_key], count = _rewrite_task_ids(child, mapping, key=child_key)
            changed += count
        return result, changed
    if isinstance(value, list):
        changed = 0
        result: list[Any] = []
        for child in value:
            if key == "depends_on" and isinstance(child, str) and child in mapping:
                result.append(mapping[child])
                changed += int(mapping[child] != child)
                continue
            rewritten, count = _rewrite_task_ids(child, mapping, key=key)
            result.append(rewritten)
            changed += count
        return result, changed
    if isinstance(value, str) and key in {
        "task_id",
        "delegated_task_id",
        "tracking_task_id",
        "replaced_by",
    }:
        mapped = mapping.get(value, value)
        return mapped, int(mapped != value)
    return value, 0


def rewrite_inbox_task_references(
    data_dir: Path,
    target: str,
    message_mapping: list[dict[str, str]],
    task_id_mapping: dict[str, str],
) -> dict[str, Any]:
    """Apply source-owned task IDs to structured metadata in moved messages."""
    data_dir = Path(data_dir).resolve()
    expected_root = (data_dir / "shared" / "inbox" / target).resolve()
    updated: list[str] = []
    replacements = 0
    for item in message_mapping:
        relative = item.get("target") if isinstance(item, dict) else None
        if not isinstance(relative, str):
            raise ValueError("Invalid moved inbox message mapping")
        path = (data_dir / relative).resolve()
        if not path.is_relative_to(expected_root) or path.parent != expected_root:
            raise ValueError(f"Unsafe moved inbox message path: {relative}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid moved inbox message {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Expected a JSON object in moved inbox message {path}")
        if payload.get("intent") != "delegation":
            continue
        rewritten, count = _rewrite_task_ids(payload, task_id_mapping)
        if count:
            atomic_write_text(path, _json_text(rewritten))
            updated.append(path.relative_to(data_dir).as_posix())
            replacements += count
    return {"message_files_updated": updated, "task_id_replacements": replacements}


def _reference_replacements(
    source: str,
    target: str,
    mappings: dict[str, str],
    *,
    qualified_only: bool = False,
) -> list[tuple[str, str]]:
    replacements: dict[str, str] = {}
    for old, new in mappings.items():
        if not qualified_only and old != new:
            replacements[old] = new
        replacements[f"animas/{source}/{old}"] = f"animas/{target}/{new}"
        replacements[f"/api/animas/{source}/{old}"] = f"/api/animas/{target}/{new}"
    return sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)


def _replace_text(text: str, replacements: list[tuple[str, str]]) -> tuple[str, int]:
    count = 0
    for old, new in replacements:
        occurrences = text.count(old)
        if occurrences:
            text = text.replace(old, new)
            count += occurrences
    return text, count


def _rewrite_markdown(
    target_dir: Path,
    replacements: list[tuple[str, str]],
    source_documents: set[str] | None,
) -> tuple[list[str], int]:
    changed: list[str] = []
    replacements_applied = 0
    for category in ("episodes", "knowledge"):
        root = target_dir / category
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            relative = path.relative_to(target_dir).as_posix()
            if source_documents is not None and relative not in source_documents:
                continue
            original = path.read_text(encoding="utf-8")
            rewritten, count = _replace_text(original, replacements)
            if rewritten != original:
                atomic_write_text(path, rewritten)
                changed.append(relative)
                replacements_applied += count
    return changed, replacements_applied


def _rewrite_facts(
    target_dir: Path,
    episode_mapping: dict[str, str],
    fact_ids_to_rewrite: set[str],
) -> tuple[list[str], int]:
    changed: list[str] = []
    replacements_applied = 0
    facts_dir = target_dir / "facts"
    if not facts_dir.is_dir():
        return changed, replacements_applied

    for path in sorted(facts_dir.glob("*.jsonl")):
        records: list[FactRecord] = []
        file_changed = False
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = FactRecord.from_json_line(line)
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                raise ValueError(f"Invalid FactRecord in {path}:{line_no}: {exc}") from exc
            if record.fact_id not in fact_ids_to_rewrite:
                records.append(record)
                continue
            mapped = episode_mapping.get(record.source_episode)
            if mapped is None:
                prefixed = f"episodes/{record.source_episode}"
                if prefixed in episode_mapping:
                    mapped = episode_mapping[prefixed].removeprefix("episodes/")
            if mapped is not None and mapped != record.source_episode:
                data = record.to_dict()
                data["source_episode"] = mapped
                record = FactRecord.from_dict(data)
                file_changed = True
                replacements_applied += 1
            records.append(record)
        if file_changed:
            content = "\n".join(record.to_json_line() for record in records)
            atomic_write_text(path, content + ("\n" if content else ""))
            changed.append(path.relative_to(target_dir).as_posix())
    return changed, replacements_applied


def rewrite_memory_references(
    target_dir: Path,
    *,
    source: str,
    target: str,
    file_mapping: dict[str, str],
    episode_mapping: dict[str, str],
    attachment_mapping: dict[str, str],
    fact_ids_to_rewrite: list[str],
) -> dict[str, Any]:
    """Apply Phase 1-2 mappings to target Markdown and parsed facts."""
    combined = {**file_mapping, **attachment_mapping}
    source_replacements = _reference_replacements(source, target, combined)
    qualified_replacements = _reference_replacements(
        source,
        target,
        combined,
        qualified_only=True,
    )
    source_documents = {
        destination for destination in file_mapping.values() if destination.startswith(("episodes/", "knowledge/"))
    }
    qualified_files, qualified_count = _rewrite_markdown(
        Path(target_dir),
        qualified_replacements,
        None,
    )
    source_files, source_count = _rewrite_markdown(
        Path(target_dir),
        source_replacements,
        source_documents,
    )
    markdown_files = sorted(set(qualified_files) | set(source_files))
    markdown_count = qualified_count + source_count
    fact_files, fact_count = _rewrite_facts(
        Path(target_dir),
        episode_mapping,
        set(fact_ids_to_rewrite),
    )

    dangling: list[dict[str, str]] = []
    old_values = [old for old, new in combined.items() if old != new]
    qualified_old_values = [old for old, _new in qualified_replacements]
    for category in ("episodes", "knowledge"):
        root = Path(target_dir) / category
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            relative = path.relative_to(target_dir).as_posix()
            text = path.read_text(encoding="utf-8")
            values_to_check = qualified_old_values + (old_values if relative in source_documents else [])
            for old in values_to_check:
                if old in text:
                    dangling.append({"path": relative, "reference": old})
    if dangling:
        details = ", ".join(f"{item['path']}:{item['reference']}" for item in dangling)
        raise ValueError(f"Dangling merged memory references remain: {details}")

    return {
        "markdown_files_updated": markdown_files,
        "markdown_replacements": markdown_count,
        "fact_files_updated": fact_files,
        "fact_replacements": fact_count,
        "dangling_references": 0,
    }
