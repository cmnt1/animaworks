from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from scripts.anima_merge.cli import cmd_anima_merge, cmd_anima_merge_finalize


def build_parser() -> argparse.ArgumentParser:
    """Build the standalone merge CLI using the former ``anima merge`` options."""
    parser = argparse.ArgumentParser(
        prog="python -m scripts.anima_merge",
        description="Merge one anima into another. Use 'finalize' to archive a completed merge.",
    )
    parser.add_argument("source", help="Anima to merge from")
    parser.add_argument("target", help="Anima to merge into")
    merge_mode = parser.add_mutually_exclusive_group()
    merge_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate a merge manifest without changing either anima (default)",
    )
    merge_mode.add_argument(
        "--execute",
        action="store_true",
        help="Execute the merge through source tombstone",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted --execute operation",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Continue despite preflight warnings for recoverable in-progress state",
    )
    return parser


def build_finalize_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.anima_merge finalize",
        description="Archive and unregister a completed merge tombstone.",
    )
    parser.add_argument("source", help="Tombstoned source anima")
    parser.add_argument("target", help="Merged target anima")
    finalize_mode = parser.add_mutually_exclusive_group()
    finalize_mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and show the finalize plan without changing data (default)",
    )
    finalize_mode.add_argument(
        "--execute",
        action="store_true",
        help="Archive the source and remove its registration",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted --execute operation",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == "finalize":
        args = build_finalize_parser().parse_args(args_list[1:])
        cmd_anima_merge_finalize(args)
        return
    args = build_parser().parse_args(args_list)
    cmd_anima_merge(args)


if __name__ == "__main__":
    main()
