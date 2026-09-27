"""Tests for the cross-process wake registry in core.tasks.wake."""

from __future__ import annotations

import pytest

from core.tasks.wake import register_wake, request_wake, unregister_wake


def _clear_registry():
    # Ensure a clean, isolated registry for each test.
    for key in list(__import__("core.tasks.wake", fromlist=["_wake_handlers"])._wake_handlers):
        unregister_wake(key)


@pytest.fixture(autouse=True)
def _clear():
    _clear_registry()
    yield
    _clear_registry()


def test_register_then_request_calls_fn_and_returns_true():
    called = []
    register_wake("anima-a", lambda: called.append("x"))
    assert request_wake("anima-a") is True
    assert called == ["x"]


def test_unregistered_returns_false():
    assert request_wake("missing") is False


def test_fn_exception_is_swallowed_and_returns_true():
    def boom():
        raise RuntimeError("boom")

    register_wake("anima-a", boom)
    assert request_wake("anima-a") is True  # no exception propagated


def test_unregister_removes_callback():
    called = []
    register_wake("anima-a", lambda: called.append("x"))
    unregister_wake("anima-a")
    assert request_wake("anima-a") is False
    assert called == []


def test_unregister_with_fn_only_removes_when_current():
    called = []
    register_wake("anima-a", lambda: called.append("old"))
    new_fn = lambda: called.append("new")  # noqa: E731
    register_wake("anima-a", new_fn)
    unregister_wake("anima-a", lambda: called.append("stale"))
    assert request_wake("anima-a") is True  # still the "new" one
    assert called == ["new"]
