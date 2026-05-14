"""CLI commands for memory backend management: status, migrate, rollback, backup."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def register_memory_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the 'memory' command group."""
    p = subparsers.add_parser("memory", help="Memory backend management")
    sub = p.add_subparsers(dest="memory_command")

    # memory status
    sub.add_parser("status", help="Show current memory backend status")

    # memory migrate
    p_migrate = sub.add_parser("migrate", help="Migrate to new backend")
    p_migrate.add_argument("--to", required=True, choices=["neo4j"], dest="target_backend")
    grp = p_migrate.add_mutually_exclusive_group(required=True)
    grp.add_argument("--all", action="store_true", dest="migrate_all")
    grp.add_argument("--anima", type=str, dest="migrate_anima")
    p_migrate.add_argument("--dry-run", action="store_true")
    p_migrate.add_argument("--resume", action="store_true")
    p_migrate.add_argument(
        "--activate-global",
        action="store_true",
        help="After migration, set global memory.backend to neo4j. Neo4j is experimental; default is migration only.",
    )

    # memory rollback
    p_rollback = sub.add_parser("rollback", help="Rollback to backup")
    p_rollback.add_argument("--from-backup", required=True, dest="backup_name")
    p_rollback.add_argument("--purge-neo4j", action="store_true")

    # memory backup
    p_backup = sub.add_parser("backup", help="Backup management")
    backup_sub = p_backup.add_subparsers(dest="backup_command")
    backup_sub.add_parser("list", help="List available backups")
    backup_sub.add_parser("create", help="Create manual backup")

    # memory cleanup
    p_cleanup = sub.add_parser("cleanup", help="Clean up graph data by source prefix")
    p_cleanup.add_argument("--anima", required=True, help="Anima name")
    p_cleanup.add_argument(
        "--source-prefix",
        required=True,
        dest="source_prefix",
        help="Episode source prefix to match",
    )
    p_cleanup.add_argument(
        "--include-orphans",
        action="store_true",
        dest="include_orphans",
        help="Also delete orphaned entities",
    )
    p_cleanup.add_argument(
        "--dry-run",
        action="store_true",
        dest="cleanup_dry_run",
        help="Show what would be deleted without deleting",
    )

    p.set_defaults(func=_handle_memory)


def _handle_memory(args: argparse.Namespace) -> None:
    """Dispatch memory subcommands."""
    cmd = getattr(args, "memory_command", None)

    if cmd == "status":
        _cmd_status()
    elif cmd == "migrate":
        _cmd_migrate(args)
    elif cmd == "rollback":
        _cmd_rollback(args)
    elif cmd == "backup":
        _cmd_backup(args)
    elif cmd == "cleanup":
        _cmd_cleanup(args)
    else:
        print("Usage: animaworks memory {status|migrate|rollback|backup|cleanup}")
        sys.exit(1)


def _cmd_status() -> None:
    """Show memory backend status."""
    from core.config.models import load_config
    from core.paths import get_data_dir

    cfg = load_config()
    backend = getattr(getattr(cfg, "memory", None), "backend", "legacy")
    data_dir = get_data_dir()

    print(f"Memory Backend: {_backend_policy_label(str(backend))}")
    print("Policy: legacy is stable/default; neo4j is experimental opt-in.")
    print(f"Data Directory: {data_dir}")

    # Count animas
    animas_dir = data_dir / "animas"
    if animas_dir.is_dir():
        anima_count = sum(1 for d in animas_dir.iterdir() if d.is_dir() and not d.name.startswith("."))
        print(f"Anima Count: {anima_count}")
        overrides = _collect_per_anima_backend_overrides(animas_dir)
        if overrides:
            print("\nPer-Anima Memory Backend Overrides:")
            for name, value in overrides:
                print(f"  {name}: {_backend_policy_label(value)}")
        else:
            print("\nPer-Anima Memory Backend Overrides: None")

    # List backups
    from core.memory.migration.backup import BackupManager

    bm = BackupManager(data_dir)
    backups = bm.list_backups()
    if backups:
        print(f"\nBackups ({len(backups)}):")
        for b in backups:
            print(f"  {b['name']}  ({b['size_mb']} MB)")
    else:
        print("\nNo backups found.")

    # Neo4j connection status (if neo4j backend)
    if backend == "neo4j":
        neo4j_cfg = getattr(getattr(cfg, "memory", None), "neo4j", None)
        if neo4j_cfg:
            print(f"\nNeo4j URI: {neo4j_cfg.uri}")
            print(f"Neo4j Database: {neo4j_cfg.database}")


