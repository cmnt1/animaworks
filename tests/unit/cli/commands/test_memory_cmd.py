"""Unit tests for memory backend CLI operations."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


class FakeBackend:
    def __init__(
        self,
        *,
        driver: FakeDriver | None = None,
        group_id: str = "sakura",
        health: bool = True,
        stats: dict[str, int] | None = None,
    ) -> None:
        self._driver = driver
        self._group_id = group_id
        self._health = health
        self._stats = stats or {"nodes_Entity": 7}
        self.closed = False
        self.reset_called = False

    async def health_check(self) -> bool:
        return self._health

    async def stats(self) -> dict[str, int]:
        return self._stats

    async def reset(self) -> None:
        self.reset_called = True

    async def close(self) -> None:
        self.closed = True

    async def _ensure_driver(self) -> FakeDriver:
        assert self._driver is not None
        return self._driver


class FakeDriver:
    def __init__(self, episode_rows: list[dict[str, str]], orphan_rows: list[dict[str, str]] | None = None) -> None:
        self.episode_rows = episode_rows
        self.orphan_rows = orphan_rows or []
        self.queries: list[tuple[str, dict]] = []
        self.writes: list[tuple[str, dict]] = []

    async def execute_query(self, query: str, parameters: dict) -> list[dict[str, str]]:
        self.queries.append((query, parameters))
        if query.lstrip().startswith("MATCH (ep:Episode)"):
            return self.episode_rows
        if query.lstrip().startswith("MATCH (e:Entity)"):
            return self.orphan_rows
        return []

    async def execute_write(self, query: str, parameters: dict) -> None:
        self.writes.append((query, parameters))


def _config(*, backend: str = "legacy", password: str = "super-secret") -> SimpleNamespace:
    return SimpleNamespace(
        memory=SimpleNamespace(
            backend=backend,
            neo4j=SimpleNamespace(
                uri="bolt://neo4j.local:7687",
                user="neo4j",
                password=password,
                database="animaworks",
            ),
        ),
    )


def _make_anima(animas_dir: Path, name: str, *, backend: str | None = None) -> Path:
    anima_dir = animas_dir / name
    anima_dir.mkdir(parents=True)
    if backend is not None:
        (anima_dir / "status.json").write_text(json.dumps({"memory_backend": backend}), encoding="utf-8")
    return anima_dir


def test_status_parser_accepts_anima_and_json() -> None:
    from cli.commands.memory_cmd import register_memory_command

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    register_memory_command(subparsers)

    args = parser.parse_args(["memory", "status", "--anima", "sakura", "--json"])

    assert args.memory_command == "status"
    assert args.status_anima == "sakura"
    assert args.json_output is True


def test_status_json_reports_effective_neo4j_without_password(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from cli.commands.memory_cmd import _cmd_status

    data_dir = tmp_path / "data"
    animas_dir = data_dir / "animas"
    _make_anima(animas_dir, "sakura", backend="neo4j")
    backend = FakeBackend(stats={"nodes_Entity": 1473, "edges_MENTIONS": 8})

    with (
        patch("core.config.models.load_config", return_value=_config()),
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.paths.get_animas_dir", return_value=animas_dir),
        patch("core.memory.migration.backup.BackupManager") as backup_manager,
        patch("core.memory.backend.registry.get_backend", return_value=backend),
    ):
        backup_manager.return_value.list_backups.return_value = []
        _cmd_status(argparse.Namespace(status_anima="sakura", all_animas=False, json_output=True))

    output = capsys.readouterr().out
    payload = json.loads(output)
    anima = payload["animas"][0]
    assert payload["global_backend"] == "legacy"
    assert payload["neo4j"] == {"uri": "bolt://neo4j.local:7687", "database": "animaworks"}
    assert anima["name"] == "sakura"
    assert anima["effective_backend"] == "neo4j"
    assert anima["source"] == "per-anima"
    assert anima["health"] is True
    assert anima["stats"]["nodes_Entity"] == 1473
    assert "password" not in output
    assert "super-secret" not in output
    assert backend.closed is True


def test_status_all_animas_includes_global_and_per_anima_backends(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from cli.commands.memory_cmd import _cmd_status

    data_dir = tmp_path / "data"
    animas_dir = data_dir / "animas"
    _make_anima(animas_dir, "legacy-bot")
    _make_anima(animas_dir, "sakura", backend="neo4j")

    with (
        patch("core.config.models.load_config", return_value=_config()),
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.paths.get_animas_dir", return_value=animas_dir),
        patch("core.memory.migration.backup.BackupManager") as backup_manager,
        patch("core.memory.backend.registry.get_backend", return_value=FakeBackend()),
    ):
        backup_manager.return_value.list_backups.return_value = []
        _cmd_status(argparse.Namespace(status_anima=None, all_animas=True, json_output=False))

    output = capsys.readouterr().out
    assert "Memory Backend (global): legacy" in output
    assert "Neo4j URI: bolt://neo4j.local:7687" in output
    assert "legacy-bot: legacy (global)" in output
    assert "sakura: neo4j (per-anima) health=ok" in output
    assert "Effective Backends: legacy=1, neo4j=1" in output


def test_status_neo4j_diagnostic_does_not_crash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from cli.commands.memory_cmd import _cmd_status

    data_dir = tmp_path / "data"
    animas_dir = data_dir / "animas"
    _make_anima(animas_dir, "sakura", backend="neo4j")

    with (
        patch("core.config.models.load_config", return_value=_config()),
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.paths.get_animas_dir", return_value=animas_dir),
        patch("core.memory.migration.backup.BackupManager") as backup_manager,
        patch("core.memory.backend.registry.get_backend", side_effect=ImportError("Neo4j driver not installed")),
    ):
        backup_manager.return_value.list_backups.return_value = []
        _cmd_status(argparse.Namespace(status_anima="sakura", all_animas=False, json_output=True))

    anima = json.loads(capsys.readouterr().out)["animas"][0]
    assert anima["health"] is False
    assert anima["stats"] == {}
    assert "Neo4j driver not installed" in anima["diagnostic"]


def test_rollback_purge_resets_only_restored_anima_dirs(tmp_path: Path) -> None:
    from cli.commands.memory_cmd import _cmd_rollback

    data_dir = tmp_path / "data"
    animas_dir = data_dir / "animas"
    _make_anima(animas_dir, "rin")
    _make_anima(animas_dir, "sakura")
    (data_dir / "benchmarks" / "locomo").mkdir(parents=True)
    cfg = _config(backend="neo4j")
    backends: dict[str, FakeBackend] = {}

    def get_backend(_backend_type: str, anima_dir: Path) -> FakeBackend:
        backend = FakeBackend(group_id=anima_dir.name)
        backends[anima_dir.name] = backend
        return backend

    with (
        patch("core.paths.get_data_dir", return_value=data_dir),
        patch("core.memory.migration.backup.BackupManager") as backup_manager,
        patch("core.config.models.load_config", return_value=cfg),
        patch("core.config.models.save_config") as save_config,
        patch("core.memory.backend.registry.get_backend", side_effect=get_backend),
    ):
        _cmd_rollback(argparse.Namespace(backup_name="pre-migration", purge_neo4j=True))

    backup_manager.return_value.restore.assert_called_once_with("pre-migration")
    save_config.assert_called_once_with(cfg)
    assert cfg.memory.backend == "legacy"
    assert set(backends) == {"rin", "sakura"}
    assert all(backend.reset_called for backend in backends.values())
    assert all(backend.closed for backend in backends.values())


def test_cleanup_dry_run_reports_counts_without_mutation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from cli.commands.memory_ops import run_cleanup

    driver = FakeDriver(
        [{"uuid": "episode-1"}, {"uuid": "episode-2"}],
        [{"uuid": "entity-1"}],
    )
    backend = FakeBackend(driver=driver)

    with patch("core.memory.backend.registry.get_backend", return_value=backend):
        asyncio.run(run_cleanup(tmp_path / "sakura", "episodes/", include_orphans=True, dry_run=True))

    output = capsys.readouterr().out
    assert "Episodes matching source prefix 'episodes/': 2" in output
    assert "Orphaned entities after episode cleanup: 1" in output
    assert driver.writes == []
    assert all("DETACH DELETE" not in query for query, _params in driver.queries)
    assert backend.closed is True


def test_cleanup_soft_deletes_episodes_and_orphan_entities(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from cli.commands.memory_ops import run_cleanup

    driver = FakeDriver(
        [{"uuid": "episode-1"}, {"uuid": "episode-2"}],
        [{"uuid": "entity-1"}],
    )
    backend = FakeBackend(driver=driver)

    with patch("core.memory.backend.registry.get_backend", return_value=backend):
        asyncio.run(run_cleanup(tmp_path / "sakura", "episodes/", include_orphans=True, dry_run=False))

    output = capsys.readouterr().out
    assert "Soft-deleted 2 episodes" in output
    assert "Soft-deleted 1 orphaned entities" in output
    assert len(driver.writes) == 2
    episode_query, episode_params = driver.writes[0]
    entity_query, entity_params = driver.writes[1]
    assert "SET ep.deleted_at" in episode_query
    assert "DELETE m" in episode_query
    assert episode_params["episode_uuids"] == ["episode-1", "episode-2"]
    assert "SET e.deleted_at" in entity_query
    assert entity_params["entity_uuids"] == ["entity-1"]
    all_cypher = "\n".join(query for query, _params in [*driver.queries, *driver.writes])
    assert "DETACH DELETE" not in all_cypher
    assert backend.closed is True
