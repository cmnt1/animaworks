from __future__ import annotations

import os
import time
from pathlib import Path

from core.memory.housekeeping import _rotate_archive_superseded, _rotate_daemon_log


def _stat_with_times(path: Path, *, mtime: float, ctime: float) -> os.stat_result:
    """Build a stat_result whose mtime/ctime match archive-age semantics."""
    st = os.stat(path)
    return os.stat_result(
        (
            st.st_mode,
            st.st_ino,
            st.st_dev,
            st.st_nlink,
            st.st_uid,
            st.st_gid,
            st.st_size,
            mtime,  # st_atime
            mtime,  # st_mtime
            ctime,  # st_ctime — archive entry time after shutil.move
        )
    )


def _patch_archive_ages(monkeypatch, ages: dict[Path, tuple[float, float]]) -> None:
    """Patch Path.stat so *ages* maps path → (mtime, ctime).

    Production ages archive/superseded files by ``max(mtime, ctime)`` because
    ``shutil.move`` preserves mtime while updating ctime.  Linux userspace
    cannot set ctime via ``os.utime`` (it refreshes ctime to "now"), so unit
    tests inject both timestamps through this helper.

    Keys are matched via ``os.path.realpath`` (not ``Path.resolve``), because
    ``Path.resolve`` itself calls ``Path.stat`` and would recurse.
    """
    resolved = {os.path.realpath(p): (mt, ct) for p, (mt, ct) in ages.items()}
    real_stat = Path.stat

    def fake_stat(self: Path, *args, **kwargs):
        key = os.path.realpath(self)
        if key in resolved:
            mtime, ctime = resolved[key]
            return _stat_with_times(self, mtime=mtime, ctime=ctime)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)


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

        old_file = archive / "old.md"
        old_file.write_text("old content")
        new_file = archive / "new.md"
        new_file.write_text("new content")

        now = time.time()
        eight_days_ago = now - (8 * 86400)
        # Both mtime and ctime old → archived long ago → delete.
        _patch_archive_ages(
            monkeypatch,
            {
                old_file: (eight_days_ago, eight_days_ago),
                new_file: (now, now),
            },
        )

        result = _rotate_archive_superseded(animas, 7)
        assert result["deleted_files"] == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_keeps_recently_moved_file_with_old_mtime(self, tmp_path, monkeypatch):
        """Files moved into archive today must not be deleted for old mtime alone.

        ``shutil.move`` preserves the source mtime; ctime advances on the move.
        Age must use max(mtime, ctime) so freshly archived knowledge is kept.
        """
        animas = tmp_path / "animas"
        archive = animas / "rin" / "archive" / "superseded"
        archive.mkdir(parents=True)

        moved = archive / "moved.md"
        moved.write_text("recently archived content")

        now = time.time()
        thirty_days_ago = now - (30 * 86400)
        _patch_archive_ages(monkeypatch, {moved: (thirty_days_ago, now)})

        result = _rotate_archive_superseded(animas, 7)
        assert result["deleted_files"] == 0
        assert moved.exists()

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
        animas = tmp_path / "animas"
        eight_days_ago = time.time() - (8 * 86400)
        ages: dict[Path, tuple[float, float]] = {}
        for name in ("rin", "sakura", "natsume"):
            archive = animas / name / "archive" / "superseded"
            archive.mkdir(parents=True)
            old = archive / "old.md"
            old.write_text("old")
            ages[old] = (eight_days_ago, eight_days_ago)

        _patch_archive_ages(monkeypatch, ages)

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
