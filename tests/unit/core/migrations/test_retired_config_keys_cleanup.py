from __future__ import annotations

import json
from pathlib import Path

from core.config import load_config
from core.migrations.registry import MigrationRunner
from core.migrations.steps import register_all_steps, step_retired_config_keys_cleanup

_RETIRABLE_CONFIG = {
    "heartbeat": {
        "orphan_grace_multiplier": 4.0,
        "orphan_grace_min_seconds": 2400,
        "interval_minutes": 45,
    },
    "background_task": {"max_parallel_llm_tasks": 4, "enabled": True},
    "rag": {"enable_file_watcher": False, "embedding_model": "keep-this-model"},
    "interaction": {"ttl_days": 14, "web_base_url": "https://example.test"},
    "system": {
        "gateway": {"host": "127.0.0.1", "port": 19000},
        "worker": {"gateway_url": "http://127.0.0.1:19000"},
        "mode": "server",
    },
    "locale": "ja",
}


def _write_config(path: Path) -> str:
    original = json.dumps(_RETIRABLE_CONFIG, ensure_ascii=False, indent=2) + "\n"
    path.write_text(original, encoding="utf-8")
    return original


def test_cleanup_dry_run_does_not_modify_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    original = _write_config(config_path)

    result = step_retired_config_keys_cleanup(tmp_path, dry_run=True, verbose=False)

    assert result.changed == 1
    assert result.error is None
    assert "Would remove retired config keys" in result.details[0]
    assert config_path.read_text(encoding="utf-8") == original


def test_cleanup_removes_only_retired_keys_and_is_idempotent(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    _write_config(config_path)

    result = step_retired_config_keys_cleanup(tmp_path, dry_run=False, verbose=False)

    assert result.changed == 1
    assert result.error is None
    for key in (
        "heartbeat.orphan_grace_multiplier",
        "heartbeat.orphan_grace_min_seconds",
        "background_task.max_parallel_llm_tasks",
        "rag.enable_file_watcher",
        "interaction.ttl_days",
        "system.gateway",
        "system.worker",
    ):
        assert key in result.details[0]
    cleaned = json.loads(config_path.read_text(encoding="utf-8"))
    assert cleaned == {
        "heartbeat": {"interval_minutes": 45},
        "background_task": {"enabled": True},
        "rag": {"embedding_model": "keep-this-model"},
        "interaction": {"web_base_url": "https://example.test"},
        "system": {"mode": "server"},
        "locale": "ja",
    }

    second_result = step_retired_config_keys_cleanup(tmp_path, dry_run=False, verbose=False)
    assert second_result.changed == 0
    assert second_result.skipped == 1

    loaded = load_config(config_path)
    assert loaded.system.mode == "server"
    assert loaded.heartbeat.interval_minutes == 45
    assert loaded.background_task.enabled is True
    assert loaded.rag.embedding_model == "keep-this-model"
    assert loaded.interaction.web_base_url == "https://example.test"
    assert not hasattr(loaded.system, "gateway")
    assert not hasattr(loaded.system, "worker")


def test_cleanup_step_is_registered_after_its_dependency_and_before_version(tmp_path: Path) -> None:
    runner = MigrationRunner(tmp_path)
    register_all_steps(runner)
    ids = [step["id"] for step in runner.list_steps()]

    assert ids.index("usage_governor_cleanup_20260927") < ids.index("retired_config_keys_cleanup_20260927")
    assert ids.index("retired_config_keys_cleanup_20260927") < ids.index("update_version")
