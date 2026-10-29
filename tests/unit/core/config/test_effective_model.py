from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.config.model_config import effective_model_key, same_effective_model

_FIELDS = ("model", "execution_mode", "resolved_mode", "credential")


def test_effective_model_key_returns_routing_fields() -> None:
    config = SimpleNamespace(model="claude", execution_mode="s", resolved_mode="S", credential="main")

    assert effective_model_key(config) == ("claude", "s", "S", "main")


def test_same_effective_model_for_equal_configs() -> None:
    left = SimpleNamespace(model="claude", execution_mode="s", resolved_mode="S", credential="main")
    right = SimpleNamespace(model="claude", execution_mode="s", resolved_mode="S", credential="main")

    assert same_effective_model(left, right)


@pytest.mark.parametrize("field", _FIELDS)
def test_same_effective_model_detects_each_routing_field(field: str) -> None:
    values = dict(model="claude", execution_mode="s", resolved_mode="S", credential="main")
    left = SimpleNamespace(**values)
    changed = values | {field: "different"}
    right = SimpleNamespace(**changed)

    assert not same_effective_model(left, right)
