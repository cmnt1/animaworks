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
