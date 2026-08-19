from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Run the stdio MCP server for an existing anima."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from cli.commands.index_cmd import _setup_server_delegation
from core.paths import get_animas_dir

_DEFAULT_TOOLS = "search_memory,read_memory_file,write_memory_file"


def _project_from_cwd(anima_dir: Path) -> str | None:
    """Resolve the project whose registered repo contains the current directory."""
    try:
        registry = json.loads((anima_dir / "projects.json").read_text(encoding="utf-8"))
        cwd = Path.cwd().resolve()
    except Exception:
        return None
    best: tuple[int, str] | None = None
    for name, entry in registry.items():
        repo = entry.get("repo") if isinstance(entry, dict) else None
        if not repo:
            continue
        repo_path = Path(repo).resolve()
        if cwd == repo_path or cwd.is_relative_to(repo_path):
            depth = len(repo_path.parts)
            if best is None or depth > best[0]:
                best = (depth, name)
    return best[1] if best else None


def setup_mcp_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("mcp", help="Run a stdio MCP server for an anima")
    parser.add_argument("--anima", required=True, help="Anima name")
    parser.add_argument("--project", help="Default project archive")
    parser.add_argument("--tools", default=_DEFAULT_TOOLS, help="Comma-separated exposed tools")
    parser.set_defaults(func=mcp_command)


def mcp_command(args: argparse.Namespace) -> None:
    animas_dir = get_animas_dir().resolve()
    anima_dir = (animas_dir / args.anima).resolve()
    if not anima_dir.is_relative_to(animas_dir) or not anima_dir.is_dir():
        print(f"Error: anima '{args.anima}' does not exist", file=sys.stderr)
        raise SystemExit(1)

    os.environ["ANIMAWORKS_ANIMA_DIR"] = str(anima_dir)
    os.environ["ANIMAWORKS_MCP_TOOLS"] = args.tools
    project = args.project or _project_from_cwd(anima_dir)
    if project:
        os.environ["ANIMAWORKS_MCP_PROJECT"] = project
    _setup_server_delegation()

    from core.mcp.server import main

    asyncio.run(main())
