from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""RAG repair command."""

import argparse
import sys


def setup_repair_rag_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the top-level repair-rag command."""
    parser = subparsers.add_parser(
        "repair-rag",
        help="Quarantine and rebuild one anima's RAG vectordb",
        description="Stop the target anima before running this command in production.",
    )
    parser.add_argument("--anima", required=True, help="Anima name to repair")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Required confirmation for destructive quarantine and full rebuild",
    )
    parser.add_argument(
        "--shared",
        action="store_true",
        help="Reindex shared common_knowledge and common_skills into this anima DB",
    )
    parser.add_argument(
        "--reason",
        default="manual_repair_rag_cli",
        help=argparse.SUPPRESS,
    )
    parser.set_defaults(func=repair_rag_command)


def repair_rag_command(args: argparse.Namespace) -> None:
    """Run synchronous RAG repair for one anima."""
    if not args.full:
        print("repair-rag requires --full for destructive quarantine and rebuild", file=sys.stderr)
        raise SystemExit(2)

    from core.memory.rag.repair import get_repair_service

    result = get_repair_service().repair_anima_if_allowed(
        args.anima,
        reason=str(getattr(args, "reason", "manual_repair_rag_cli")),
        collection=None,
        source="cli",
        include_shared=bool(args.shared),
    )
    if result.ok:
        print(
            "RAG repair succeeded: "
            f"anima={result.anima_name} chunks={result.chunks_indexed} quarantine={result.quarantine_path}"
        )
        return

    print(
        "RAG repair failed: "
        f"anima={result.anima_name} status={result.status} stage={result.stage} error={result.error}",
        file=sys.stderr,
    )
    raise SystemExit(1)
