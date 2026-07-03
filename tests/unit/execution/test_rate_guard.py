# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.execution.rate_guard — file-backed fail-open guard."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core.config.schemas import LlmRateGuardConfig
from core.execution.rate_guard import LlmRateGuard


def _guard(tmp_path: Path, **cfg_overrides) -> LlmRateGuard:
    cfg = LlmRateGuardConfig(**cfg_overrides)
    return LlmRateGuard(config=cfg, path=tmp_path / "llm_rate_guard.json")


class TestReportAndQuery:
    def test_report_then_blocked(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path)
        guard.report_block("anthropic", 60, "rate_limit")
        remaining = guard.blocked_remaining("anthropic")
        assert 0 < remaining <= 60

    def test_unblocked_family_returns_zero(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path)
        guard.report_block("anthropic", 60, "rate_limit")
        assert guard.blocked_remaining("openai") == 0.0

    def test_expired_entry_returns_zero(self, tmp_path: Path) -> None:
        path = tmp_path / "llm_rate_guard.json"
        path.write_text(json.dumps({"anthropic": {"blocked_until": time.time() - 5, "reason": "rate_limit"}}))
        guard = _guard(tmp_path)
        assert guard.blocked_remaining("anthropic") == 0.0

    def test_reason_and_updated_by_persisted(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_ANIMA_NAME", "aoi")
        guard = _guard(tmp_path)
        guard.report_block("anthropic", 30, "overloaded")
        state = json.loads((tmp_path / "llm_rate_guard.json").read_text())
        assert state["anthropic"]["reason"] == "overloaded"
        assert state["anthropic"]["updated_by"] == "aoi"


class TestClamp:
    def test_huge_block_clamped_to_max(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path, max_block_seconds=600)
        guard.report_block("anthropic", 999999, "rate_limit")
        assert guard.blocked_remaining("anthropic") <= 600

    def test_nonpositive_block_uses_default(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path, default_block_seconds=45)
        guard.report_block("anthropic", -10, "rate_limit")
        remaining = guard.blocked_remaining("anthropic")
        assert 40 < remaining <= 45


class TestFailOpen:
    def test_corrupt_file_reads_as_unblocked(self, tmp_path: Path) -> None:
        path = tmp_path / "llm_rate_guard.json"
        path.write_text("{not valid json ::::")
        guard = _guard(tmp_path)
        assert guard.blocked_remaining("anthropic") == 0.0

    def test_report_over_corrupt_file_replaces_it(self, tmp_path: Path) -> None:
        path = tmp_path / "llm_rate_guard.json"
        path.write_text("garbage")
        guard = _guard(tmp_path)
        guard.report_block("anthropic", 60, "rate_limit")
        state = json.loads(path.read_text())
        assert "anthropic" in state

    def test_write_failure_is_swallowed(self, tmp_path: Path, monkeypatch) -> None:
        guard = _guard(tmp_path)

        def _boom(_state) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(guard, "_write_state", _boom)
        # Must not raise.
        guard.report_block("anthropic", 60, "rate_limit")


class TestEnabledToggle:
    def test_disabled_query_returns_zero_even_when_file_blocks(self, tmp_path: Path) -> None:
        path = tmp_path / "llm_rate_guard.json"
        path.write_text(json.dumps({"anthropic": {"blocked_until": time.time() + 300, "reason": "rate_limit"}}))
        guard = _guard(tmp_path, enabled=False)
        assert guard.blocked_remaining("anthropic") == 0.0

    def test_disabled_report_is_noop(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path, enabled=False)
        guard.report_block("anthropic", 60, "rate_limit")
        assert not (tmp_path / "llm_rate_guard.json").exists()


class TestConcurrency:
    def test_concurrent_writes_stay_valid_json(self, tmp_path: Path) -> None:
        guard = _guard(tmp_path)
        families = [f"provider-{i}" for i in range(8)]

        def _writer(fam: str) -> None:
            for _ in range(25):
                guard.report_block(fam, 60, "rate_limit")

        threads = [threading.Thread(target=_writer, args=(fam,)) for fam in families]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # File must remain parseable (atomic replace, last-writer-wins).
        state = json.loads((tmp_path / "llm_rate_guard.json").read_text())
        assert isinstance(state, dict)
        # At least one family recorded; concurrent replaces may drop others.
        assert any(fam in state for fam in families)
