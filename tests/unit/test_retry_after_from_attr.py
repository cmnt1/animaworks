from __future__ import annotations

import pytest

from core.integrations._retry import retry_after_from_attr


@pytest.mark.parametrize(
    ("retry_after", "expected"),
    [(3, 3.0), ("2.5", 2.5), (None, None), ("later", None)],
)
def test_retry_after_from_attr_coerces_numeric_values(retry_after: object, expected: float | None) -> None:
    exc = Exception("rate limited")
    if retry_after is not None:
        exc.retry_after = retry_after  # type: ignore[attr-defined]

    assert retry_after_from_attr(exc) == expected


def test_retry_after_from_attr_returns_none_when_missing() -> None:
    assert retry_after_from_attr(Exception("no retry-after")) is None
