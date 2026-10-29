"""Cron thread ids must satisfy the state writer's thread_id contract."""

from __future__ import annotations

import pytest

from core.anima.lifecycle import _cron_thread_id
from core.platform.state_writer import _SAFE_THREAD_ID


def test_short_ascii_name_keeps_legacy_id() -> None:
    assert _cron_thread_id("daily-report") == "cron-daily-report"


@pytest.mark.parametrize(
    "name",
    [
        "PRレビュー即応巡回（2026-09-07 sakura 追加・taka指示「レビューが遅い」への対応）",
        "Beeper 未返信チェック（LINE/WhatsApp/Telegram/Facebook）",
        "日次",
        "a" * 80,
    ],
)
def test_long_or_non_ascii_names_are_valid_thread_ids(name: str) -> None:
    thread_id = _cron_thread_id(name)
    assert _SAFE_THREAD_ID.fullmatch(thread_id)
    assert thread_id == _cron_thread_id(name)


def test_names_collapsing_to_same_ascii_get_distinct_ids() -> None:
    assert _cron_thread_id("朝の巡回") != _cron_thread_id("夜の巡回")
    assert _cron_thread_id("AI-Schreiber Web 監視（sakura 依頼）") != _cron_thread_id(
        "AI-Schreiber Web 確認（sakura 依頼）"
    )
