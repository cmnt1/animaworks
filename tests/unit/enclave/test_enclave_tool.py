# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the enclave_ask host-side tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from core.config import invalidate_cache
from core.integrations import enclave as enclave_mod
from tests.helpers.filesystem import DEFAULT_TEST_CONFIG


class _FakeResp:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self, responses: list[_FakeResp]) -> None:
        self.responses = responses
        self.calls = 0

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def post(self, url: str, json: Any = None) -> _FakeResp:  # noqa: A002
        self.calls += 1
        return self.responses.pop(0)


def _write_config(data_dir: Path, enclaves: dict) -> None:
    cfg = dict(DEFAULT_TEST_CONFIG)
    cfg["enclaves"] = enclaves
    (data_dir / "config.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    invalidate_cache()


def _fake_http(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[_FakeResp],
) -> _FakeClient:
    client = _FakeClient(responses)
    monkeypatch.setattr(enclave_mod.httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(enclave_mod.httpx, "HTTPTransport", lambda **kwargs: object())
    return client


def test_dispatch_200_formats_facts(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(
        data_dir,
        {"pii": {"socket_path": "/tmp/enclave.sock", "allowed_animas": ["anima-a"], "timeout_s": 5}},
    )
    client = _fake_http(
        monkeypatch,
        [
            _FakeResp(
                200, {"audit_id": "aud-1", "facts": [{"fact": "ann says hi", "evidence": ["record:1", "record:2"]}]}
            )
        ],
    )
    result = enclave_mod.dispatch("enclave_ask", {"enclave": "pii", "question": "q", "anima_dir": "/x/anima-a"})
    assert client.calls == 1
    assert "- ann says hi（根拠: record:1, record:2）" in result
    assert "audit_id: aud-1" in result


def test_dispatch_422_formats_error(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(
        data_dir,
        {"pii": {"socket_path": "/tmp/enclave.sock", "allowed_animas": ["anima-a"], "timeout_s": 5}},
    )
    client = _fake_http(monkeypatch, [_FakeResp(422, {"error": "egress_blocked", "audit_id": "aud-x"})])
    result = enclave_mod.dispatch("enclave_ask", {"enclave": "pii", "question": "q", "anima_dir": "/x/anima-a"})
    assert client.calls == 1
    assert "code=422" in result
    assert "audit_id: aud-x" in result


def test_dispatch_denied_anima(data_dir: Path) -> None:
    _write_config(
        data_dir,
        {"pii": {"socket_path": "/tmp/enclave.sock", "allowed_animas": ["anima-a"], "timeout_s": 5}},
    )
    # anima-b not in allowed_animas -> rejected before any HTTP call (no socket needed).
    result = enclave_mod.dispatch("enclave_ask", {"enclave": "pii", "question": "q", "anima_dir": "/x/anima-b"})
    assert "許可" in result or "allowed" in result


def test_dispatch_empty_allow_list_denies_everyone(data_dir: Path) -> None:
    _write_config(data_dir, {"pii": {"socket_path": "/tmp/enclave.sock", "allowed_animas": [], "timeout_s": 5}})
    result = enclave_mod.dispatch("enclave_ask", {"enclave": "pii", "question": "q", "anima_dir": "/x/anima-a"})
    assert "許可" in result or "allowed" in result


def test_dispatch_unknown_enclave(data_dir: Path) -> None:
    _write_config(data_dir, {})
    result = enclave_mod.dispatch("enclave_ask", {"enclave": "missing", "question": "q", "anima_dir": "/x/a"})
    assert "missing" in result


def test_dispatch_socket_missing(data_dir: Path) -> None:
    missing = str(data_dir / "does-not-exist.sock")
    _write_config(data_dir, {"pii": {"socket_path": missing, "allowed_animas": ["anima-a"], "timeout_s": 5}})
    result = enclave_mod.dispatch("enclave_ask", {"enclave": "pii", "question": "q", "anima_dir": "/x/anima-a"})
    assert "接続" in result or "reach" in result


def test_default_case_id_is_safe() -> None:
    from core.integrations.enclave import _safe_case_id

    value = _safe_case_id("あるアニマ名!!" * 20)
    assert "-" in value
    assert len(value) <= 64
    assert all(c.isalnum() or c in "_.-" for c in value)


def test_http_transport_uses_uds(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The tool posts over the configured Unix socket."""
    seen: dict[str, Any] = {}

    class _ProbeTransport:
        def __init__(self, *, uds: str) -> None:
            seen["uds"] = uds

    class _ProbeClient:
        def __init__(self, **kwargs: Any) -> None:
            seen["kwargs"] = kwargs

        def __enter__(self) -> _ProbeClient:
            return self

        def __exit__(self, *args: object) -> bool:
            return False

        def post(self, url: str, json: Any = None) -> _FakeResp:  # noqa: A002
            seen["url"] = url
            seen["body"] = json
            return _FakeResp(200, {"audit_id": "a", "facts": []})

    monkeypatch.setattr(enclave_mod.httpx, "HTTPTransport", _ProbeTransport)
    monkeypatch.setattr(enclave_mod.httpx, "Client", _ProbeClient)

    _write_config(data_dir, {"pii": {"socket_path": "/srv/e.sock", "allowed_animas": ["anima-a"], "timeout_s": 7}})
    enclave_mod.dispatch("enclave_ask", {"enclave": "pii", "question": "hello", "anima_dir": "/x/anima-a"})
    assert seen["uds"] == "/srv/e.sock"
    assert seen["url"] == "http://enclave/v1/ask"
    assert seen["body"]["question"] == "hello"


def test_httpx_imports() -> None:
    assert isinstance(httpx.Client, type)
