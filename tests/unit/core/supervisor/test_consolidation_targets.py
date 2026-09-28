# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for consolidation targeting all initialized animas.

Verifies that ``_iter_consolidation_targets()`` scans ``self.animas_dir``
on disk rather than relying on ``self.processes`` (live process dict),
so that stopped / crashed animas still receive memory consolidation.

Note: Tests for ``_run_daily_consolidation()`` and ``_run_weekly_integration()``
were removed because those methods call ``daily_consolidate``/``weekly_integrate``
which were removed from ConsolidationEngine in the consolidation refactor.

Issue: docs/issues/20260217_consolidation-run-for-all-animas.md
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.supervisor.ipc import IPCResponse
from core.supervisor.manager import ProcessSupervisor
from core.supervisor.process_handle import ProcessState

# ── Helpers ──────────────────────────────────────────────────────────


def _make_supervisor(tmp_path: Path) -> ProcessSupervisor:
    """Create a minimal ProcessSupervisor rooted under *tmp_path*."""
    animas_dir = tmp_path / "animas"
    animas_dir.mkdir(parents=True, exist_ok=True)
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return ProcessSupervisor(
        animas_dir=animas_dir,
        shared_dir=shared_dir,
        run_dir=run_dir,
    )


def _create_anima_dir(
    animas_dir: Path,
    name: str,
    *,
    has_identity: bool = True,
    has_status: bool = True,
    enabled: bool = True,
) -> Path:
    """Create a mock anima directory on disk with optional files."""
    d = animas_dir / name
    d.mkdir(parents=True, exist_ok=True)
    if has_identity:
        (d / "identity.md").write_text(f"# {name}", encoding="utf-8")
    if has_status:
        (d / "status.json").write_text(json.dumps({"enabled": enabled}), encoding="utf-8")
    return d


# ── _iter_consolidation_targets ──────────────────────────────────────


class TestIterConsolidationTargets:
    """Tests for the helper that enumerates consolidation-eligible animas."""

    def test_returns_fully_initialized_anima(self, tmp_path: Path) -> None:
        sup = _make_supervisor(tmp_path)
        _create_anima_dir(sup.animas_dir, "sakura")

        targets = sup._iter_consolidation_targets()

        assert len(targets) == 1
        assert targets[0][0] == "sakura"
        assert targets[0][1] == sup.animas_dir / "sakura"

    def test_skips_directory_without_identity(self, tmp_path: Path) -> None:
        sup = _make_supervisor(tmp_path)
        _create_anima_dir(sup.animas_dir, "incomplete", has_identity=False)

        targets = sup._iter_consolidation_targets()

        assert targets == []

    def test_skips_directory_without_status_json(self, tmp_path: Path) -> None:
        sup = _make_supervisor(tmp_path)
        _create_anima_dir(sup.animas_dir, "no_status", has_status=False)

        targets = sup._iter_consolidation_targets()

        assert targets == []

    def test_skips_disabled_anima(self, tmp_path: Path) -> None:
        sup = _make_supervisor(tmp_path)
        _create_anima_dir(sup.animas_dir, "disabled_anima", enabled=False)

        targets = sup._iter_consolidation_targets()

        assert targets == []

    def test_skips_regular_files(self, tmp_path: Path) -> None:
        sup = _make_supervisor(tmp_path)
        (sup.animas_dir / "not_a_dir.txt").write_text("file", encoding="utf-8")

        targets = sup._iter_consolidation_targets()

        assert targets == []

    def test_returns_empty_when_animas_dir_missing(self, tmp_path: Path) -> None:
        sup = _make_supervisor(tmp_path)
        sup.animas_dir = tmp_path / "nonexistent"

        targets = sup._iter_consolidation_targets()

        assert targets == []

    def test_includes_multiple_animas_sorted(self, tmp_path: Path) -> None:
        sup = _make_supervisor(tmp_path)
        _create_anima_dir(sup.animas_dir, "zeta")
        _create_anima_dir(sup.animas_dir, "alpha")
        _create_anima_dir(sup.animas_dir, "mu")

        targets = sup._iter_consolidation_targets()
        names = [t[0] for t in targets]

        assert names == ["alpha", "mu", "zeta"]

    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        sup = _make_supervisor(tmp_path)
        _create_anima_dir(sup.animas_dir, "good")
        _create_anima_dir(sup.animas_dir, "no_id", has_identity=False)
        _create_anima_dir(sup.animas_dir, "no_status", has_status=False)
        _create_anima_dir(sup.animas_dir, "off", enabled=False)
        _create_anima_dir(sup.animas_dir, "also_good")

        targets = sup._iter_consolidation_targets()
        names = [t[0] for t in targets]

        assert names == ["also_good", "good"]


