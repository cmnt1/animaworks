from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI command: ``animaworks tmp``."""

import argparse
import sys
import time

from core.i18n import t
from core.tmp_cleanup import (
    clean_tmp_dir,
    format_size,
    parse_size,
    resolve_tmp_roots,
    scan_tmp_dir,
)


def register_tmp_command(subparsers: argparse._SubParsersAction) -> None:
    """Register the tmp command group."""
    parser = subparsers.add_parser(
        "tmp",
        help="Inspect and clean AnimaWorks tmp directories",
    )
    tmp_sub = parser.add_subparsers(dest="tmp_command")

    list_parser = tmp_sub.add_parser("list", help="Show tmp usage summary")
    list_parser.add_argument(
        "--project",
        action="store_true",
        help="Include repository tmp/ in addition to runtime tmp",
    )
    list_parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Maximum number of entries to show per root (default: 20)",
    )
    list_parser.set_defaults(func=cmd_tmp_list)

    clean_parser = tmp_sub.add_parser("clean", help="Remove old or large tmp files")
    clean_parser.add_argument(
        "--older-than",
        type=int,
        default=7,
        metavar="DAYS",
        help="Remove entries older than DAYS (default: 7)",
    )
    clean_parser.add_argument(
        "--min-size",
        metavar="SIZE",
        help="Also remove entries at or above SIZE (e.g. 100M, 1G)",
    )
    clean_parser.add_argument(
        "--all",
        action="store_true",
        help="Remove all entries under tmp (requires --force)",
    )
    clean_parser.add_argument(
        "--force",
        action="store_true",
        help="Required with --all for destructive full cleanup",
    )
    clean_parser.add_argument(
        "--project",
        action="store_true",
        help="Also clean repository tmp/",
    )
    clean_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting",
    )
    clean_parser.set_defaults(func=cmd_tmp_clean)


def cmd_tmp(args: argparse.Namespace) -> None:
    """Dispatch tmp subcommands."""
    handler = getattr(args, "func", None)
    if handler is None:
        print("Usage: animaworks tmp {list|clean}")
        raise SystemExit(2)
    handler(args)


def cmd_tmp_list(args: argparse.Namespace) -> None:
    """Print tmp directory summaries."""
    roots = resolve_tmp_roots(include_project=bool(args.project))
    for root in roots:
        scan = scan_tmp_dir(root)
        print(t("tmp.list_header", path=scan.root))
        if scan.entry_count == 0:
            print(t("tmp.list_empty"))
            print()
            continue

        print(t("tmp.list_summary", size=format_size(scan.total_bytes), count=scan.entry_count))
        for entry in scan.entries[: max(args.top, 0)]:
            print(
                t(
                    "tmp.list_entry",
                    size=format_size(entry.size_bytes),
                    age=_format_age(entry.mtime),
                    name=entry.path.name,
                    kind=t("tmp.list_entry_dir") if entry.is_dir else "",
                )
            )
        print()


def cmd_tmp_clean(args: argparse.Namespace) -> None:
    """Remove eligible tmp entries."""
    clean_all = bool(args.all)
    min_size_bytes: int | None = None
    older_than_days: int | None = args.older_than

    if args.min_size:
        try:
            min_size_bytes = parse_size(args.min_size)
        except ValueError:
            print(t("tmp.invalid_size", value=args.min_size), file=sys.stderr)
            raise SystemExit(2) from None

    if clean_all:
        if not args.force:
            print(t("tmp.clean_requires_force"), file=sys.stderr)
            raise SystemExit(2)
        older_than_days = None
    elif min_size_bytes is None and older_than_days is None:
        print(t("tmp.clean_requires_filter"), file=sys.stderr)
        raise SystemExit(2)

    exit_code = 0
    for root in resolve_tmp_roots(include_project=bool(args.project)):
        print(t("tmp.clean_header", path=root))
        result = clean_tmp_dir(
            root,
            older_than_days=older_than_days,
            min_size_bytes=min_size_bytes,
            clean_all=clean_all,
            dry_run=bool(args.dry_run),
        )
        message_key = "tmp.clean_dry_run" if args.dry_run else "tmp.clean_done"
        print(
            t(
                message_key,
                count=result.removed_count,
                size=format_size(result.removed_bytes),
            )
        )
        if result.skipped_count:
            print(t("tmp.clean_skipped", count=result.skipped_count))
        for error in result.errors:
            print(t("tmp.clean_error", message=error))
            exit_code = 1
        print()

    raise SystemExit(exit_code)


def _format_age(mtime: float) -> str:
    age_seconds = max(0, int(time.time() - mtime))
    days = age_seconds // 86400
    if days >= 1:
        return t("tmp.age_days", days=days)
    hours = age_seconds // 3600
    if hours >= 1:
        return t("tmp.age_hours", hours=hours)
    return t("tmp.age_recent")
