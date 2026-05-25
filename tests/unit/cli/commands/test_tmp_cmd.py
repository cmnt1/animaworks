from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for cli/commands/tmp_cmd.py."""

import argparse
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from cli.commands import tmp_cmd


def _capture_stdout(func, args: argparse.Namespace) -> str:
    buffer = StringIO()
    with patch("sys.stdout", buffer):
        func(args)
    return buffer.getvalue()


def _capture_exit(func, args: argparse.Namespace) -> tuple[int | None, str]:
    buffer = StringIO()
    with patch("sys.stdout", buffer):
        with pytest.raises(SystemExit) as exc:
            func(args)
        code = exc.value.code
    return code, buffer.getvalue()


class TestTmpCmd:
    def test_list_shows_summary(self, tmp_path: Path):
        data_dir = tmp_path / ".animaworks"
        tmp_root = data_dir / "tmp"
        tmp_root.mkdir(parents=True)
        (tmp_root / "sample.txt").write_text("hello", encoding="utf-8")

        args = argparse.Namespace(project=False, top=10)
        with patch("core.tmp_cleanup.get_data_dir", return_value=data_dir):
            output = _capture_stdout(tmp_cmd.cmd_tmp_list, args)

        assert "sample.txt" in output

    def test_clean_requires_force_for_all(self):
        args = argparse.Namespace(
            all=True,
            force=False,
            project=False,
            dry_run=False,
            older_than=7,
            min_size=None,
        )
        with pytest.raises(SystemExit) as exc, patch("sys.stderr", new=StringIO()):
            tmp_cmd.cmd_tmp_clean(args)
        assert exc.value.code == 2

    def test_clean_dry_run(self, tmp_path: Path):
        data_dir = tmp_path / ".animaworks"
        tmp_root = data_dir / "tmp"
        tmp_root.mkdir(parents=True)
        target = tmp_root / "old.txt"
        target.write_text("old", encoding="utf-8")
        old_mtime = 1_000_000_000.0
        import os

        os.utime(target, (old_mtime, old_mtime))

        args = argparse.Namespace(
            all=False,
            force=False,
            project=False,
            dry_run=True,
            older_than=7,
            min_size=None,
        )
        with patch("core.tmp_cleanup.get_data_dir", return_value=data_dir):
            code, output = _capture_exit(tmp_cmd.cmd_tmp_clean, args)

        assert code == 0
        assert "DRY RUN" in output or "削除対象" in output
        assert target.exists()
