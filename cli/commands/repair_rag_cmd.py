from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""RAG repair command."""

import argparse
import sys
from typing import Any


def setup_repair_rag_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the top-level repair-rag command."""
    parser = subparsers.add_parser(
        "repair-rag",
        help="Quarantine and rebuild RAG vectordb data",
        description="Rebuild RAG through the active phase3 vector owner.",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--anima", help="Anima name to repair")
    target.add_argument("--all", action="store_true", help="Repair all enabled animas")
    target.add_argument("--suspect-only", action="store_true", help="Repair animas with recent RAG corruption evidence")
    target.add_argument("--list-suspects", action="store_true", help="List suspected corrupt RAG DBs without repairing")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Required confirmation for destructive quarantine and full rebuild",
    )
    parser.add_argument(
        "--shared",
        action="store_true",
        help="Accepted for compatibility; phase3 always rebuilds shared collections too",
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=None,
        help="Lookback window for --suspect-only/--list-suspects (default: repair config window)",
    )
    parser.add_argument("--reason", default="manual_repair_rag_cli", help=argparse.SUPPRESS)
    parser.set_defaults(func=repair_rag_command)


def repair_rag_command(args: argparse.Namespace) -> None:
    """Request server repair or rebuild directly as temporary vector owner."""
    list_suspects = bool(getattr(args, "list_suspects", False))
    if not list_suspects and not args.full:
        print("repair-rag requires --full for destructive quarantine and rebuild", file=sys.stderr)
        raise SystemExit(2)

    from core.memory.rag.repair import get_repair_service

    service = get_repair_service()
    suspect_only = bool(getattr(args, "suspect_only", False))
    all_animas = bool(getattr(args, "all", False))
    anima = getattr(args, "anima", None)
    window_minutes = getattr(args, "window_minutes", None)

    if list_suspects:
        suspects = service.discover_suspect_animas(window_minutes=window_minutes)
        if suspects:
            print("RAG repair suspects:")
            for name in suspects:
                print(f"  {name}")
        else:
            print("No RAG repair suspects found.")
        return

    if not anima and not all_animas and not suspect_only:
        print("repair-rag requires one of --anima, --all, --suspect-only, or --list-suspects", file=sys.stderr)
        raise SystemExit(2)

    if anima:
        targets = [anima]
    elif all_animas:
        targets = service.list_repairable_animas()
    else:
        targets = service.discover_suspect_animas(window_minutes=window_minutes)

    if not targets:
        print("No RAG repair targets found.")
        return

    from core.memory.rag.cli_access import open_vector_access
    from core.memory.rag.owner_lock import VectorOwnerBusy
    from core.paths import get_animas_dir

    animas_dir = get_animas_dir()
    reason = str(getattr(args, "reason", "manual_repair_rag_cli"))
    failed = False
    for name in targets:
        anima_dir = animas_dir / name
        if not anima_dir.is_dir():
            print(f"RAG repair failed: anima={name} error=Anima directory not found", file=sys.stderr)
            failed = True
            continue
        try:
            with open_vector_access(name, anima_dir, purpose=reason) as access:
                result = access.repair(include_shared=True)
        except VectorOwnerBusy as exc:
            print(f"RAG repair failed: anima={name} error={exc}", file=sys.stderr)
            failed = True
            continue
        except Exception as exc:
            print(f"RAG repair failed: anima={name} error={exc}", file=sys.stderr)
            failed = True
            continue

        _print_result(name, result)
        failed = failed or not bool(result.get("ok", result.get("status") in {"success", "healthy"}))

    if failed:
        raise SystemExit(1)


def _print_result(anima_name: str, result: dict[str, Any]) -> None:
    ok = bool(result.get("ok", result.get("status") in {"success", "healthy"}))
    chunks = result.get("chunks_indexed", result.get("last_chunks_indexed", 0))
    archive = result.get("archive_path", result.get("last_quarantine_path"))
    if ok:
        print(f"RAG repair succeeded: anima={anima_name} chunks={chunks} quarantine={archive}")
        return

    error = result.get("error", result.get("last_error"))
    if result.get("status") == "timeout":
        from core.i18n import t

        error = t("rag.cli_repair_timeout", anima=anima_name)
    print(
        f"RAG repair failed: anima={anima_name} status={result.get('status')} "
        f"stage={result.get('stage')} error={error}",
        file=sys.stderr,
    )
