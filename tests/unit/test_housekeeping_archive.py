from __future__ import annotations

import os
from datetime import UTC, datetime

from core.memory.housekeeping import _rotate_archive_superseded, _rotate_daemon_log


class TestRotateArchiveSuperseded:
    def test_no_animas_dir(self, tmp_path):
        result = _rotate_archive_superseded(tmp_path / "nonexistent", 7)
        assert result == {"skipped": True}

    def test_no_archive_dirs(self, tmp_path):
        animas = tmp_path / "animas"
        (animas / "rin" / "state").mkdir(parents=True)
        result = _rotate_archive_superseded(animas, 7)
        assert result["deleted_files"] == 0

    def test_deletes_old_files(self, tmp_path, monkeypatch):
        animas = tmp_path / "animas"
        archive = animas / "rin" / "archive" / "superseded"
        archive.mkdir(parents=True)

        # Pin both the file mtime and now_local to fixed values so the test is
        # independent of the system clock and os.utime precision on CI runners.
        ref_ts = 1_700_000_000.0  # 2024-11-15 ~06:13 UTC
        fixed_now = datetime.fromtimestamp(ref_ts, tz=UTC)
        monkeypatch.setattr("core.memory.housekeeping.now_local", lambda: fixed_now)

        old_file = archive / "old.md"
        old_file.write_text("old content")
        os.utime(old_file, (ref_ts - 8 * 86400, ref_ts - 8 * 86400))

        new_file = archive / "new.md"
        new_file.write_text("new content")

        result = _rotate_archive_superseded(animas, 7)
        assert result["deleted_files"] == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_keeps_recent_files(self, tmp_path):
        animas = tmp_path / "animas"
        archive = animas / "rin" / "archive" / "superseded"
        archive.mkdir(parents=True)

        recent = archive / "recent.md"
        recent.write_text("recent content")

        result = _rotate_archive_superseded(animas, 7)
        assert result["deleted_files"] == 0
        assert recent.exists()

    def test_multiple_animas(self, tmp_path, monkeypatch):
        ref_ts = 1_700_000_000.0
        fixed_now = datetime.fromtimestamp(ref_ts, tz=UTC)
        monkeypatch.setattr("core.memory.housekeeping.now_local", lambda: fixed_now)

        animas = tmp_path / "animas"
        for name in ("rin", "sakura", "natsume"):
            archive = animas / name / "archive" / "superseded"
            archive.mkdir(parents=True)
            old = archive / "old.md"
            old.write_text("old")
            os.utime(old, (ref_ts - 8 * 86400, ref_ts - 8 * 86400))

        result = _rotate_archive_superseded(animas, 7)
        assert result["deleted_files"] == 3


def test_rotate_daemon_log_copytruncate_preserves_live_append_fd(tmp_path):
    log_path = tmp_path / "server-daemon.log"
    log_path.write_text("old\n", encoding="utf-8")

    with log_path.open("a", encoding="utf-8") as live_fd:
        live_fd.write("before rotate\n")
        live_fd.flush()

        result = _rotate_daemon_log(log_path, max_size_mb=0, keep_generations=3)

        live_fd.write("after rotate\n")
        live_fd.flush()

    assert result["rotated"] is True
    assert (tmp_path / "server-daemon.log.1").read_text(encoding="utf-8") == "old\nbefore rotate\n"
    assert log_path.read_text(encoding="utf-8") == "after rotate\n"
