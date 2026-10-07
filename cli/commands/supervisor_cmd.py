from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI subcommands for supervisor tools invoked via animaworks-tool supervisor.

Usage via animaworks-tool:
    animaworks-tool supervisor org-dashboard
    animaworks-tool supervisor ping [--name NAME]
    animaworks-tool supervisor read-state NAME
    animaworks-tool supervisor task-tracker [--status STATUS]

These commands delegate to ``ToolHandler`` (via
``cli._anima_tool.run_and_print``) so their output
matches what the MCP / Mode A executors return for the same tool.
"""

import argparse
import logging
import sys

from cli._anima_tool import run_and_print

logger = logging.getLogger("animaworks")


def cmd_supervisor(args: argparse.Namespace) -> None:
    """Dispatch supervisor subcommand."""
    sub = getattr(args, "supervisor_command", None)
    if sub == "org-dashboard":
        _cmd_org_dashboard(args)
    elif sub == "ping":
        _cmd_ping(args)
    elif sub == "read-state":
        _cmd_read_state(args)
    elif sub == "task-tracker":
        _cmd_task_tracker(args)
    else:
        print(
            "Usage: animaworks-tool supervisor {org-dashboard|ping|read-state|task-tracker}",
            file=sys.stderr,
        )
        sys.exit(1)


def _cmd_org_dashboard(args: argparse.Namespace) -> None:
    run_and_print("org_dashboard", {})


def _cmd_ping(args: argparse.Namespace) -> None:
    target_name = getattr(args, "name", None)
    tool_args = {"name": target_name} if target_name else {}
    run_and_print("ping_subordinate", tool_args)


def _cmd_read_state(args: argparse.Namespace) -> None:
    target_name = getattr(args, "name", "")
    if not target_name:
        print("Error: NAME is required", file=sys.stderr)
        sys.exit(1)
    run_and_print("read_subordinate_state", {"name": target_name})


def _cmd_task_tracker(args: argparse.Namespace) -> None:
    status_filter = getattr(args, "status", "delegated")
    run_and_print("task_tracker", {"status": status_filter})


def register_supervisor_command(subparsers) -> None:
    """Register the supervisor subcommand under animaworks-tool."""
    p_supervisor = subparsers.add_parser("supervisor", help="Supervisor tools for animas")
    sup_sub = p_supervisor.add_subparsers(dest="supervisor_command")

    sup_sub.add_parser("org-dashboard", help="Show org tree with status and tasks")

    p_ping = sup_sub.add_parser("ping", help="Check if subordinate animas are alive")
    p_ping.add_argument("--name", default=None, help="Specific anima name (omit for all subordinates)")

    p_read = sup_sub.add_parser("read-state", help="Read subordinate state (current_state.md, pending)")
    p_read.add_argument("name", help="Target anima name")

    p_tracker = sup_sub.add_parser("task-tracker", help="Track delegated tasks")
    p_tracker.add_argument(
        "--status",
        default="delegated",
        help="Filter by status (default: delegated)",
    )

    p_supervisor.set_defaults(func=cmd_supervisor)
