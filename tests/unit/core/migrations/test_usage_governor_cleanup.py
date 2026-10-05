from __future__ import annotations

import json
from pathlib import Path

from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_usage_governor_cleanup


def test_cleanup_dry_run_preserves_config_and_state_files(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"server": {"usage_governor": {"enabled": True}, "port": 18500}, "locale": "ja"}),
        encoding="utf-8",
    )
    state_paths = [tmp_path / "usage_governor_state.json", tmp_path / "usage_policy.json"]
    for path in state_paths:
        path.write_text(f"{path.name} data\n", encoding="utf-8")
    config_before = config_path.read_bytes()
    states_before = [path.read_bytes() for path in state_paths]

    result = step_usage_governor_cleanup(tmp_path, dry_run=True, verbose=False)

    assert result.error is None
    assert result.changed == 0
    assert config_path.read_bytes() == config_before
    assert [path.read_bytes() for path in state_paths] == states_before
    assert not (tmp_path / "archive" / "retired").exists()


def test_cleanup_preserves_fork_governor_idempotently(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"server": {"usage_governor": {"enabled": True}, "port": 18500}, "locale": "ja"}),
        encoding="utf-8",
    )
    state_contents = {
        "usage_governor_state.json": '{"suspended_animas": ["alice"]}\n',
        "usage_policy.json": '{"daily_limit": 10}\n',
    }
    for filename, content in state_contents.items():
        (tmp_path / filename).write_text(content, encoding="utf-8")

    config_before = config_path.read_bytes()
    result = step_usage_governor_cleanup(tmp_path, dry_run=False, verbose=False)

    assert result.error is None
    assert result.changed == 0
    assert config_path.read_bytes() == config_before
    for filename, content in state_contents.items():
        source = tmp_path / filename
        archived = tmp_path / "archive" / "retired" / filename
        assert source.read_text(encoding="utf-8") == content
        assert not archived.exists()

    second = step_usage_governor_cleanup(tmp_path, dry_run=False, verbose=False)
    assert second.error is None
    assert second.changed == 0


def test_cleanup_is_registered_before_update_version(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    ids = [step["id"] for step in runner.list_steps()]

    assert ids.index("usage_governor_cleanup_20260927") < ids.index("update_version")
