"""Operational helpers for ``animaworks memory`` CLI commands."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FIND_EPISODES_BY_SOURCE_PREFIX = """
MATCH (ep:Episode)
WHERE ep.group_id = $group_id
  AND ep.deleted_at IS NULL
  AND ep.source STARTS WITH $prefix
RETURN ep.uuid AS uuid
ORDER BY ep.created_at
"""

_FIND_ORPHAN_ENTITIES_AFTER_EPISODE_CLEANUP = """
MATCH (e:Entity)
WHERE e.group_id = $group_id
  AND e.deleted_at IS NULL
  AND EXISTS {
    MATCH (ep:Episode)-[:MENTIONS]->(e)
    WHERE ep.group_id = $group_id AND ep.uuid IN $episode_uuids
  }
  AND NOT EXISTS {
    MATCH (ep:Episode)-[:MENTIONS]->(e)
    WHERE ep.group_id = $group_id
      AND ep.deleted_at IS NULL
      AND NOT (ep.uuid IN $episode_uuids)
  }
  AND NOT EXISTS { MATCH (e)-[:RELATES_TO]-() }
RETURN e.uuid AS uuid
ORDER BY e.uuid
"""

_SOFT_DELETE_EPISODES_BY_UUIDS = """
MATCH (ep:Episode)
WHERE ep.group_id = $group_id AND ep.uuid IN $episode_uuids
SET ep.deleted_at = datetime($deleted_at)
WITH ep
OPTIONAL MATCH (ep)-[m:MENTIONS]->(:Entity)
DELETE m
"""

_SOFT_DELETE_ENTITIES_BY_UUIDS = """
MATCH (e:Entity)
WHERE e.group_id = $group_id AND e.uuid IN $entity_uuids
SET e.deleted_at = datetime($deleted_at)
"""


def public_neo4j_config(memory_cfg: object | None) -> dict[str, str]:
    neo4j_cfg = getattr(memory_cfg, "neo4j", None)
    return {
        "uri": str(getattr(neo4j_cfg, "uri", "bolt://localhost:7687")),
        "database": str(getattr(neo4j_cfg, "database", "neo4j")),
    }


def iter_anima_dirs(animas_dir: Path) -> list[Path]:
    if not animas_dir.is_dir():
        return []
    return sorted(
        (path for path in animas_dir.iterdir() if path.is_dir() and not path.name.startswith(".")),
        key=lambda path: path.name,
    )


def collect_anima_statuses(animas_dir: Path, global_backend: str) -> list[dict[str, Any]]:
    from core.memory.backend.registry import resolve_backend_type

    entries: list[dict[str, Any]] = []
    for anima_dir in iter_anima_dirs(animas_dir):
        override = _read_per_anima_backend(anima_dir)
        entry: dict[str, Any] = {
            "name": anima_dir.name,
            "effective_backend": override or global_backend,
            "source": "per-anima" if override else "global",
        }
        try:
            entry["effective_backend"] = resolve_backend_type(anima_dir)
        except Exception as exc:
            entry["diagnostic"] = f"backend resolution failed: {exc}"
        entries.append(entry)
    return entries


def status_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    backends: dict[str, int] = {}
    for entry in entries:
        backend = str(entry.get("effective_backend", "unknown"))
        backends[backend] = backends.get(backend, 0) + 1
    return {
        "anima_count": len(entries),
        "override_count": sum(1 for entry in entries if entry.get("source") == "per-anima"),
        "backends": backends,
    }


async def attach_neo4j_diagnostics(entries: list[dict[str, Any]], animas_dir: Path) -> None:
    from core.memory.backend.registry import get_backend

    for entry in entries:
        if entry.get("effective_backend") != "neo4j":
            continue
        backend = None
        try:
            backend = get_backend("neo4j", animas_dir / str(entry["name"]))
            health = await backend.health_check()
            entry["health"] = bool(health)
            entry["stats"] = await backend.stats() if health else {}
            if not health:
                entry["diagnostic"] = "Neo4j health check failed"
        except Exception as exc:
            entry["health"] = False
            entry["stats"] = {}
            entry["diagnostic"] = str(exc)
        finally:
            if backend is not None:
                await backend.close()


def print_status(payload: dict[str, Any], *, show_animas: bool) -> None:
    summary = payload["summary"]
    print(f"Memory Backend (global): {payload['global_backend']}")
    print(f"Data Directory: {payload['data_dir']}")
    print(f"Neo4j URI: {payload['neo4j']['uri']}")
    print(f"Neo4j Database: {payload['neo4j']['database']}")
    print(f"Anima Count: {summary['anima_count']}")
    print(f"Per-Anima Overrides: {summary['override_count']}")
    if summary["backends"]:
        counts = ", ".join(f"{backend}={count}" for backend, count in sorted(summary["backends"].items()))
        print(f"Effective Backends: {counts}")

    backups = payload["backups"]
    if backups:
        print(f"\nBackups ({len(backups)}):")
        for backup in backups:
            print(f"  {backup['name']}  ({backup['size_mb']} MB)")
    else:
        print("\nNo backups found.")

    if show_animas:
        print("\nAnimas:")
        for entry in payload["animas"]:
            health = ""
            if "health" in entry:
                health = f" health={'ok' if entry['health'] else 'failed'}"
            print(f"  {entry['name']}: {entry['effective_backend']} ({entry['source']}){health}")
            if entry.get("stats"):
                stats = ", ".join(f"{key}={value}" for key, value in sorted(entry["stats"].items()))
                print(f"    stats: {stats}")
            if entry.get("diagnostic"):
                print(f"    diagnostic: {entry['diagnostic']}")
        return

    overrides = [entry for entry in payload["animas"] if entry.get("source") == "per-anima"]
    if overrides:
        print("\nPer-Anima Overrides:")
        for entry in overrides:
            print(f"  {entry['name']}: {entry['effective_backend']}")


async def purge_restored_anima_graphs(animas_dir: Path) -> tuple[int, list[tuple[str, str]]]:
    from core.memory.backend.registry import get_backend

    purged = 0
    failures: list[tuple[str, str]] = []
    for anima_dir in iter_anima_dirs(animas_dir):
        backend = None
        try:
            backend = get_backend("neo4j", anima_dir)
            await backend.reset()
            purged += 1
        except Exception as exc:
            failures.append((anima_dir.name, str(exc)))
        finally:
            if backend is not None:
                await backend.close()
    return purged, failures


async def run_cleanup(anima_dir: Path, prefix: str, include_orphans: bool, dry_run: bool) -> None:
    from core.memory.backend.registry import get_backend

    backend = get_backend("neo4j", anima_dir)
    driver = await backend._ensure_driver()
    group_id = backend._group_id

    try:
        episode_rows = await driver.execute_query(
            _FIND_EPISODES_BY_SOURCE_PREFIX,
            {"group_id": group_id, "prefix": prefix},
        )
        episode_uuids = _row_uuids(episode_rows)
        orphan_uuids: list[str] = []
        if include_orphans and episode_uuids:
            orphan_rows = await driver.execute_query(
                _FIND_ORPHAN_ENTITIES_AFTER_EPISODE_CLEANUP,
                {"group_id": group_id, "episode_uuids": episode_uuids},
            )
            orphan_uuids = _row_uuids(orphan_rows)

        if dry_run:
            print(f"[DRY RUN] Episodes matching source prefix '{prefix}': {len(episode_uuids)}")
            if include_orphans:
                print(f"[DRY RUN] Orphaned entities after episode cleanup: {len(orphan_uuids)}")
            print("\nNo changes made (dry-run mode).")
            return

        if episode_uuids:
            await driver.execute_write(
                _SOFT_DELETE_EPISODES_BY_UUIDS,
                {
                    "group_id": group_id,
                    "episode_uuids": episode_uuids,
                    "deleted_at": datetime.now(tz=UTC).isoformat(),
                },
            )
        print(f"Soft-deleted {len(episode_uuids)} episodes with source prefix '{prefix}'")

        if include_orphans:
            if orphan_uuids:
                await driver.execute_write(
                    _SOFT_DELETE_ENTITIES_BY_UUIDS,
                    {
                        "group_id": group_id,
                        "entity_uuids": orphan_uuids,
                        "deleted_at": datetime.now(tz=UTC).isoformat(),
                    },
                )
            print(f"Soft-deleted {len(orphan_uuids)} orphaned entities")

        print("\nCleanup complete.")
    finally:
        await backend.close()


def _read_per_anima_backend(anima_dir: Path) -> str | None:
    status_path = anima_dir / "status.json"
    if not status_path.is_file():
        return None
    try:
        value = json.loads(status_path.read_text(encoding="utf-8")).get("memory_backend")
    except Exception:
        logger.debug("Failed to read memory_backend from %s", status_path, exc_info=True)
        return None
    return str(value) if value else None


def _row_uuids(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row["uuid"]) for row in rows if row.get("uuid")]
