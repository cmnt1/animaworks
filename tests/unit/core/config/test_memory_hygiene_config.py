from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config.schemas import HousekeepingConfig


def test_memory_hygiene_config_defaults() -> None:
    housekeeping = HousekeepingConfig()

    assert housekeeping.shortterm_archive_retention_days == 30
    assert housekeeping.shortterm_thread_gc_days == 30
    assert housekeeping.facts_lock_stale_hours == 24
    assert housekeeping.hygiene_grace_days == 21


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("shortterm_archive_retention_days", 0),
        ("shortterm_thread_gc_days", 0),
        ("facts_lock_stale_hours", 0),
        ("hygiene_grace_days", 0),
    ],
)
def test_housekeeping_memory_hygiene_fields_require_positive_values(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        HousekeepingConfig(**{field: value})
