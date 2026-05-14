"""Unit tests for cli/commands/memory_cmd.py."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def _make_successful_migrator() -> MagicMock:
    migrator = MagicMock()
    migrator.migrate_anima = AsyncMock(
        return_value={"files": 1, "entities": 2, "facts": 3, "skipped": 0, "errors": 0},
    )
    return migrator


def _migrate_args(*, activate_global: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        target_backend="neo4j",
        migrate_all=False,
        migrate_anima="sakura",
        dry_run=False,
        resume=True,
        activate_global=activate_global,
    )


def test_register_memory_command_parses_activate_global() -> None:
    from cli.commands.memory_cmd import register_memory_command

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    register_memory_command(sub)

    args = parser.parse_args(["memory", "migrate", "--to", "neo4j", "--anima", "sakura", "--activate-global"])

    assert args.memory_command == "migrate"
    assert args.activate_global is True


@patch("core.paths.get_data_dir")
@patch("core.memory.migration.migrator.MemoryMigrator")
@patch("core.memory.migration.checkpoint.CheckpointManager")
@patch("core.config.models.save_config")
@patch("core.config.models.load_config")
@patch("cli.commands.memory_cmd.asyncio.get_event_loop")
def test_migrate_neo4j_does_not_activate_global_by_default(
    mock_loop,
    mock_load_config,
    mock_save_config,
    _mock_checkpoint,
    mock_migrator_cls,
    mock_data_dir,
    tmp_path: Path,
    capsys,
):
    from cli.commands.memory_cmd import _cmd_migrate
    from core.config.schemas import AnimaWorksConfig

    mock_data_dir.return_value = tmp_path
    mock_loop.return_value = "loop"
    cfg = AnimaWorksConfig()
    cfg.memory.backend = "legacy"
    mock_load_config.return_value = cfg
    mock_migrator_cls.return_value = _make_successful_migrator()

    _cmd_migrate(_migrate_args())

    assert cfg.memory.backend == "legacy"
    mock_save_config.assert_not_called()
    captured = capsys.readouterr()
    assert "Global config unchanged: memory.backend = legacy" in captured.out
    assert "migration completed as data preparation only" in captured.out


@patch("core.paths.get_data_dir")
@patch("core.memory.migration.migrator.MemoryMigrator")
@patch("core.memory.migration.checkpoint.CheckpointManager")
@patch("core.config.models.save_config")
@patch("core.config.models.load_config")
@patch("cli.commands.memory_cmd.asyncio.get_event_loop")
def test_migrate_neo4j_activate_global_sets_backend(
    mock_loop,
    mock_load_config,
    mock_save_config,
    _mock_checkpoint,
    mock_migrator_cls,
    mock_data_dir,
    tmp_path: Path,
    capsys,
):
    from cli.commands.memory_cmd import _cmd_migrate
    from core.config.schemas import AnimaWorksConfig

    mock_data_dir.return_value = tmp_path
    mock_loop.return_value = "loop"
    cfg = AnimaWorksConfig()
    cfg.memory.backend = "legacy"
    mock_load_config.return_value = cfg
    mock_migrator_cls.return_value = _make_successful_migrator()

    _cmd_migrate(_migrate_args(activate_global=True))

    assert cfg.memory.backend == "neo4j"
    mock_save_config.assert_called_once_with(cfg)
    captured = capsys.readouterr()
    assert "Config updated: memory.backend = neo4j" in captured.out
    assert "experimental/opt-in" in captured.out


@patch("core.paths.get_data_dir")
@patch("core.memory.migration.backup.BackupManager")
@patch("core.config.models.load_config")
def test_status_prints_backend_policy_and_per_anima_overrides(
    mock_load_config,
    mock_backup_cls,
    mock_data_dir,
    tmp_path: Path,
    capsys,
):
    from cli.commands.memory_cmd import _cmd_status
    from core.config.schemas import AnimaWorksConfig

    data_dir = tmp_path / ".animaworks"
    animas_dir = data_dir / "animas"
    sakura_dir = animas_dir / "sakura"
    hinata_dir = animas_dir / "hinata"
    sakura_dir.mkdir(parents=True)
    hinata_dir.mkdir()
    (sakura_dir / "status.json").write_text(json.dumps({"memory_backend": "neo4j"}), encoding="utf-8")
    (hinata_dir / "status.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")

    cfg = AnimaWorksConfig()
    cfg.memory.backend = "legacy"
    mock_load_config.return_value = cfg
    mock_data_dir.return_value = data_dir
    mock_backup_cls.return_value.list_backups.return_value = []

    _cmd_status()

    captured = capsys.readouterr()
    assert "Memory Backend: legacy (stable/default)" in captured.out
    assert "Policy: legacy is stable/default; neo4j is experimental opt-in." in captured.out
    assert "Per-Anima Memory Backend Overrides:" in captured.out
    assert "sakura: neo4j (experimental/opt-in)" in captured.out
