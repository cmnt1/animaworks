from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest


def _increment_status(path: str, key: str) -> None:
    from core.platform.status_store import update_status

    anima_dir = Path(path)
    for _ in range(50):
        update_status(anima_dir, lambda status: status.__setitem__(key, status.get(key, 0) + 1))


def _append_config_alias(path: str, anima_name: str) -> None:
    from core.config.io import update_config
    from core.config.schemas import AnimaModelConfig

    config_path = Path(path)
    for _ in range(50):

        def append_alias(config):
            anima = config.animas.setdefault(anima_name, AnimaModelConfig())
            anima.aliases.append(anima_name)

        update_config(append_alias, config_path)


def _run_two_process_updates(target: Path, worker, *args: str) -> None:
    context = multiprocessing.get_context("spawn")
    processes = [context.Process(target=worker, args=(str(target), key)) for key in args]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=60)
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            pytest.fail("update worker did not finish within 60 seconds")
        assert process.exitcode == 0


def test_update_status_serializes_concurrent_processes(tmp_path: Path) -> None:
    from core.platform.status_store import read_status

    anima_dir = tmp_path / "anima"
    _run_two_process_updates(anima_dir, _increment_status, "first", "second")

    assert read_status(anima_dir) == {"first": 50, "second": 50}


def test_update_status_does_not_overwrite_malformed_json(tmp_path: Path) -> None:
    from core.platform.status_store import update_status

    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    status_path = anima_dir / "status.json"
    malformed = '{"enabled": '
    status_path.write_text(malformed, encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        update_status(anima_dir, lambda status: status.update(enabled=False))

    assert status_path.read_text(encoding="utf-8") == malformed


def test_update_config_serializes_concurrent_processes(tmp_path: Path) -> None:
    from core.config.io import load_config

    config_path = tmp_path / "config.json"
    _run_two_process_updates(config_path, _append_config_alias, "first", "second")

    config = load_config(config_path)
    assert config.animas["first"].aliases == ["first"] * 50
    assert config.animas["second"].aliases == ["second"] * 50
