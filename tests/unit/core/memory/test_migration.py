from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.memory.migration.backup import BackupManager
from core.memory.migration.checkpoint import CheckpointManager
from core.memory.migration.migrator import MemoryMigrator


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Create a minimal data directory structure."""
    animas = tmp_path / "animas"
    (animas / "sakura" / "knowledge").mkdir(parents=True)
    (animas / "sakura" / "episodes").mkdir(parents=True)
    (animas / "sakura" / "knowledge" / "test1.md").write_text("# Test\nContent1")
    (animas / "sakura" / "knowledge" / "test2.md").write_text("# Test2\nContent2")
    (animas / "sakura" / "episodes" / "2026-04-22.md").write_text(
        "# Episode\nSomething happened"
    )
    return tmp_path


# ── TestBackupManager ──────────────────────────────────────────


class TestBackupManager:
    def test_create_backup(self, data_dir: Path) -> None:
        bm = BackupManager(data_dir)
        backup_path = bm.create()

        assert backup_path.is_dir()
        tar_files = list(backup_path.glob("*.tar.gz"))
        assert len(tar_files) >= 1
        assert (backup_path / "manifest.json").exists()

        manifest = json.loads(
            (backup_path / "manifest.json").read_text(encoding="utf-8")
        )
        for tar in tar_files:
            assert tar.name in manifest

    def test_create_backup_with_config(self, data_dir: Path) -> None:
        (data_dir / "config.json").write_text('{"memory": "legacy"}')

        bm = BackupManager(data_dir)
        backup_path = bm.create()

        assert (backup_path / "config.json").exists()
        restored = json.loads(
            (backup_path / "config.json").read_text(encoding="utf-8")
        )
        assert restored["memory"] == "legacy"

    def test_restore_backup(self, data_dir: Path) -> None:
        bm = BackupManager(data_dir)
        backup_path = bm.create(label="restore-test")

        orig = (data_dir / "animas" / "sakura" / "knowledge" / "test1.md").read_text()
        (data_dir / "animas" / "sakura" / "knowledge" / "test1.md").write_text(
            "MODIFIED"
        )
        assert (
            data_dir / "animas" / "sakura" / "knowledge" / "test1.md"
        ).read_text() == "MODIFIED"

        bm.restore(backup_path.name)

        restored = (
            data_dir / "animas" / "sakura" / "knowledge" / "test1.md"
        ).read_text()
        assert restored == orig

    def test_restore_verifies_manifest(self, data_dir: Path) -> None:
        bm = BackupManager(data_dir)
        backup_path = bm.create()

        tar_files = list(backup_path.glob("*.tar.gz"))
        assert tar_files
        with open(tar_files[0], "ab") as f:
            f.write(b"CORRUPTION")

        with pytest.raises(ValueError, match="SHA256 mismatch"):
            bm.restore(backup_path.name)

    def test_restore_missing_backup(self, data_dir: Path) -> None:
        bm = BackupManager(data_dir)
        with pytest.raises(FileNotFoundError, match="Backup not found"):
            bm.restore("memory-nonexistent-000000")

    def test_list_backups(self, data_dir: Path) -> None:
        bm = BackupManager(data_dir)
        bm.create(label="first")
        bm.create(label="second")

        backups = bm.list_backups()
        assert len(backups) == 2
        names = [b["name"] for b in backups]
        assert any("first" in n for n in names)
        assert any("second" in n for n in names)

    def test_list_backups_empty(self, data_dir: Path) -> None:
        bm = BackupManager(data_dir)
        assert bm.list_backups() == []


# ── TestCheckpointManager ──────────────────────────────────────


class TestCheckpointManager:
    def test_mark_done(self, tmp_path: Path) -> None:
        cm = CheckpointManager(tmp_path / "ckpt.jsonl")
        cm.mark_done("key1")
        assert cm.is_done("key1") is True

    def test_not_done(self, tmp_path: Path) -> None:
        cm = CheckpointManager(tmp_path / "ckpt.jsonl")
        assert cm.is_done("key2") is False

    def test_resume_from_file(self, tmp_path: Path) -> None:
        ckpt_path = tmp_path / "ckpt.jsonl"

        cm1 = CheckpointManager(ckpt_path)
        cm1.mark_done("resume1", anima="sakura", file="test.md")
        cm1.mark_done("resume2", anima="sakura", file="test2.md")

        cm2 = CheckpointManager(ckpt_path)
        assert cm2.is_done("resume1") is True
        assert cm2.is_done("resume2") is True
        assert cm2.completed_count == 2

    def test_mark_error(self, tmp_path: Path) -> None:
        cm = CheckpointManager(tmp_path / "ckpt.jsonl")
        cm.mark_error("err_key", "some error")
        assert cm.is_done("err_key") is False

    def test_reset(self, tmp_path: Path) -> None:
        ckpt_path = tmp_path / "ckpt.jsonl"
        cm = CheckpointManager(ckpt_path)
        cm.mark_done("a")
        cm.mark_done("b")
        assert cm.is_done("a") is True

        cm.reset()
        assert cm.is_done("a") is False
        assert cm.is_done("b") is False
        assert cm.completed_count == 0

    def test_completed_count(self, tmp_path: Path) -> None:
        cm = CheckpointManager(tmp_path / "ckpt.jsonl")
        cm.mark_done("x1")
        cm.mark_done("x2")
        cm.mark_done("x3")
        assert cm.completed_count == 3


# ── TestMemoryMigrator ─────────────────────────────────────────


class TestMemoryMigrator:
    def test_list_animas(self, tmp_path: Path) -> None:
        animas = tmp_path / "animas"
        for name in ("a", "b", "c"):
            (animas / name).mkdir(parents=True)
        migrator = MemoryMigrator(tmp_path)
        assert migrator.list_animas() == ["a", "b", "c"]

    def test_count_files(self, data_dir: Path) -> None:
        migrator = MemoryMigrator(data_dir)
        counts = migrator.count_files("sakura")
        assert counts["knowledge"] == 2
        assert counts["episodes"] == 1

    def test_estimate_cost(self, data_dir: Path) -> None:
        migrator = MemoryMigrator(data_dir)
        est = migrator.estimate_cost("sakura")
        assert "estimated_files" in est
        assert "estimated_llm_calls" in est
        assert est["estimated_files"] == 3
        assert est["estimated_llm_calls"] == 6

    @pytest.mark.asyncio
    async def test_migrate_anima_with_mock_backend(self, data_dir: Path) -> None:
        mock_backend = AsyncMock()
        mock_backend.ingest_file = AsyncMock(return_value=5)
        mock_backend.close = AsyncMock()

        migrator = MemoryMigrator(data_dir)

        with patch(
            "core.memory.backend.registry.get_backend",
            return_value=mock_backend,
        ):
            stats = await migrator.migrate_anima("sakura")

        assert stats["files"] == 3
        assert stats["errors"] == 0
        assert mock_backend.ingest_file.call_count == 3

    @pytest.mark.asyncio
    async def test_migrate_anima_with_checkpoint_skip(
        self, data_dir: Path, tmp_path: Path
    ) -> None:
        cm = CheckpointManager(tmp_path / "ckpt.jsonl")
        cm.mark_done("sakura:knowledge/test1.md")
        cm.mark_done("sakura:episodes/2026-04-22.md")

        mock_backend = AsyncMock()
        mock_backend.ingest_file = AsyncMock(return_value=1)
        mock_backend.close = AsyncMock()

        migrator = MemoryMigrator(data_dir)

        with patch(
            "core.memory.backend.registry.get_backend",
            return_value=mock_backend,
        ):
            stats = await migrator.migrate_anima(
                "sakura", checkpoint_manager=cm
            )

        assert stats["skipped"] == 2
        assert stats["files"] == 1
        assert mock_backend.ingest_file.call_count == 1

    @pytest.mark.asyncio
    async def test_migrate_anima_records_errors(self, data_dir: Path) -> None:
        mock_backend = AsyncMock()
        mock_backend.ingest_file = AsyncMock(
            side_effect=RuntimeError("Neo4j connection failed")
        )
        mock_backend.close = AsyncMock()

        migrator = MemoryMigrator(data_dir)

        with patch(
            "core.memory.backend.registry.get_backend",
            return_value=mock_backend,
        ):
            stats = await migrator.migrate_anima("sakura")

        assert stats["errors"] == 3
        assert stats["files"] == 0


# ── TestMemoryCLIRegister ──────────────────────────────────────


class TestMemoryCLIRegister:
    def test_register_adds_memory_parser(self) -> None:
        from cli.commands.memory_cmd import register_memory_command

        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_memory_command(sub)

        args = parser.parse_args(["memory", "status"])
        assert args.command == "memory"
        assert args.memory_command == "status"
