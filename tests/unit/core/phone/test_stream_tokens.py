from __future__ import annotations

from core.phone.stream_tokens import PhoneStreamTokenStore


def test_stream_token_is_bound_to_call_and_consumed_once() -> None:
    store = PhoneStreamTokenStore()
    token = store.issue("CA-1")

    assert store.consume(token, "CA-OTHER") is False
    assert store.consume(token, "CA-1") is True
    assert store.consume(token, "CA-1") is False


def test_stream_token_expires_after_configured_ttl() -> None:
    now = [100.0]
    store = PhoneStreamTokenStore(ttl_seconds=10, clock=lambda: now[0])
    token = store.issue("CA-1")

    now[0] = 110.0

    assert store.consume(token, "CA-1") is False
    assert len(store) == 0


def test_stream_token_can_be_revoked_for_a_call() -> None:
    store = PhoneStreamTokenStore()
    first = store.issue("CA-1")
    second = store.issue("CA-2")

    store.revoke_for_call("CA-1")

    assert store.consume(first, "CA-1") is False
    assert store.consume(second, "CA-2") is True


def test_stream_token_store_evicts_oldest_when_full() -> None:
    store = PhoneStreamTokenStore(max_items=1)
    first = store.issue("CA-1")
    second = store.issue("CA-2")

    assert store.consume(first, "CA-1") is False
    assert store.consume(second, "CA-2") is True
