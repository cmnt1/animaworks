"""CLI commands for memory backend management: status, migrate, rollback, backup."""

from __future__ import annotations

import argparse
import asyncio
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

    # memory rollback
    p_rollback = sub.add_parser("rollback", help="Rollback to backup")
    p_rollback.add_argument("--from-backup", required=True, dest="backup_name")
    p_rollback.add_argument("--purge-neo4j", action="store_true")

    # memory backup
    p_backup = sub.add_parser("backup", help="Backup management")
    backup_sub = p_backup.add_subparsers(dest="backup_command")
    backup_sub.add_parser("list", help="List available backups")
    backup_sub.add_parser("create", help="Create manual backup")

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
    else:
        print("Usage: animaworks memory {status|migrate|rollback|backup}")
        sys.exit(1)


def _cmd_status() -> None:
    """Show memory backend status."""
    from core.config.models import load_config
    from core.paths import get_data_dir

    cfg = load_config()
    backend = getattr(getattr(cfg, "memory", None), "backend", "legacy")
    data_dir = get_data_dir()

    print(f"Memory Backend: {backend}")
    print(f"Data Directory: {data_dir}")

    # Count animas
    animas_dir = data_dir / "animas"
    if animas_dir.is_dir():
        anima_count = sum(1 for d in animas_dir.iterdir() if d.is_dir() and not d.name.startswith("."))
        print(f"Anima Count: {anima_count}")

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
            cfg.memory.backend = "neo4j"
            save_config(cfg)
            print("\n  Config updated: memory.backend = neo4j")
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
