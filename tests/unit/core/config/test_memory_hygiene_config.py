from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config.schemas import ConsolidationConfig, HousekeepingConfig


def test_memory_hygiene_config_defaults() -> None:
    housekeeping = HousekeepingConfig()

    assert housekeeping.shortterm_archive_retention_days == 30
    assert housekeeping.shortterm_thread_gc_days == 30
    assert housekeeping.facts_lock_stale_hours == 24
    assert housekeeping.archive_versions_keep_per_file == 5
    assert housekeeping.sdk_bash_injection_max_size_mb == 10


def test_sdk_bash_injection_limit_preserves_legacy_config_and_allows_override() -> None:
    legacy = HousekeepingConfig(suppressed_messages_max_size_mb=20)
    assert legacy.sdk_bash_injection_max_size_mb == 20

    overridden = HousekeepingConfig(suppressed_messages_max_size_mb=20, sdk_bash_injection_max_size_mb=32)
    assert overridden.sdk_bash_injection_max_size_mb == 32


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("shortterm_archive_retention_days", 0),
        ("shortterm_thread_gc_days", 0),
        ("facts_lock_stale_hours", 0),
        ("archive_versions_keep_per_file", 0),
        ("sdk_bash_injection_max_size_mb", 0),
    ],
)
def test_housekeeping_memory_hygiene_fields_require_positive_values(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        HousekeepingConfig(**{field: value})


def test_weekly_consolidation_parallelism_defaults_to_three() -> None:
    assert ConsolidationConfig().max_concurrent_animas == 3


@pytest.mark.parametrize("value", [-1, -9])
def test_consolidation_parallelism_rejects_negative_value(value: int) -> None:
    with pytest.raises(ValidationError):
        ConsolidationConfig(max_concurrent_animas=value)