class _TimeoutHandle:
    """Fake running process handle that times out consolidation IPC."""

    state = ProcessState.RUNNING

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.timeouts: list[float] = []

    async def send_request(
        self,
        method: str,
        params: dict,
        timeout: float = 60.0,
    ) -> IPCResponse:
        self.calls.append(method)
        self.timeouts.append(timeout)
        if method == "run_consolidation":
            raise TimeoutError("consolidation timed out")
        return IPCResponse(id="fake", result={})


class _RecordingHandle:
    state = ProcessState.RUNNING

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def send_request(self, method: str, params: dict, timeout: float = 60.0) -> IPCResponse:
        self.calls.append((method, params))
        return IPCResponse(id="fake", result={})


class _RecentEpisodesEngine:
    """Minimal consolidation engine stub with work to do."""

    def __init__(self, anima_dir: Path, anima_name: str) -> None:
        self.anima_dir = anima_dir
        self.anima_name = anima_name

    def _collect_recent_episodes(self, hours: int) -> list[str]:
        return ["episode"]

    def count_recent_activity_entries(self, hours: int = 24, **_kwargs) -> int:
        return 0


def test_consolidation_ipc_timeout_scales_with_daily_workload(tmp_path: Path) -> None:
    sup = _make_supervisor(tmp_path)
    cfg = SimpleNamespace(
        ipc_timeout_base_seconds=1800,
        ipc_timeout_per_activity_entry_seconds=4.0,
        ipc_timeout_per_episode_seconds=120.0,
        ipc_timeout_max_seconds=7200,
    )
    gate = SimpleNamespace(activity_count=300, episode_count=2)

    timeout = sup._resolve_consolidation_ipc_timeout(cfg, consolidation_type="daily", gate=gate)

    assert timeout == 3240.0


@pytest.mark.parametrize(
    ("activity_count", "episode_count", "should_run"),
    [(2, 0, True), (0, 2, True), (1, 1, False)],
)
def test_daily_gate_uses_only_activity_and_episode_thresholds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    activity_count: int,
    episode_count: int,
    should_run: bool,
) -> None:
    from core.lifecycle.system_consolidation import evaluate_daily_consolidation_gate

    class _GateEngine:
        def __init__(self, *_args) -> None:
            pass

        def _collect_recent_episodes(self, hours: int) -> list[dict]:
            return [{} for _ in range(episode_count)]

        @staticmethod
        def previous_local_day_window():
            return None, None, None

        def count_recent_activity_entries(self, **_kwargs) -> int:
            return activity_count

    monkeypatch.setattr("core.memory.maintenance.consolidation.ConsolidationEngine", _GateEngine)
    gate = evaluate_daily_consolidation_gate(tmp_path, "fixture", threshold=2)

    assert gate.should_run is should_run
    assert not hasattr(gate, "carryover_count")


def test_daily_gate_runs_for_pending_episode_backfill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import date, datetime, timedelta

    from core.lifecycle.system_consolidation import evaluate_daily_consolidation_gate

    class _BackfillGateEngine:
        def __init__(self, *_args) -> None:
            self.visited: list[date] = []

        def _collect_recent_episodes(self, hours: int) -> list[dict]:
            return []

        @staticmethod
        def previous_local_day_window():
            yesterday = date(2026, 9, 27)
            return yesterday, None, None

        @staticmethod
        def local_day_window(day: date):
            return datetime.combine(day, datetime.min.time()), datetime.combine(
                day + timedelta(days=1), datetime.min.time()
            )

        def collect_activity_chunks(self, *, since, **_kwargs):
            day = since.date()
            self.visited.append(day)
            return ["missed episode"] if day == date(2026, 9, 25) else []

        @staticmethod
        def unprocessed_activity_chunks(_day, chunks):
            return chunks

        @staticmethod
        def count_recent_activity_entries(**_kwargs) -> int:
            return 0

    engine = _BackfillGateEngine()
    monkeypatch.setattr("core.memory.maintenance.consolidation.ConsolidationEngine", lambda *_args: engine)

    gate = evaluate_daily_consolidation_gate(
        tmp_path,
        "fixture",
        threshold=2,
        backfill_days=4,
        model="test-model",
    )

    assert gate.should_run
    assert gate.pending_backfill_days == 1
    assert len(engine.visited) == 4


