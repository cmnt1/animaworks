from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the internal API caller authentication (R04-1)."""

import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.internal_auth import (
    InternalAuth,
    require_internal_caller,
    write_operator_token,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class TestInternalAuth:
    def test_anima_token_roundtrip(self):
        auth = InternalAuth.generate()
        caller = auth.verify(auth.token_for_anima("sora"))
        assert caller is not None
        assert caller.kind == "anima"
        assert caller.name == "sora"

    def test_tampered_display_name_returns_none(self):
        auth = InternalAuth.generate()
        token = auth.token_for_anima("sora")
        assert auth.verify(token.replace("sora.", "miku.", 1)) is None

    def test_tampered_hmac_returns_none(self):
        auth = InternalAuth.generate()
        token = auth.token_for_anima("sora")
        head, _, tail = token.rpartition(".")
        bad = head + "." + ("0" if tail[-1] != "0" else "1") + tail[-1]
        assert auth.verify(bad) is None

    def test_other_secret_returns_none(self):
        token = InternalAuth.generate().token_for_anima("sora")
        assert InternalAuth.generate().verify(token) is None

    def test_invalid_anima_name_returns_none(self):
        auth = InternalAuth.generate()
        assert auth.verify(auth.token_for_anima("Not-valid")) is None

    def test_operator_token(self):
        auth = InternalAuth.generate()
        caller = auth.verify(auth.operator_token())
        assert caller is not None
        assert caller.kind == "operator"
        assert caller.name == "operator"

    def test_missing_or_garbage_header_returns_none(self):
        auth = InternalAuth.generate()
        assert auth.verify(None) is None
        assert auth.verify("") is None
        assert auth.verify("no-dot") is None


class TestWriteOperatorToken:
    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits are not supported on Windows")
    def test_permission_is_0600(self, tmp_path: Path):
        target = tmp_path / "run" / "internal_api.auth"
        with patch("server.internal_auth._current_auth", InternalAuth.generate()):
            write_operator_token(target)
        assert stat.S_IMODE(target.stat().st_mode) == 0o600


def _make_app(internal_auth) -> FastAPI:
    from fastapi import APIRouter, Depends

    app = FastAPI()
    app.state.internal_auth = internal_auth
    internal = APIRouter(dependencies=[Depends(require_internal_caller)])

    @internal.get("/internal/echo")
    def _echo():
        return {"ok": True}

    router = APIRouter()

    @router.get("/messages/{message_id}")
    def _get_message(message_id: str):
        return {"id": message_id}

    router.include_router(internal)
    app.include_router(router, prefix="/api")
    return app


class TestRequireInternalCaller:
    def test_no_header_enforce_returns_401(self, monkeypatch):
        cfg = SimpleNamespace(server=SimpleNamespace(internal_api_auth="enforce"))
        monkeypatch.setattr("server.internal_auth.load_config", lambda: cfg)
        client = TestClient(_make_app(InternalAuth.generate()))
        assert client.get("/api/internal/echo").status_code == 401

    def test_valid_header_enforce_returns_200(self, monkeypatch):
        cfg = SimpleNamespace(server=SimpleNamespace(internal_api_auth="enforce"))
        monkeypatch.setattr("server.internal_auth.load_config", lambda: cfg)
        auth = InternalAuth.generate()
        client = TestClient(_make_app(auth))
        resp = client.get(
            "/api/internal/echo",
            headers={"X-AnimaWorks-Internal-Auth": auth.token_for_anima("sora")},
        )
        assert resp.status_code == 200

    def test_non_internal_route_not_gated(self, monkeypatch):
        cfg = SimpleNamespace(server=SimpleNamespace(internal_api_auth="enforce"))
        monkeypatch.setattr("server.internal_auth.load_config", lambda: cfg)
        client = TestClient(_make_app(InternalAuth.generate()))
        assert client.get("/api/messages/abc").status_code == 200

    def test_log_mode_passes_without_header_and_warns(self, monkeypatch):
        cfg = SimpleNamespace(server=SimpleNamespace(internal_api_auth="log"))
        monkeypatch.setattr("server.internal_auth.load_config", lambda: cfg)
        fake = _FakeLogger()
        monkeypatch.setattr("server.internal_auth.logger", fake)
        client = TestClient(_make_app(InternalAuth.generate()))
        assert client.get("/api/internal/echo").status_code == 200
        assert fake.warning_called

    def test_off_mode_passes_without_header(self, monkeypatch):
        cfg = SimpleNamespace(server=SimpleNamespace(internal_api_auth="off"))
        monkeypatch.setattr("server.internal_auth.load_config", lambda: cfg)
        client = TestClient(_make_app(InternalAuth.generate()))
        assert client.get("/api/internal/echo").status_code == 200


class _FakeLogger:
    def __init__(self) -> None:
        self.warning_called = False

    def warning(self, *args, **kwargs):  # noqa: ARG002
        self.warning_called = True


class TestProcessHandleChildEnv:
    @pytest.mark.anyio
    async def test_internal_auth_env_goes_to_child(self, tmp_path: Path, monkeypatch):
        import subprocess

        from server.supervisor.process_handle import IPCClient, ProcessHandle

        captured = {}

        def _fake_popen(*args, **kwargs):
            captured["env"] = kwargs["env"]
            return SimpleNamespace(pid=7, poll=lambda: None, returncode=None)

        sock = tmp_path / "test.sock"
        sock.touch()
        monkeypatch.setattr(subprocess, "Popen", _fake_popen)
        monkeypatch.setattr(
            IPCClient,
            "connect",
            AsyncMock(return_value=None),
        )

        handle = ProcessHandle(
            anima_name="sora",
            socket_path=sock,
            animas_dir=tmp_path,
            shared_dir=tmp_path,
            internal_auth_env={"ANIMAWORKS_INTERNAL_AUTH": "sora.abc123"},
            startup_ready_timeout=1.0,
        )
        monkeypatch.setattr(handle, "_wait_for_ready", AsyncMock(return_value=None))
        monkeypatch.setattr(handle, "_send_startup_ack", AsyncMock(return_value=None))
        await handle.start()
        assert captured["env"]["ANIMAWORKS_INTERNAL_AUTH"] == "sora.abc123"


def _codex_stub(tmp_path: Path):
    return SimpleNamespace(
        _anima_dir=tmp_path,
        _codex_home=tmp_path / ".codex",
        _model_config=SimpleNamespace(
            credential_type="openai",
            api_base_url=None,
            extra_keys={},
            model="codex/gpt-5.6",
        ),
        _resolve_api_key=lambda: None,
        _uses_codex_login_auth=lambda: True,
    )


class TestExplicitEnvPassthrough:
    def test_codex_cli_env(self, monkeypatch, tmp_path):
        from core.execution.engines.codex import setup as codex_setup

        monkeypatch.setenv("ANIMAWORKS_INTERNAL_AUTH", "sora.mytoken")
        env = codex_setup.CodexSetupMixin._build_env(_codex_stub(tmp_path))
        assert env.get("ANIMAWORKS_INTERNAL_AUTH") == "sora.mytoken"

    def test_codex_mcp_env(self, monkeypatch, tmp_path):
        from core.execution.engines.codex import setup as codex_setup

        monkeypatch.setenv("ANIMAWORKS_INTERNAL_AUTH", "sora.mytoken")
        env = codex_setup.CodexSetupMixin._build_mcp_env(_codex_stub(tmp_path))
        assert env.get("ANIMAWORKS_INTERNAL_AUTH") == "sora.mytoken"

    def test_claude_sdk_mcp_env(self, monkeypatch, tmp_path):
        from core.execution.engines.claude import _sdk_options as sdk

        monkeypatch.setenv("ANIMAWORKS_INTERNAL_AUTH", "sora.mytoken")
        obj = SimpleNamespace(_anima_dir=tmp_path)
        monkeypatch.setattr("core.execution.session.session_context.current_runtime_session", lambda: None)
        env = sdk.SDKOptionsMixin._build_mcp_env(obj)
        assert env.get("ANIMAWORKS_INTERNAL_AUTH") == "sora.mytoken"


class TestInternalApiHeaders:
    def test_env_precedence(self, monkeypatch):
        monkeypatch.setenv("ANIMAWORKS_INTERNAL_AUTH", "env-token")
        from core.internal_api import internal_api_headers

        assert internal_api_headers() == {"X-AnimaWorks-Internal-Auth": "env-token"}

    def test_file_fallback(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ANIMAWORKS_INTERNAL_AUTH", raising=False)
        run = tmp_path / "run"
        run.mkdir()
        (run / "internal_api.auth").write_text("file-token", encoding="utf-8")
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)
        from core.internal_api import internal_api_headers

        assert internal_api_headers() == {"X-AnimaWorks-Internal-Auth": "file-token"}

    def test_none_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ANIMAWORKS_INTERNAL_AUTH", raising=False)
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)
        from core.internal_api import internal_api_headers

        assert internal_api_headers() == {}


def test_internal_auth_required_string_exists():
    from core.i18n import t

    assert t("server.internal_auth_required")


def test_anima_named_operator_is_verified_as_anima() -> None:
    from server.internal_auth import InternalAuth as _Auth

    auth = _Auth.generate()
    caller = auth.verify(auth.token_for_anima("operator"))
    assert caller is not None
    assert caller.kind == "anima"
    assert caller.name == "operator"
    op = auth.verify(auth.operator_token())
    assert op is not None and op.kind == "operator"
