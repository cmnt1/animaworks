#!/usr/bin/env python3
"""Translate Japanese documentation and runtime templates incrementally."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.i18n.pipeline import PipelineError, Translator, load_configuration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate en/ko translations from Japanese source files")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("docs", "templates", "readme", "all"):
        subparser = subparsers.add_parser(command, help=f"Process {command} translations")
        subparser.add_argument("--check", action="store_true", help="Check generated files and manifest freshness only")
        subparser.add_argument(
            "--dry-run", action="store_true", help="List selected files without translating or writing"
        )
        subparser.add_argument("--only", metavar="GLOB", help="Limit processing to source paths matching this glob")
        subparser.add_argument("--force", metavar="GLOB", help="Retranslate every section in matching source files")
        subparser.add_argument("--engine", metavar="NAME", help="Select a configured translation engine")
        subparser.add_argument("--lang", metavar="LANGS", help="Comma-separated target languages")
        subparser.add_argument(
            "--stats", action="store_true", help="Report token usage, elapsed time, requests, and failures"
        )
        subparser.add_argument("--concurrency", type=int, metavar="N", help="Maximum concurrent translation requests")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        configuration, targets, glossary = load_configuration()
        if args.concurrency is not None:
            if args.concurrency < 1:
                raise PipelineError("--concurrency must be greater than zero")
            configuration.setdefault("defaults", {})["concurrency"] = args.concurrency
        translator = Translator(configuration=configuration, targets=targets, glossary=glossary)
        requested_langs = [lang.strip() for lang in args.lang.split(",") if lang.strip()] if args.lang else None
        return translator.run(
            args.command,
            requested_langs=requested_langs,
            only=args.only,
            force=args.force,
            dry_run=args.dry_run,
            check=args.check,
            engine_name=args.engine,
            stats=args.stats,
        )
    except (PipelineError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
