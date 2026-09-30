from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core/infra/tmp_cleanup.py."""

from pathlib import Path

import pytest

from core.infra.tmp_cleanup import (
    clean_tmp_dir,
    format_size,
    parse_size,
    scan_tmp_dir,
    select_clean_candidates,
)


class TestParseSize:
    def test_bytes(self):
        assert parse_size("512") == 512

    def test_megabytes(self):
        assert parse_size("100M") == 100 * 1024 * 1024

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_size("big")


class TestFormatSize:
    def test_bytes(self):
        assert format_size(512) == "512B"

    def test_megabytes(self):
        assert format_size(1024 * 1024) == "1.0MB"


class TestTmpCleanup:
    @pytest.fixture(autouse=True)
    def _runtime_data_dir(self, data_dir_at_tmp_path: Path) -> None:
        """Use the real path accessor with the test's temporary root."""

    def test_scan_and_clean_old_entries(self, tmp_path: Path):
        data_dir = tmp_path
        tmp_root = data_dir / "tmp"
        tmp_root.mkdir(parents=True)
        old_file = tmp_root / "old.txt"
        old_file.write_text("old", encoding="utf-8")
        old_mtime = 1_000_000_000.0
        old_file.touch()
        import os

        os.utime(old_file, (old_mtime, old_mtime))

        new_file = tmp_root / "new.txt"
        new_file.write_text("new", encoding="utf-8")

        scan = scan_tmp_dir(tmp_root)
        assert scan.entry_count == 2
        assert scan.total_bytes > 0

        candidates = select_clean_candidates(tmp_root, older_than_days=7)
        assert [entry.path.name for entry in candidates] == ["old.txt"]

        result = clean_tmp_dir(tmp_root, older_than_days=7)
        assert result.removed_count == 1
        assert new_file.exists()
        assert not old_file.exists()
        assert (tmp_root / "attachments").is_dir()

    def test_clean_all_requires_force_flag_in_cli_only(self, tmp_path: Path):
        data_dir = tmp_path
        tmp_root = data_dir / "tmp"
        tmp_root.mkdir(parents=True)
        target = tmp_root / "large.json"
        target.write_text("x" * 1024, encoding="utf-8")

        result = clean_tmp_dir(tmp_root, clean_all=True)
        assert result.removed_count == 1
        assert not target.exists()
        assert (tmp_root / "attachments").is_dir()

    def test_dry_run_does_not_delete(self, tmp_path: Path):
        data_dir = tmp_path
        tmp_root = data_dir / "tmp"
        tmp_root.mkdir(parents=True)
        target = tmp_root / "keep.txt"
        target.write_text("keep", encoding="utf-8")

        result = clean_tmp_dir(tmp_root, clean_all=True, dry_run=True)
        assert result.removed_count == 1
        assert target.exists()

    def test_min_size_filter(self, tmp_path: Path):
        data_dir = tmp_path
        tmp_root = data_dir / "tmp"
        tmp_root.mkdir(parents=True)
        small = tmp_root / "small.txt"
        small.write_text("a", encoding="utf-8")
        large = tmp_root / "large.bin"
        large.write_bytes(b"x" * 2048)

        candidates = select_clean_candidates(tmp_root, older_than_days=None, min_size_bytes=1024)
        assert [entry.path.name for entry in candidates] == ["large.bin"]