def _backend_policy_label(backend: str) -> str:
    """Return backend name plus stability policy for CLI display."""
    if backend == "legacy":
        return "legacy (stable/default)"
    if backend == "neo4j":
        return "neo4j (experimental/opt-in)"
    return backend


def _collect_per_anima_backend_overrides(animas_dir: Path) -> list[tuple[str, str]]:
    """Read per-anima memory_backend overrides from status.json files."""
    overrides: list[tuple[str, str]] = []
    for anima_dir in sorted(animas_dir.iterdir(), key=lambda p: p.name):
        if not anima_dir.is_dir() or anima_dir.name.startswith("."):
            continue
        status_path = anima_dir / "status.json"
        if not status_path.is_file():
            continue
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        backend = data.get("memory_backend")
        if isinstance(backend, str) and backend:
            overrides.append((anima_dir.name, backend))
    return overrides


def _cmd_migrate(args: argparse.Namespace) -> None:
    """Run migration."""
    from core.memory.migration.backup import BackupManager
    from core.memory.migration.migrator import MemoryMigrator
    from core.paths import get_data_dir

    data_dir = get_data_dir()
    migrator = MemoryMigrator(data_dir)

    if args.migrate_all:
        anima_names = migrator.list_animas()
    else:
        anima_names = [args.migrate_anima]

    if not anima_names:
        print("No animas found to migrate.")
        return

    if args.dry_run:
        print("=== DRY RUN ===\n")
        total_files = 0
        total_calls = 0
        for name in anima_names:
            est = migrator.estimate_cost(name)
            files = est["estimated_files"]
            calls = est["estimated_llm_calls"]
            total_files += files
            total_calls += calls
            print(f"  {name}: {files} files, ~{calls} LLM calls")
            for scope, cnt in est.get("file_counts", {}).items():
                if cnt:
                    print(f"    {scope}: {cnt}")
        print(f"\nTotal: {total_files} files, ~{total_calls} LLM calls")
        print(f"Estimated tokens: ~{total_files * 4000:,}")
        return

    # Lock check
    lock_path = data_dir / "run" / "migration.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        print("ERROR: Migration already in progress (lock file exists).")
        print(f"  Remove {lock_path} if previous migration crashed.")
        sys.exit(1)

    if not args.resume:
        print("Creating backup...")
        bm = BackupManager(data_dir)
        backup_path = bm.create(label="pre-migration")
        print(f"  Backup: {backup_path}")

    try:
        lock_path.write_text(str(asyncio.get_event_loop()), encoding="utf-8")

        from core.memory.migration.checkpoint import CheckpointManager

        ckpt = CheckpointManager(data_dir / "run" / "migration.ckpt")

        print(f"\nMigrating {len(anima_names)} anima(s)...")

        total_stats: dict[str, int] = {"files": 0, "entities": 0, "facts": 0, "skipped": 0, "errors": 0}

        for name in anima_names:
            print(f"\n  [{name}]")

            def progress(path: str, status: str) -> None:
                sym = "✓" if status == "done" else "✗"
                print(f"    {sym} {Path(path).name}")

            stats = asyncio.run(migrator.migrate_anima(name, checkpoint_manager=ckpt, on_progress=progress))

            for k, v in stats.items():
                total_stats[k] = total_stats.get(k, 0) + v

        print("\n=== Migration Complete ===")
        print(f"  Files: {total_stats['files']}")
        print(f"  Skipped: {total_stats['skipped']}")
        print(f"  Errors: {total_stats['errors']}")

        if total_stats["errors"] == 0:
            from core.config.models import load_config, save_config

            cfg = load_config()
            if getattr(args, "activate_global", False):
                cfg.memory.backend = "neo4j"
                save_config(cfg)
                print("\n  Config updated: memory.backend = neo4j")
                print("  WARNING: Neo4j memory backend is experimental/opt-in.")
            else:
                current = getattr(getattr(cfg, "memory", None), "backend", "legacy")
                print("\n  Global config unchanged: memory.backend = " + str(current))
                print("  Neo4j migration completed as data preparation only.")
                print("  To use Neo4j globally, re-run with --activate-global.")
                print("  To opt in one anima, use: animaworks anima set-memory-backend <name> neo4j")
        else:
            print("\n  WARNING: Errors occurred. Config NOT updated.")
            print("  Fix errors and re-run with --resume")
    finally:
        if lock_path.exists():
            lock_path.unlink()