def test_consolidation_ipc_timeout_respects_max_and_weekly_override(tmp_path: Path) -> None:
    sup = _make_supervisor(tmp_path)
    cfg = SimpleNamespace(
        ipc_timeout_base_seconds=1800,
        ipc_timeout_per_activity_entry_seconds=10.0,
        ipc_timeout_per_episode_seconds=100.0,
        ipc_timeout_max_seconds=2000,
        weekly_ipc_timeout_seconds=4800,
    )
    gate = SimpleNamespace(activity_count=300, episode_count=2)

    daily = sup._resolve_consolidation_ipc_timeout(cfg, consolidation_type="daily", gate=gate)
    weekly = sup._resolve_consolidation_ipc_timeout(cfg, consolidation_type="weekly")

    assert daily == 2000.0
    assert weekly == 4800.0


@pytest.mark.asyncio
async def test_daily_consolidation_timeout_logs_once_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Timeouts still run framework-side post-processing before continuing."""
    sup = _make_supervisor(tmp_path)
    _create_anima_dir(sup.animas_dir, "mio")
    handle = _TimeoutHandle()
    sup.processes["mio"] = handle
    mock_forgetter = MagicMock()
    mock_forgetter.synaptic_downscaling.return_value = {"scanned": 1}
    monkeypatch.setattr(
        "core.memory.maintenance.consolidation.ConsolidationEngine",
        _RecentEpisodesEngine,
    )
    monkeypatch.setattr("core.memory.maintenance.forgetting.ForgettingEngine", lambda *_args: mock_forgetter)
    monkeypatch.setattr(
        "core.lifecycle.system_consolidation.run_knowledge_self_correction_if_enabled",
        AsyncMock(),
    )
    monkeypatch.setattr("core.lifecycle.system_consolidation.should_skip_inactive_consolidation", lambda *_args: False)

    with caplog.at_level(logging.WARNING, logger="core.supervisor._mgr_scheduler"):
        await sup._run_daily_consolidation()

    assert handle.calls == ["run_consolidation", "interrupt"]
    assert "consolidation_timeout anima=mio phase=phase_a type=daily" in caplog.text
    assert "Daily consolidation failed for mio" not in caplog.text
    # synaptic_downscaling_enabled defaults to True (harness diet PR-6),
    # so framework-side post-processing still runs downscaling on timeout.
    mock_forgetter.synaptic_downscaling.assert_called_once()


@pytest.mark.asyncio
async def test_weekly_consolidation_timeout_logs_once_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Weekly timeout handling should mirror daily timeout handling."""
    sup = _make_supervisor(tmp_path)
    _create_anima_dir(sup.animas_dir, "mio")
    handle = _TimeoutHandle()
    sup.processes["mio"] = handle
    postprocess = AsyncMock()
    monkeypatch.setattr("core.lifecycle.system_consolidation.run_weekly_integration_post_processing", postprocess)
    monkeypatch.setattr("core.lifecycle.system_consolidation.should_skip_inactive_consolidation", lambda *_args: False)

    with caplog.at_level(logging.WARNING, logger="core.supervisor._mgr_scheduler"):
        await sup._run_weekly_integration()

    assert handle.calls == ["run_consolidation", "interrupt"]
    assert "consolidation_timeout anima=mio phase=phase_b type=weekly" in caplog.text
    assert "Weekly integration failed for mio" not in caplog.text
    postprocess.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("method_name", ["_run_daily_consolidation", "_run_weekly_integration"])
async def test_scheduler_skips_inactive_anima_before_ipc(
    tmp_path: Path,
    method_name: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sup = _make_supervisor(tmp_path)
    _create_anima_dir(sup.animas_dir, "sleepy")
    handle = _TimeoutHandle()
    sup.processes["sleepy"] = handle

    with caplog.at_level(logging.INFO):
        await getattr(sup, method_name)()

    assert handle.calls == []
    assert "no activity_log entries in the last 7 days" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "consolidation_type"),
    [
        ("_run_daily_consolidation", "daily"),
        ("_run_weekly_integration", "weekly"),
    ],
)
async def test_project_archives_bypass_inactivity_and_skip_empty_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    consolidation_type: str,
) -> None:
    sup = _make_supervisor(tmp_path)
    anima_dir = _create_anima_dir(sup.animas_dir, "librarian")
    (anima_dir / "episodes" / "projects" / "empty").mkdir(parents=True)
    active_dir = anima_dir / "episodes" / "projects" / "active"
    active_dir.mkdir(parents=True)
    (active_dir / "2026-08-13_sessions.md").write_text("episode", encoding="utf-8")
    handle = _RecordingHandle()
    sup.processes["librarian"] = handle
    monkeypatch.setattr("core.lifecycle.system_consolidation.should_skip_inactive_consolidation", lambda *_args: True)

    await getattr(sup, method_name)()

    assert handle.calls == [
        (
            "run_consolidation",
            {"consolidation_type": consolidation_type, "project": "active"},
        )
    ]
