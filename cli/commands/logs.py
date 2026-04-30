"""CLI commands for viewing anima logs."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def cmd_logs(args: argparse.Namespace) -> None:
    """View anima logs."""
    from core.paths import get_data_dir

    log_dir = get_data_dir() / "logs"
    follow = bool(getattr(args, "follow", False))

    if args.all:
        # Show all logs (server + all animas)
        _tail_all_logs(log_dir, lines=args.lines, follow=follow)
    else:
        # Show specific anima log
        if not args.anima:
            print("Error: --anima is required (or use --all)")
            sys.exit(1)

        _tail_anima_log(log_dir=log_dir, anima_name=args.anima, lines=args.lines, date=args.date, follow=follow)


def _tail_anima_log(
    log_dir: Path,
    anima_name: str,
    lines: int = 50,
    date: str | None = None,
    follow: bool = False,
) -> None:
    """Tail a specific anima's log file."""
    anima_log_dir = log_dir / "animas" / anima_name

    if not anima_log_dir.exists():
        print(f"Error: No log directory for anima '{anima_name}'")
        print(f"Expected: {anima_log_dir}")
        sys.exit(1)

    # Determine log file
    if date:
        log_file = anima_log_dir / f"{date}.log"
        if not log_file.exists():
            print(f"Error: No log file for date {date}")
            sys.exit(1)
        follow = False
    else:
        # Use current.log symlink or find latest
        current_link = anima_log_dir / "current.log"
        if current_link.exists():
            if current_link.is_symlink():
                log_file = anima_log_dir / current_link.readlink()
            else:
                # Fallback: read text file reference
                target_name = current_link.read_text().strip()
                log_file = anima_log_dir / target_name
        else:
            # Find latest log file
            log_files = sorted(anima_log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not log_files:
                print(f"Error: No log files found in {anima_log_dir}")
                sys.exit(1)
            log_file = log_files[0]

    if not log_file.exists():
        print(f"Error: Log file not found: {log_file}")
        sys.exit(1)

    print(f"{'Tailing' if follow else 'Showing'} log: {log_file}")
    print("-" * 60)

    # Show last N lines
    _show_last_lines(log_file, lines)

    # Follow mode (like tail -f)
    if follow:
        try:
            _follow_file(log_file)
        except KeyboardInterrupt:
            print("\n[Stopped]")


def _tail_all_logs(log_dir: Path, lines: int = 50, follow: bool = False) -> None:
    """Tail all logs (server + all animas)."""
    # Find all anima log directories
    animas_log_dir = log_dir / "animas"

    if not animas_log_dir.exists():
        print("No anima logs found")
        return

    anima_dirs = [d for d in animas_log_dir.iterdir() if d.is_dir()]

    print(f"Monitoring {len(anima_dirs)} anima logs")
    print("-" * 60)

    # Collect all current log files
    log_files = {}

    server_log = log_dir / "animaworks.log"
    if server_log.exists():
        log_files["[SERVER]"] = server_log
    daemon_log = log_dir / "server-daemon.log"
    if daemon_log.exists():
        log_files["[SERVER-DAEMON]"] = daemon_log

    # Anima logs
    for anima_dir in anima_dirs:
        anima_name = anima_dir.name
        current_link = anima_dir / "current.log"

        if current_link.exists():
            if current_link.is_symlink():
                log_file = anima_dir / current_link.readlink()
            else:
                target_name = current_link.read_text().strip()
                log_file = anima_dir / target_name

            if log_file.exists():
                log_files[f"[{anima_name}]"] = log_file

    if not log_files:
        print("No log files found")
        return

    # Show recent lines from each
    for prefix, log_file in log_files.items():
        print(f"\n{prefix} {log_file.name}")
        _show_last_lines(log_file, lines, prefix=prefix)

    if not follow:
        return

    print("\n" + "=" * 60)
    print("Following all logs... (Ctrl+C to stop)")
    print("=" * 60)

    # Follow all files
    try:
        _follow_multiple_files(log_files)
    except KeyboardInterrupt:
        print("\n[Stopped]")


def _show_last_lines(log_file: Path, n: int, prefix: str = "") -> None:
    """Show last N lines of a file."""
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-n:]:
            if prefix:
                print(f"{prefix} {line}")
            else:
                print(line)
    except Exception as e:
        print(f"Error reading {log_file}: {e}")


def _follow_file(log_file: Path) -> None:
    """Follow a single log file (like tail -f)."""
    position = log_file.stat().st_size

    while True:
        try:
            current_size = log_file.stat().st_size
            if current_size < position:
                position = 0
            if current_size > position:
                with open(log_file, encoding="utf-8", errors="replace") as f:
                    f.seek(position)
                    for line in f:
                        print(line.rstrip())
                    position = f.tell()
        except OSError:
            pass
        time.sleep(0.2)


def _follow_multiple_files(log_files: dict[str, Path]) -> None:
    """Follow multiple log files simultaneously."""
    positions: dict[str, int] = {}
    for prefix, log_file in list(log_files.items()):
        try:
            positions[prefix] = log_file.stat().st_size
        except Exception as e:
            print(f"Error opening {log_file}: {e}")

    while True:
        any_output = False

        for prefix, log_file in log_files.items():
            try:
                position = positions.get(prefix, 0)
                current_size = log_file.stat().st_size
                if current_size < position:
                    position = 0
                if current_size > position:
                    with open(log_file, encoding="utf-8", errors="replace") as f:
                        f.seek(position)
                        for line in f:
                            print(f"{prefix} {line.rstrip()}")
                            any_output = True
                        positions[prefix] = f.tell()
            except Exception:
                pass

        if not any_output:
            time.sleep(0.2)
