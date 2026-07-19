from __future__ import annotations

import email.message
import io
import json
import time
import urllib.error
from pathlib import Path

from server.routes import usage_routes


def _http_error(url: str, code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError(url, code, "err", hdrs, io.BytesIO(b"{}"))


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

    monkeypatch.setattr(
        usage_routes, "_read_codex_auth_data", lambda: (auth_path, {"tokens": {"access_token": "token"}})
    )

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


def test_relogin_claude_no_terminal_when_launch_disabled_and_refresh_fails(monkeypatch):
    """Automatic callers (launch_terminal=False) must never spawn a CMD window,
    even when the token is expired and the silent refresh fails."""
    launched: list[str] = []
    expired_at = int(time.time() * 1000) - 10 * 60 * 1000

    monkeypatch.setattr(usage_routes, "_CACHE", {"claude": ({"stale": True}, time.time())})
    monkeypatch.setattr(usage_routes, "get_claude_executable", lambda: "C:\\Tools\\claude.exe")
    monkeypatch.setattr(
        usage_routes,
        "_select_best_claude_credential",
        lambda: (Path("credentials.json"), "access-token", "refresh-token", expired_at),
    )
    # Silent refresh fails → would normally fall through to launching a terminal.
    monkeypatch.setattr(usage_routes, "_refresh_claude_token", lambda path, refresh: None)
    monkeypatch.setattr(
        usage_routes,
        "_launch_claude_login_terminal",
        lambda executable: launched.append(executable) or True,
    )

    payload, _status = usage_routes._relogin_claude(launch_terminal=False)

    assert payload["success"] is False
    assert payload["terminal_launched"] is False
    assert launched == []  # no CMD window spawned


def test_relogin_claude_launches_terminal_when_interactive_and_refresh_fails(monkeypatch):
    """Explicit user action (launch_terminal=True) still opens the CMD window
    when the token is expired and the refresh fails."""
    launched: list[str] = []
    expired_at = int(time.time() * 1000) - 10 * 60 * 1000

    monkeypatch.setattr(usage_routes, "_CACHE", {"claude": ({"stale": True}, time.time())})
    monkeypatch.setattr(usage_routes, "get_claude_executable", lambda: "C:\\Tools\\claude.exe")
    monkeypatch.setattr(
        usage_routes,
        "_select_best_claude_credential",
        lambda: (Path("credentials.json"), "access-token", "refresh-token", expired_at),
    )
    monkeypatch.setattr(usage_routes, "_refresh_claude_token", lambda path, refresh: None)
    monkeypatch.setattr(
        usage_routes,
        "_launch_claude_login_terminal",
        lambda executable: launched.append(executable) or True,
    )

    payload, _status = usage_routes._relogin_claude(launch_terminal=True)

    assert payload["terminal_launched"] is True
    assert launched == ["C:\\Tools\\claude.exe"]


def _stub_claude_usage(monkeypatch, raw: dict[str, object]) -> None:
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_read_claude_token", lambda: "access-token")
    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", lambda req, timeout=0: _FakeResponse(raw))


def test_fetch_claude_usage_omits_window_missing_utilization(monkeypatch):
    # A window with no utilization must be dropped, not reported as 0% used —
    # "100% remaining" would disguise schema drift as an untouched quota.
    _stub_claude_usage(
        monkeypatch,
        {
            "five_hour": {"resets_at": "2026-07-16T10:09:59+00:00"},
            "seven_day": {"utilization": 0.0, "resets_at": "2026-07-18T09:59:59+00:00"},
        },
    )

    result = usage_routes._fetch_claude_usage()

    assert "five_hour" not in result
    # A genuine 0.0 still reports 100% remaining — absence and zero stay distinct.
    assert result["seven_day"]["remaining"] == 100.0


def test_fetch_claude_usage_parses_extra_usage_when_enabled(monkeypatch):
    _stub_claude_usage(
        monkeypatch,
        {
            "five_hour": {"utilization": 1.0, "resets_at": "2026-07-16T10:09:59+00:00"},
            "extra_usage": {
                "is_enabled": True,
                "monthly_limit": 5000,
                "used_credits": 1250,
                "utilization": 25.0,
                "currency": "USD",
                "decimal_places": 2,
            },
        },
    )

    result = usage_routes._fetch_claude_usage()

    assert result["extra_usage"] == {
        "utilization": 25.0,
        "remaining": 75.0,
        "used_credits": 1250,
        "monthly_limit": 5000,
        "currency": "USD",
        "decimal_places": 2,
    }


def test_fetch_claude_usage_omits_extra_usage_when_disabled(monkeypatch):
    # Shape observed live while extra usage is turned off: every field is null.
    _stub_claude_usage(
        monkeypatch,
        {
            "five_hour": {"utilization": 1.0, "resets_at": "2026-07-16T10:09:59+00:00"},
            "extra_usage": {
                "is_enabled": False,
                "monthly_limit": None,
                "used_credits": None,
                "utilization": None,
                "currency": None,
                "decimal_places": None,
            },
        },
    )

    result = usage_routes._fetch_claude_usage()

    assert "extra_usage" not in result
    assert result["five_hour"]["utilization"] == 1.0


# ── Rate-limit backoff (Retry-After) ─────────────────────────────────────────


def test_parse_retry_after_variants():
    assert usage_routes._parse_retry_after("120") == 120.0
    # Missing header → default backoff.
    assert usage_routes._parse_retry_after(None) == usage_routes._RATE_LIMIT_BACKOFF_DEFAULT
    # Oversized value is clamped to the max window.
    assert usage_routes._parse_retry_after("99999") == usage_routes._RATE_LIMIT_BACKOFF_MAX


def test_fetch_claude_usage_429_sets_backoff_without_refresh(monkeypatch):
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {})
    monkeypatch.setattr(usage_routes, "_read_claude_token", lambda: "access-token")

    # A 429 must NOT trigger a token refresh — that would only add load.
    def _no_refresh(*a, **k):
        raise AssertionError("token refresh must not be attempted on 429")

    monkeypatch.setattr(usage_routes, "_refresh_claude_token", _no_refresh)
    monkeypatch.setattr(
        usage_routes.urllib.request,
        "urlopen",
        lambda req, timeout=0: (_ for _ in ()).throw(_http_error("https://x", 429, retry_after="90")),
    )

    result = usage_routes._fetch_claude_usage()

    assert result["error"] == "rate_limited"
    assert result["retry_after_s"] > 0
    assert usage_routes._in_rate_limit_backoff("claude")


def test_fetch_claude_usage_backoff_short_circuits_network(monkeypatch):
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {"claude": time.time() + 300})

    def _no_network(*a, **k):
        raise AssertionError("must not hit the endpoint while backing off")

    monkeypatch.setattr(usage_routes, "_read_claude_token", lambda: "access-token")
    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", _no_network)

    # Even an explicit skip_cache refresh must honor the backoff window.
    result = usage_routes._fetch_claude_usage(skip_cache=True)

    assert result["error"] == "rate_limited"


def test_fetch_claude_usage_success_clears_backoff(monkeypatch):
    # A stale (expired) backoff entry must be cleared once a fetch succeeds.
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {"claude": time.time() - 10})
    _stub_claude_usage(
        monkeypatch,
        {"seven_day": {"utilization": 9.0, "resets_at": "2026-07-25T09:59:59+00:00"}},
    )

    result = usage_routes._fetch_claude_usage()

    assert result["provider"] == "claude"
    assert "claude" not in usage_routes._RATE_LIMIT_UNTIL
