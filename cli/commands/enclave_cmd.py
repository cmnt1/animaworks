# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Operational commands for enclave runtimes."""

from __future__ import annotations

import argparse
import grp
import importlib
import json
import logging
import stat
from pathlib import Path
from typing import Any

from core.i18n import t

logger = logging.getLogger(__name__)


def register_enclave_command(subparsers: argparse._SubParsersAction) -> None:
    """Register enclave doctor and audit-summary commands."""
    parser = subparsers.add_parser("enclave", help="Enclave health and audit operations")
    enclave_sub = parser.add_subparsers(dest="enclave_command", required=True)

    doctor = enclave_sub.add_parser("doctor", help="Check enclave runtime configuration and connectivity")
    doctor.add_argument("--json", action="store_true", dest="json_output", help=t("enclave.cli.doctor_json"))
    doctor.set_defaults(func=enclave_doctor_command)

    status = enclave_sub.add_parser("status", help="Show today's enclave egress audit counts")
    status.set_defaults(func=enclave_status_command)


def _check_row(scope: str, check: str, status: str, detail: str) -> dict[str, str]:
    return {"scope": scope, "check": check, "status": status, "detail": detail}


def _socket_checks(socket_path: str, socket_group: str) -> list[dict[str, str]]:
    """Inspect a local gateway socket's type, mode, and configured group."""
    if not socket_path:
        return [
            _check_row("enclave", "socket_exists", "fail", "socket_path is not configured"),
            _check_row("enclave", "socket_mode_0660", "skip", "socket is unavailable"),
            _check_row("enclave", "socket_group", "skip", "socket is unavailable"),
        ]

    path = Path(socket_path)
    try:
        socket_stat = path.lstat()
    except OSError:
        return [
            _check_row("enclave", "socket_exists", "fail", "Unix socket does not exist or cannot be inspected"),
            _check_row("enclave", "socket_mode_0660", "skip", "socket is unavailable"),
            _check_row("enclave", "socket_group", "skip", "socket is unavailable"),
        ]

    is_socket = stat.S_ISSOCK(socket_stat.st_mode)
    rows = [
        _check_row(
            "enclave",
            "socket_exists",
            "ok" if is_socket else "fail",
            "Unix socket exists" if is_socket else "path is not a Unix socket",
        )
    ]
    if not is_socket:
        rows.extend(
            [
                _check_row("enclave", "socket_mode_0660", "skip", "path is not a Unix socket"),
                _check_row("enclave", "socket_group", "skip", "path is not a Unix socket"),
            ]
        )
        return rows

    actual_mode = stat.S_IMODE(socket_stat.st_mode)
    rows.append(
        _check_row(
            "enclave",
            "socket_mode_0660",
            "ok" if actual_mode == 0o660 else "fail",
            f"mode is {actual_mode:04o}; expected 0660",
        )
    )

    if not socket_group:
        rows.append(_check_row("enclave", "socket_group", "fail", "socket_group is not configured"))
        return rows

    try:
        expected_group = grp.getgrnam(socket_group)
    except KeyError:
        rows.append(_check_row("enclave", "socket_group", "fail", f"configured group '{socket_group}' does not exist"))
        return rows

    try:
        actual_group = grp.getgrgid(socket_stat.st_gid).gr_name
    except KeyError:
        actual_group = f"gid:{socket_stat.st_gid}"
    group_matches = socket_stat.st_gid == expected_group.gr_gid
    detail = f"group is {actual_group}; expected {socket_group}"
    rows.append(_check_row("enclave", "socket_group", "ok" if group_matches else "fail", detail))
    return rows


def _masker_dependencies() -> list[str]:
    """Return the masker dependencies that cannot be imported."""
    missing: list[str] = []
    for module_name in ("fugashi", "ipadic"):
        try:
            importlib.import_module(module_name)
        except Exception:
            missing.append(module_name)
    return missing


