from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Skill Hub CLI commands."""

import argparse
import sys

from core.skills.hub import SkillHub, result_json


def register_skills_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("skills", help="Install and manage Skill Hub imports")
    sub = parser.add_subparsers(dest="skills_command")

    install = sub.add_parser("install", help="Install a skill from a local path, URL, or GitHub source")
    install.add_argument("source", help="Local path, direct URL, or github:owner/repo/path")
    _target_args(install)
    install.add_argument("--dry-run", action="store_true", help="Stage and scan without installing")
    install.add_argument("--replace", action="store_true", help="Replace an existing skill after creating a backup")
    install.add_argument("--force", action="store_true", help="Accepted for compatibility; import policy still applies")
    install.add_argument("--quarantine", action="store_true", help="Install into quarantine instead of active catalog")
    install.add_argument(
        "--trust-level",
        default="community",
        choices=["community", "untrusted"],
        help="Trust level to apply to active installs",
    )
    install.set_defaults(func=cmd_skills_install)

    list_cmd = sub.add_parser("list", help="List installed skills")
    _target_args(list_cmd, require_source=False)
    list_cmd.add_argument("--quarantine", action="store_true", help="List quarantine entries")
    list_cmd.set_defaults(func=cmd_skills_list)

    inspect = sub.add_parser("inspect", help="Inspect an installed or quarantined skill")
    inspect.add_argument("skill_name", help="Skill name")
    _target_args(inspect, require_source=False)
    inspect.set_defaults(func=cmd_skills_inspect)

    remove = sub.add_parser("remove", help="Remove an installed or quarantined skill")
    remove.add_argument("skill_name", help="Skill name")
    _target_args(remove, require_source=False)
    remove.set_defaults(func=cmd_skills_remove)

    quarantine = sub.add_parser("quarantine", help="Manage quarantined skills")
    quarantine_sub = quarantine.add_subparsers(dest="quarantine_command")

    q_list = quarantine_sub.add_parser("list", help="List quarantined skills")
    _target_args(q_list, require_source=False)
    q_list.set_defaults(func=cmd_skills_quarantine_list)

    q_promote = quarantine_sub.add_parser("promote", help="Promote a quarantined skill after approval")
    q_promote.add_argument("skill_name", help="Skill name")
    q_promote.add_argument("--approval-id", required=True, help="Human approval identifier")
    q_promote.add_argument("--replace", action="store_true", help="Replace existing active skill with backup")
    q_promote.add_argument(
        "--trust-level",
        default="community",
        choices=["community", "untrusted"],
        help="Trust level to apply after promotion",
    )
    _target_args(q_promote, require_source=False)
    q_promote.set_defaults(func=cmd_skills_quarantine_promote)


def _target_args(parser: argparse.ArgumentParser, *, require_source: bool = True) -> None:
    del require_source
    parser.add_argument("--target", choices=["personal", "common"], default="personal", help="Install target")
    parser.add_argument("--anima", default=None, help="Anima name for personal target")


def _hub(args: argparse.Namespace) -> SkillHub:
    return SkillHub(actor="cli")


def _print_json(value) -> None:
    print(result_json(value))


def _handle_errors(func, args: argparse.Namespace) -> None:
    try:
        func(args)
    except Exception as exc:
        print(result_json({"status": "error", "error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from exc


def cmd_skills_install(args: argparse.Namespace) -> None:
    _handle_errors(_cmd_skills_install, args)


def _cmd_skills_install(args: argparse.Namespace) -> None:
    result = _hub(args).install(
        args.source,
        target=args.target,
        anima=args.anima,
        dry_run=args.dry_run,
        replace=args.replace,
        force=args.force,
        trust_level=args.trust_level,
        quarantine=args.quarantine,
    )
    _print_json(result)


def cmd_skills_list(args: argparse.Namespace) -> None:
    _handle_errors(_cmd_skills_list, args)


def _cmd_skills_list(args: argparse.Namespace) -> None:
    _print_json(_hub(args).list_skills(target=args.target, anima=args.anima, quarantine=args.quarantine))


def cmd_skills_inspect(args: argparse.Namespace) -> None:
    _handle_errors(_cmd_skills_inspect, args)


def _cmd_skills_inspect(args: argparse.Namespace) -> None:
    _print_json(_hub(args).inspect(args.skill_name, target=args.target, anima=args.anima))


def cmd_skills_remove(args: argparse.Namespace) -> None:
    _handle_errors(_cmd_skills_remove, args)


def _cmd_skills_remove(args: argparse.Namespace) -> None:
    _print_json(_hub(args).remove(args.skill_name, target=args.target, anima=args.anima))


def cmd_skills_quarantine_list(args: argparse.Namespace) -> None:
    _handle_errors(_cmd_skills_quarantine_list, args)


def _cmd_skills_quarantine_list(args: argparse.Namespace) -> None:
    _print_json(_hub(args).list_skills(target=args.target, anima=args.anima, quarantine=True))


def cmd_skills_quarantine_promote(args: argparse.Namespace) -> None:
    _handle_errors(_cmd_skills_quarantine_promote, args)


def _cmd_skills_quarantine_promote(args: argparse.Namespace) -> None:
    result = _hub(args).promote_quarantine(
        args.skill_name,
        target=args.target,
        anima=args.anima,
        approval_id=args.approval_id,
        replace=args.replace,
        trust_level=args.trust_level,
    )
    _print_json(result)
