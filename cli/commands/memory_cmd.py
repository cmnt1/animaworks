from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Memory maintenance commands."""

import argparse
import json
import logging
from pathlib import Path

from core.i18n import t
from core.paths import get_data_dir

logger = logging.getLogger("animaworks.cli.memory")


def register_memory_command(subparsers: argparse._SubParsersAction) -> None:
    """Register memory maintenance subcommands."""
    parser = subparsers.add_parser("memory", help=t("cli.memory_help"))
    memory_sub = parser.add_subparsers(dest="memory_command", required=True)

    dry_run = memory_sub.add_parser(
        "forgetting-dry-run",
        help=t("cli.memory_forgetting_dry_run_help"),
    )
    dry_run.add_argument("--anima", required=True, help=t("cli.memory_forgetting_dry_run_anima_help"))
    dry_run.set_defaults(func=forgetting_dry_run_command)


def forgetting_dry_run_command(args: argparse.Namespace) -> None:
    """Report forgetting counts using the active vector owner without writes."""
    anima_name = args.anima
    anima_dir = Path(get_data_dir()) / "animas" / anima_name
    if not anima_dir.is_dir():
        logger.error(t("cli.memory_anima_not_found", anima=anima_name))
        raise SystemExit(1)

    from core.memory.maintenance.forgetting import ForgettingEngine
    from core.memory.rag.cli_access import open_vector_access
    from core.memory.rag.owner_lock import VectorOwnerBusy

    try:
        with open_vector_access(anima_name, anima_dir, purpose="forgetting-dry-run") as access:
            result = ForgettingEngine(
                anima_dir,
                anima_name,
                vector_store=access.store,
            ).synaptic_downscaling(dry_run=True)
    except VectorOwnerBusy as exc:
        logger.error(t("cli.memory_vector_store_unavailable", anima=anima_name, error=exc))
        raise SystemExit(1) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))
