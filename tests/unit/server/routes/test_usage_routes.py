from __future__ import annotations

import io
import json
import time
import urllib.error
from pathlib import Path

from server.routes import usage_routes


def _jwt(payload: dict[str, object]) -> str:
    import base64

    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode("utf-8").rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"{header}.{body}.sig"


class _FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self.status = 200
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeTextResponse:
    def __init__(self, text: str):
        self.status = 200
        self._body = text.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_refresh_codex_token_updates_auth_file(tmp_path: Path, monkeypatch):
    auth_path = tmp_path / "auth.json"
    auth_data = {
        "auth_mode": "chatgpt",
        "tokens": {
            "access_token": _jwt(
                {
                    "client_id": "client-123",
                    "https://api.openai.com/auth": {
                        "chatgpt_account_id": "acct-old",
                    },
                }
            ),
            "refresh_token": "refresh-123",
            "account_id": "acct-old",
        },
    }
    auth_path.write_text(json.dumps(auth_data), encoding="utf-8")

    def fake_urlopen(req, timeout=0):
        assert req.full_url == "https://auth.openai.com/oauth/token"
        body = json.loads(req.data.decode("utf-8"))
        assert body["grant_type"] == "refresh_token"
        assert body["client_id"] == "client-123"
        assert body["refresh_token"] == "refresh-123"
        return _FakeResponse(
            {
                "access_token": _jwt(
                    {
                        "client_id": "client-123",
                        "https://api.openai.com/auth": {
                            "chatgpt_account_id": "acct-new",
                        },
                    }
                ),
                "id_token": _jwt({"aud": ["client-123"]}),
                "refresh_token": "refresh-456",
            }
        )

    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", fake_urlopen)
    token, account_id = usage_routes._refresh_codex_token(auth_path, auth_data)

    saved = json.loads(auth_path.read_text("utf-8"))
    assert token == saved["tokens"]["access_token"]
    assert account_id == "acct-new"
    assert saved["tokens"]["account_id"] == "acct-new"
    assert saved["tokens"]["refresh_token"] == "refresh-456"
    assert "last_refresh" in saved


def test_fetch_openai_usage_refreshes_after_401(monkeypatch):
    old_token = _jwt(
        {
            "client_id": "client-123",
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "acct-123",
            },
        }
    )
    new_token = _jwt(
        {
            "client_id": "client-123",
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "acct-123",
            },
        }
    )

    calls: list[str] = []

    def fake_read_codex_credentials():
        if calls:
            return new_token, "acct-123"
        return old_token, "acct-123"

    def fake_urlopen(req, timeout=0):
        calls.append(req.headers.get("Authorization", ""))
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                req.full_url,
                401,
                "Unauthorized",
                hdrs=None,
                fp=io.BytesIO(b'{"error":{"code":"token_expired"}}'),
            )
        return _FakeResponse(
            {
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 12,
                        "reset_at": 1775000000,
                        "limit_window_seconds": 18000,
                    },
                    "secondary_window": {
                        "used_percent": 34,
                        "reset_at": 1775400000,
                        "limit_window_seconds": 604800,
                    },
                }
            }
        )

    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_read_codex_credentials", fake_read_codex_credentials)
    monkeypatch.setattr(usage_routes, "_read_codex_auth_data", lambda: (Path("auth.json"), {"tokens": {}}))
    monkeypatch.setattr(usage_routes, "_refresh_codex_token", lambda path, data: (new_token, "acct-123"))
    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", fake_urlopen)

    result = usage_routes._fetch_openai_usage(skip_cache=True)

    assert result["provider"] == "openai"
    assert result["5h"]["remaining"] == 88
    assert result["Week"]["remaining"] == 66
    assert len(calls) == 2


def test_openai_subscription_codex_home_uses_usage_governor_auth_path(tmp_path: Path, monkeypatch):
    auth_path = tmp_path / "codex-home" / "auth.json"
    auth_path.parent.mkdir()
    auth_path.write_text(json.dumps({"tokens": {"access_token": "token"}}), encoding="utf-8")

    monkeypatch.setattr(usage_routes, "_read_codex_auth_data", lambda: (auth_path, {"tokens": {"access_token": "token"}}))

    assert usage_routes.get_openai_subscription_codex_home() == auth_path.parent


def test_relogin_claude_does_not_launch_terminal_when_token_is_fresh(monkeypatch):
    launched: list[str] = []
    expires_at = int(time.time() * 1000) + 10 * 60 * 1000

    monkeypatch.setattr(usage_routes, "_CACHE", {"claude": ({"stale": True}, time.time())})
    monkeypatch.setattr(usage_routes, "get_claude_executable", lambda: "C:\\Tools\\claude.exe")
    monkeypatch.setattr(
        usage_routes,
        "_select_best_claude_credential",
        lambda: (Path("credentials.json"), "access-token", "refresh-token", expires_at),
    )
    monkeypatch.setattr(
        usage_routes,
        "_launch_claude_login_terminal",
        lambda executable: launched.append(executable) or True,
    )

    payload, status_code = usage_routes._relogin_claude()

    assert status_code == 200
    assert payload["success"] is True
    assert payload["terminal_launched"] is False
    assert "already fresh" in payload["message"]
    assert launched == []
    assert "claude" not in usage_routes._CACHE


def test_parse_opencode_go_dashboard_window_handles_field_order():
    html = "rollingUsage:$R[7]={resetInSec:7200,usagePercent:30}"

    assert usage_routes._parse_opencode_go_window(html, "rollingUsage") == (30.0, 7200.0)


def test_fetch_opencode_go_usage_scrapes_dashboard_windows(monkeypatch):
    html = (
        "rollingUsage:$R[1]={usagePercent:7,resetInSec:18000}"
        "weeklyUsage:$R[2]={usagePercent:22,resetInSec:540000}"
        "monthlyUsage:$R[3]={resetInSec:2480000,usagePercent:64}"
    )
    calls: list[str] = []

    def fake_urlopen(req, timeout=0):
        calls.append(req.full_url)
        assert req.headers["Cookie"] == "auth=cookie-abc"
        return _FakeTextResponse(html)

    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(
        usage_routes,
        "_read_opencode_go_dashboard_config",
        lambda: ("ws-123", "cookie-abc", "env", None),
    )
    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", fake_urlopen)

    result = usage_routes._fetch_opencode_go_usage(skip_cache=True)

    assert calls == ["https://opencode.ai/workspace/ws-123/go"]
    assert result["provider"] == "opencode_go"
    assert result["5h"]["remaining"] == 93
    assert result["Week"]["remaining"] == 78
    assert result["Month"]["remaining"] == 36
