# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit-test fixtures: global permissions cache for ToolHandler security tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from core.config.global_permissions import GlobalPermissionsCache
from core.paths import TEMPLATES_DIR


@pytest.fixture(autouse=True)
def _reset_vector_error_reset_cooldown() -> None:
    """Clear the process-wide vector-store error-reset cooldown between tests."""
    from core.memory.rag import singleton

    with singleton._error_reset_lock:
        singleton._last_error_reset_monotonic = None
    yield
    with singleton._error_reset_lock:
        singleton._last_error_reset_monotonic = None


@pytest.fixture(autouse=True)
def _reset_llm_rate_guard_singleton(tmp_path: Path) -> None:
    """Point the process-wide LLM rate guard at a per-test temp file."""
    from core.config.schemas import LlmRateGuardConfig
    from core.execution import rate_guard

    rate_guard._shared_guard = rate_guard.LlmRateGuard(
        config=LlmRateGuardConfig(),
        path=tmp_path / "_llm_rate_guard.json",
    )
    yield
    rate_guard._shared_guard = None


@pytest.fixture(autouse=True)
def _reset_config_caches_for_unit_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Isolate runtime config and event exporters from the developer machine."""
    from core.config import invalidate_cache, invalidate_vault_cache
    from core.event_export import reset_event_exporters

    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / "_runtime"))
    reset_event_exporters()
    invalidate_cache()
    invalidate_vault_cache()
    yield
    reset_event_exporters()
    invalidate_cache()
    invalidate_vault_cache()


@pytest.fixture(autouse=True)
def _disable_skill_dense_embeddings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bypass the real embedding model in unit tests.

    ``core.skills.dense`` normally invokes the local HTTP embedding model;
    unit tests replace it so no real model is ever loaded.  Individual tests
    (e.g. test_skill_dense.py) override ``generate_embeddings`` themselves.
    """
    import core.skills.dense as skill_dense

    monkeypatch.setattr(skill_dense, "generate_embeddings", lambda *a, **k: [])
    skill_dense._PROCESS_CACHE.clear()
    skill_dense._QUERY_LRU.clear()
    yield
    skill_dense._PROCESS_CACHE.clear()
    skill_dense._QUERY_LRU.clear()


@pytest.fixture(autouse=True)
def _global_permissions_for_unit_tests(tmp_path: Path) -> None:
    """Load ``permissions.global.json`` template so command block patterns match production.

    Uses a dedicated subdirectory so the hash file (``run/``) does not
    pollute the test's ``tmp_path`` root.
    """
    GlobalPermissionsCache.reset()
    gp_dir = tmp_path / "_global_perms"
    gp_dir.mkdir(exist_ok=True)
    src = TEMPLATES_DIR / "_shared" / "config_defaults" / "permissions.global.json"
    dst = gp_dir / "permissions.global.json"
    shutil.copy(src, dst)
    GlobalPermissionsCache.get().load(dst, interactive=False)
    yield
    GlobalPermissionsCache.reset()


# ── Default-topology shim ─────────────────────────────────────────────
# Production default topology is ``phase3`` (missing status.json resolves to
# root DB ownership).  Legacy-path tests use ad-hoc anima dirs without a
# status.json; resolve those to ``legacy`` so pre-existing fixtures keep
# exercising the legacy worker/in-process paths.  Tests that write an explicit
# status.json keep the real resolver behaviour.
import pytest as _pytest_topology

import core.config.resolver as _resolver_module
from core.config.resolver import resolve_process_model_config as _real_resolve_pm
from core.config.schemas import (
    ResolvedProcessModelConfig as _RPMC,
    TaskProcessIsolationConfig as _TPIC,
)


@_pytest_topology.fixture(autouse=True)
def _legacy_topology_for_fixtureless_animas(monkeypatch):
    from pathlib import Path as _Path

    def _resolve(anima_dir):
        if (_Path(anima_dir) / "status.json").is_file():
            return _real_resolve_pm(anima_dir)
        return _RPMC(process_model="legacy", task_process_isolation=_TPIC())

    monkeypatch.setattr(_resolver_module, "resolve_process_model_config", _resolve)
    yield
