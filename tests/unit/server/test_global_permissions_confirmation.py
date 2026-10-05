from __future__ import annotations

from unittest.mock import patch

import pytest

from server.app import _confirm_global_permissions_change


def test_global_permissions_confirmation_requires_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("server.app.sys.stdin", type("NonTTY", (), {"isatty": lambda self: False})())

    with pytest.raises(SystemExit, match="non-interactive session cannot confirm"):
        _confirm_global_permissions_change("accept?")


def test_global_permissions_confirmation_accepts_only_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("server.app.sys.stdin", type("TTY", (), {"isatty": lambda self: True})())
    with patch("builtins.input", return_value=" YES ") as input_mock:
        assert _confirm_global_permissions_change("accept?") is True
    input_mock.assert_called_once_with("accept?")

    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    assert _confirm_global_permissions_change("accept?") is False
