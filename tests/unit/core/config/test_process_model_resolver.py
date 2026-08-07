"""Process topology resolution from status.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.config.resolver import resolve_process_model_config


def _write_status(anima_dir: Path, value: object) -> None:
    anima_dir.mkdir(parents=True)
    (anima_dir / "status.json").write_text(json.dumps(value), encoding="utf-8")


def test_missing_status_defaults_to_legacy(tmp_path: Path) -> None:
    resolved = resolve_process_model_config(tmp_path / "anima")

    assert resolved.valid
    assert resolved.process_model == "legacy"
    assert not resolved.task_process_isolation.cron


def test_phase2_uses_strict_lane_flags(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    _write_status(
        anima_dir,
        {
            "process_model": "phase2",
            "task_process_isolation": {"cron": True},
        },
    )

    resolved = resolve_process_model_config(anima_dir)

    assert resolved.valid
    assert resolved.task_process_isolation.cron
    assert not resolved.task_process_isolation.heartbeat


@pytest.mark.parametrize(
    "flags",
    [None, [], {"cron": 1}, {"cron": "true"}, {"unknown": True}],
)
def test_phase2_rejects_malformed_flags(tmp_path: Path, flags: object) -> None:
    anima_dir = tmp_path / "anima"
    _write_status(
        anima_dir,
        {"process_model": "phase2", "task_process_isolation": flags},
    )

    resolved = resolve_process_model_config(anima_dir)

    assert not resolved.valid
    assert "task_process_isolation" in (resolved.error or "")


def test_legacy_ignores_even_malformed_lane_flags(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    _write_status(
        anima_dir,
        {"process_model": "legacy", "task_process_isolation": "bad"},
    )

    resolved = resolve_process_model_config(anima_dir)

    assert resolved.valid
    assert resolved.warnings
    assert not resolved.task_process_isolation.cron


def test_phase3_ignores_stale_flags_and_resolves_all_lanes(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    _write_status(
        anima_dir,
        {"process_model": "phase3", "task_process_isolation": "bad"},
    )

    resolved = resolve_process_model_config(anima_dir)

    assert resolved.valid
    assert resolved.task_process_isolation.model_dump() == {
        "cron": True,
        "heartbeat": True,
        "task": True,
        "background": True,
    }


@pytest.mark.parametrize("process_model", ["", "PHASE2", 2, None])
def test_invalid_process_model_never_falls_back(tmp_path: Path, process_model: object) -> None:
    anima_dir = tmp_path / "anima"
    _write_status(anima_dir, {"process_model": process_model})

    resolved = resolve_process_model_config(anima_dir)

    assert not resolved.valid
    assert "process_model" in (resolved.error or "")