def _cmd_rollback(args: argparse.Namespace) -> None:
    """Rollback from backup."""
    from core.memory.migration.backup import BackupManager
    from core.paths import get_data_dir

    data_dir = get_data_dir()
    bm = BackupManager(data_dir)

    print(f"Restoring from backup: {args.backup_name}")
    try:
        bm.restore(args.backup_name)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    from core.config.models import load_config, save_config

    cfg = load_config()
    cfg.memory.backend = "legacy"
    save_config(cfg)
    print("Config updated: memory.backend = legacy")
    print("Rollback complete.")


def _cmd_backup(args: argparse.Namespace) -> None:
    """Backup subcommands."""
    from core.memory.migration.backup import BackupManager
    from core.paths import get_data_dir

    data_dir = get_data_dir()
    bm = BackupManager(data_dir)

    sub = getattr(args, "backup_command", None)

    if sub == "list":
        backups = bm.list_backups()
        if not backups:
            print("No backups found.")
            return
        for b in backups:
            print(f"  {b['name']}  ({b['size_mb']} MB)")
    elif sub == "create":
        path = bm.create()
        print(f"Backup created: {path}")
    else:
        print("Usage: animaworks memory backup {list|create}")
        sys.exit(1)


def _cmd_cleanup(args: argparse.Namespace) -> None:
    """Clean up Neo4j graph data by episode source prefix."""
    import asyncio

    from core.memory.backend.registry import resolve_backend_type
    from core.paths import get_animas_dir

    anima_dir = get_animas_dir() / args.anima
    if not anima_dir.is_dir():
        print(f"Error: anima '{args.anima}' not found")
        sys.exit(1)

    backend_type = resolve_backend_type(anima_dir)
    if backend_type != "neo4j":
        print(
            f"Error: anima '{args.anima}' is not using Neo4j backend (current: {backend_type})",
        )
        sys.exit(1)

    asyncio.run(
        _run_cleanup(anima_dir, args.source_prefix, args.include_orphans, args.cleanup_dry_run),
    )


async def _run_cleanup(
    anima_dir: Path,
    prefix: str,
    include_orphans: bool,
    dry_run: bool,
) -> None:
    """Async cleanup runner."""
    from core.memory.backend.registry import get_backend

    backend = get_backend("neo4j", anima_dir)
    driver = await backend._ensure_driver()
    group_id = backend._group_id

    try:
        if dry_run:
            # Count episodes to be deleted
            count_result = await driver.execute_query(
                "MATCH (ep:Episode) WHERE ep.group_id = $group_id AND ep.source STARTS WITH $prefix "
                "RETURN count(ep) AS cnt",
                {"group_id": group_id, "prefix": prefix},
            )
            ep_count = count_result[0]["cnt"] if count_result else 0
            print(f"[DRY RUN] Episodes matching source prefix '{prefix}': {ep_count}")

            if include_orphans:
                orphan_result = await driver.execute_query(
                    """MATCH (e:Entity)
                    WHERE e.group_id = $group_id
                      AND NOT EXISTS { (ep:Episode)-[:MENTIONS]->(e) WHERE NOT (ep.source STARTS WITH $prefix) }
                      AND NOT EXISTS { ()-[:RELATES_TO]->(e) }
                      AND NOT EXISTS { (e)-[:RELATES_TO]->() }
                    RETURN count(e) AS cnt""",
                    {"group_id": group_id, "prefix": prefix},
                )
                orphan_count = orphan_result[0]["cnt"] if orphan_result else 0
                print(f"[DRY RUN] Orphaned entities (after episode deletion): {orphan_count}")

            print("\nNo changes made (dry-run mode).")
        else:
            # Delete episodes
            delete_result = await driver.execute_query(
                "MATCH (ep:Episode) WHERE ep.group_id = $group_id AND ep.source STARTS WITH $prefix "
                "DETACH DELETE ep RETURN count(ep) AS cnt",
                {"group_id": group_id, "prefix": prefix},
            )
            ep_deleted = delete_result[0]["cnt"] if delete_result else 0
            print(f"Deleted {ep_deleted} episodes with source prefix '{prefix}'")

            if include_orphans:
                orphan_result = await driver.execute_query(
                    """MATCH (e:Entity)
                    WHERE e.group_id = $group_id
                      AND NOT EXISTS { (ep:Episode)-[:MENTIONS]->(e) }
                      AND NOT EXISTS { ()-[:RELATES_TO]->(e) }
                      AND NOT EXISTS { (e)-[:RELATES_TO]->() }
                    DETACH DELETE e
                    RETURN count(e) AS cnt""",
                    {"group_id": group_id},
                )
                orphan_deleted = orphan_result[0]["cnt"] if orphan_result else 0
                print(f"Deleted {orphan_deleted} orphaned entities")

            print("\nCleanup complete.")
    finally:
        await backend.close()
