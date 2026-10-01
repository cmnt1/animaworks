from __future__ import annotations

import os

import pytest

from core.runtime.process_role import PROCESS_ROLE_ENV, get_process_role, set_process_role


@pytest.mark.parametrize("role", ["root", "anima", "task_runner", "cli", "mcp"])
def test_set_process_role_updates_current_process_and_child_environment(monkeypatch, role: str) -> None:
    monkeypatch.delenv(PROCESS_ROLE_ENV, raising=False)

    set_process_role(role)  # type: ignore[arg-type]

    assert get_process_role() == role
    assert os.environ[PROCESS_ROLE_ENV] == role


def test_get_process_role_defaults_to_cli_for_unset_or_invalid_value(monkeypatch) -> None:
    monkeypatch.delenv(PROCESS_ROLE_ENV, raising=False)
    assert get_process_role() == "cli"

    monkeypatch.setenv(PROCESS_ROLE_ENV, "unknown")
    assert get_process_role() == "cli"


def test_set_process_role_rejects_invalid_role(monkeypatch) -> None:
    monkeypatch.delenv(PROCESS_ROLE_ENV, raising=False)

    with pytest.raises(ValueError, match="Unknown process role"):
        set_process_role("unknown")  # type: ignore[arg-type]

    assert PROCESS_ROLE_ENV not in os.environ
