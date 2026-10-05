from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI

from core.config.schemas import AnimaWorksConfig
from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps


@pytest.mark.asyncio
async def test_governor_suspension_survives_reconciliation_and_resumes(tmp_path):
    import json

    from server.supervisor.manager import ProcessSupervisor
    from server.usage_governor import UsageGovernor

    animas = tmp_path / "animas"
    alice = animas / "alice"
    alice.mkdir(parents=True)
    (alice / "identity.md").write_text("# Alice", encoding="utf-8")
    status = {"enabled": True, "restart_requested": True}
    (alice / "status.json").write_text(json.dumps(status), encoding="utf-8")
    (tmp_path / "config.json").write_text('{"animas": {"alice": {}}}', encoding="utf-8")
    supervisor = ProcessSupervisor(animas, tmp_path / "shared", tmp_path / "run")
    governor = UsageGovernor(SimpleNamespace(state=SimpleNamespace(supervisor=supervisor)), tmp_path, animas)
    await governor._apply_suspensions({"alice"})
    with (
        patch.object(supervisor, "start_anima", new_callable=AsyncMock) as start,
        patch.object(supervisor, "restart_anima", new_callable=AsyncMock) as restart,
        patch.object(supervisor, "_check_config_freshness"),
    ):
        await supervisor._reconcile()
        start.assert_not_awaited()
        restart.assert_not_awaited()
        assert json.loads((alice / "status.json").read_text(encoding="utf-8")) == status
        await governor._apply_suspensions(set())
        start.assert_awaited_once_with("alice")
        assert not supervisor._governor_suspended

    supervisor._governor_suspended = {"alice"}
    with patch("server.supervisor.manager.ProcessHandle") as handle:
        await supervisor.start_anima("alice")
        handle.assert_not_called()


@pytest.mark.asyncio
async def test_governor_starts_once_after_runtime_is_available(tmp_path):
    from server.app import _start_usage_governor_if_enabled

    app = FastAPI()
    app.state.animas_dir = tmp_path / "animas"
    app.state.supervisor = SimpleNamespace()
    config = AnimaWorksConfig.model_validate({"server": {"usage_governor": {"enabled": True}}})
    governor = SimpleNamespace(start=AsyncMock())
    with (
        patch("server.app.load_config", return_value=config),
        patch("core.paths.get_data_dir", return_value=tmp_path),
        patch("server.usage_governor.UsageGovernor", return_value=governor) as factory,
    ):
        await _start_usage_governor_if_enabled(app)
        await _start_usage_governor_if_enabled(app)

    factory.assert_called_once_with(app, tmp_path, app.state.animas_dir)
    governor.start.assert_awaited_once()
    assert app.state.usage_governor is governor


def test_forced_registered_migration_keeps_governor_files(tmp_path):
    import json

    config = {"server": {"usage_governor": {"enabled": True}}, "locale": "ja"}
    paths = {
        "config.json": json.dumps(config),
        "usage_policy.json": '{"hard_floor_activity_level": 10}',
        "usage_governor_state.json": '{"suspended_animas": ["alice"]}',
        "usage_governor_history.json": '{"claude": []}',
    }
    for name, text in paths.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    for _ in range(2):
        report = runner._run(
            [step for step in runner._steps if step.id == "usage_governor_cleanup_20260927"],
            dry_run=False, verbose=False, force=True,
        )
        assert not report.errors
        for name, text in paths.items():
            assert (tmp_path / name).read_text(encoding="utf-8") == text


def test_background_activity_still_follows_governor_provider(tmp_path):
    import json

    from core.runtime.scheduler_manager import _read_governor_background_activity_level

    anima = tmp_path / "animas" / "alice"
    anima.mkdir(parents=True)
    (anima / "status.json").write_text(
        json.dumps({"credential": "anthropic", "background_credential": "openai"}), encoding="utf-8"
    )
    (tmp_path / "usage_governor_state.json").write_text(
        json.dumps({"background_activity_level_by_provider": {"claude": 20, "openai": 80}}), encoding="utf-8"
    )
    with patch("core.paths.get_data_dir", return_value=tmp_path):
        assert _read_governor_background_activity_level(anima) == 80


def test_full_v015_migration_preserves_governor_and_anima_content(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    anima = tmp_path / "animas" / "alice"
    anima.mkdir(parents=True)
    config = {"server": {"usage_governor": {"enabled": True}}, "locale": "ja"}
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (anima / "status.json").write_text(
        json.dumps({"enabled": True, "model": "codex/gpt-5.4", "process_model": "legacy"}), encoding="utf-8"
    )
    identity = "# Alice\nUser-managed identity remains intact.\n"
    (anima / "identity.md").write_text(identity, encoding="utf-8")
    governor_files = {
        "usage_policy.json": '{"hard_floor_activity_level": 10}',
        "usage_governor_state.json": '{"front_activity_level_by_provider": {"openai": 40}}',
        "usage_governor_history.json": '{"openai": []}',
    }
    for name, content in governor_files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    for _ in range(2):
        report = runner.run_all()
        assert not report.errors
        assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["server"]["usage_governor"]["enabled"]
        assert "process_model" not in json.loads((anima / "status.json").read_text(encoding="utf-8"))
        assert (anima / "identity.md").read_text(encoding="utf-8") == identity
        for name, content in governor_files.items():
            assert (tmp_path / name).read_text(encoding="utf-8") == content