def _check_local_enclave(config: Any, data_dir: Path) -> list[dict[str, str]]:
    """Run all local-only checks for an enabled enclave config."""
    from core.enclave.guards import collect_enclave_violations
    from core.enclave.ops import check_gateway_health

    rows: list[dict[str, str]] = []
    try:
        violations = collect_enclave_violations(config, data_dir, host=None)
    except Exception as exc:
        logger.warning("Could not collect enclave guard results (%s)", type(exc).__name__)
        violations = ["Could not collect enclave guard results"]
    if violations:
        rows.extend(_check_row("enclave", "guards", "fail", violation) for violation in violations)
    else:
        rows.append(_check_row("enclave", "guards", "ok", "no startup guard violations"))

    rows.extend(_socket_checks(config.enclave.socket_path, config.enclave.socket_group))
    healthy = check_gateway_health(config.enclave.socket_path)
    rows.append(
        _check_row(
            "enclave",
            "gateway_health",
            "ok" if healthy else "fail",
            "GET /v1/health succeeded" if healthy else "gateway did not return a healthy response",
        )
    )

    try:
        from core.enclave.egress.config import load_egress_config
        from core.enclave.egress.pipeline import EgressPipeline

        pipeline_config = load_egress_config(config.enclave.egress)
        EgressPipeline(config=pipeline_config, data_dir=data_dir)
    except Exception as exc:
        logger.warning("Enclave egress pipeline validation failed (%s)", type(exc).__name__)
        rows.append(_check_row("enclave", "egress_pipeline", "fail", "egress config cannot build a pipeline"))
    else:
        rows.append(_check_row("enclave", "egress_pipeline", "ok", "pipeline config is valid"))

    missing = _masker_dependencies()
    rows.append(
        _check_row(
            "enclave",
            "masker_dependencies",
            "fail" if missing else "ok",
            f"cannot import: {', '.join(missing)}" if missing else "fugashi and ipadic import successfully",
        )
    )
    return rows


def _check_host_enclaves(enclaves: dict[str, Any]) -> list[dict[str, str]]:
    """Probe each configured host-side enclave gateway."""
    from core.enclave.ops import check_gateway_health

    if not enclaves:
        return [_check_row("host", "enclaves", "skip", "no host-side enclaves are configured")]

    rows: list[dict[str, str]] = []
    for name, client_config in sorted(enclaves.items()):
        healthy = check_gateway_health(client_config.socket_path)
        rows.append(
            _check_row(
                "host",
                f"{name}.gateway_health",
                "ok" if healthy else "fail",
                "reachable and healthy" if healthy else "socket connection or /v1/health failed",
            )
        )
    return rows


def _print_checks(checks: list[dict[str, str]], *, json_output: bool) -> None:
    success = all(item["status"] != "fail" for item in checks)
    if json_output:
        print(json.dumps({"ok": success, "checks": checks}, ensure_ascii=False, indent=2))
        return

    print(f"{'SCOPE':<8} {'CHECK':<28} {'RESULT':<6} DETAIL")
    for item in checks:
        print(f"{item['scope']:<8} {item['check']:<28} {item['status']:<6} {item['detail']}")


def enclave_doctor_command(args: argparse.Namespace) -> None:
    """Check local enclave security and gateway health."""
    from core.config import load_config
    from core.paths import get_data_dir

    try:
        config = load_config()
    except Exception as exc:
        logger.error("Could not load AnimaWorks config (%s)", type(exc).__name__)
        checks = [_check_row("config", "load", "fail", "config.json could not be loaded")]
        _print_checks(checks, json_output=bool(getattr(args, "json_output", False)))
        raise SystemExit(1) from exc

    data_dir = get_data_dir()
    checks: list[dict[str, str]] = []
    if config.enclave.enabled:
        checks.extend(_check_local_enclave(config, data_dir))
    else:
        checks.append(_check_row("enclave", "enabled", "skip", "local enclave mode is disabled"))
    checks.extend(_check_host_enclaves(config.enclaves))

    success = all(item["status"] != "fail" for item in checks)
    _print_checks(checks, json_output=bool(getattr(args, "json_output", False)))
    if not success:
        raise SystemExit(1)


def enclave_status_command(_args: argparse.Namespace) -> None:
    """Print only today's aggregate egress success and block counts."""
    from core.enclave.ops import count_today_egress_audits
    from core.paths import get_data_dir

    counts = count_today_egress_audits(get_data_dir())
    print(f"ok={counts['ok']} blocked={counts['blocked']}")


__all__ = ["enclave_doctor_command", "enclave_status_command", "register_enclave_command"]
