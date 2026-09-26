from __future__ import annotations

import email.message
import io
import json
import time
import urllib.error
from pathlib import Path

from server.routes import usage_routes


def _http_error(
    code: int, *, url: str = "https://x", retry_after: str | None = None, body: bytes = b"{}"
) -> urllib.error.HTTPError:
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError(url, code, "err", hdrs, io.BytesIO(body))


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

    def fake_urlopen(req, timeout=0, context=None):
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

    def fake_urlopen(req, timeout=0, context=None):
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


def test_fetch_openai_usage_uses_certifi_tls_context(monkeypatch):
    tls_context = object()
    observed_contexts: list[object | None] = []

    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {})
    monkeypatch.setattr(
        usage_routes,
        "get_openai_subscription_auth_headers",
        lambda **kwargs: {"Authorization": "Bearer token"},
    )
    monkeypatch.setattr(usage_routes, "_outbound_tls_context", lambda: tls_context)

    def fake_urlopen(req, timeout=0, context=None):
        observed_contexts.append(context)
        return _FakeResponse({"rate_limit": {}})

    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", fake_urlopen)

    result = usage_routes._fetch_openai_usage(skip_cache=True)

    assert result == {"provider": "openai"}
    assert observed_contexts == [tls_context]


def test_fetch_openai_usage_caches_transport_failure(monkeypatch):
    calls = 0

    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {})
    monkeypatch.setattr(
        usage_routes,
        "get_openai_subscription_auth_headers",
        lambda **kwargs: {"Authorization": "Bearer token"},
    )

    def fake_urlopen(req, timeout=0, context=None):
        nonlocal calls
        calls += 1
        raise urllib.error.URLError("TLS failed")

    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", fake_urlopen)

    first = usage_routes._fetch_openai_usage()
    second = usage_routes._fetch_openai_usage()

    assert first["error"] == "fetch_failed"
    assert second == first
    assert calls == 1


def test_openai_subscription_codex_home_uses_usage_governor_auth_path(tmp_path: Path, monkeypatch):
    auth_path = tmp_path / "codex-home" / "auth.json"
    auth_path.parent.mkdir()
    auth_path.write_text(json.dumps({"tokens": {"access_token": "token"}}), encoding="utf-8")

    monkeypatch.setattr(
        usage_routes, "_read_codex_auth_data", lambda: (auth_path, {"tokens": {"access_token": "token"}})
    )

    assert usage_routes.get_openai_subscription_codex_home() == auth_path.parent


def _stub_fresh_claude_credential(monkeypatch) -> None:
    expires_at = int(time.time() * 1000) + 60 * 60 * 1000
    monkeypatch.setattr(
        usage_routes,
        "_select_best_claude_credential",
        lambda: (Path("credentials.json"), "access-token", "refresh-token", expires_at),
    )


def test_relogin_claude_does_not_launch_terminal_when_token_is_fresh(monkeypatch):
    launched: list[str] = []

    monkeypatch.setattr(usage_routes, "_CACHE", {"claude": ({"stale": True}, time.time())})
    monkeypatch.setattr(usage_routes, "get_claude_executable", lambda: "C:\\Tools\\claude.exe")
    _stub_fresh_claude_credential(monkeypatch)
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


def test_relogin_claude_read_only_when_launch_disabled(monkeypatch):
    """Automatic callers (interactive=False) are read-only: for an expired
    token they neither refresh the shared credentials file nor spawn a window."""
    launched: list[str] = []
    refreshed: list[str] = []
    expired_at = int(time.time() * 1000) - 10 * 60 * 1000

    monkeypatch.setattr(usage_routes, "_CACHE", {"claude": ({"stale": True}, time.time())})
    monkeypatch.setattr(usage_routes, "get_claude_executable", lambda: "C:\\Tools\\claude.exe")
    monkeypatch.setattr(
        usage_routes,
        "_select_best_claude_credential",
        lambda: (Path("credentials.json"), "access-token", "refresh-token", expired_at),
    )
    monkeypatch.setattr(usage_routes, "_refresh_claude_token", lambda path, refresh: refreshed.append(refresh) or None)
    monkeypatch.setattr(
        usage_routes,
        "_launch_claude_login_terminal",
        lambda executable: launched.append(executable) or True,
    )

    payload, _status = usage_routes._relogin_claude(interactive=False)

    assert payload["success"] is False
    assert payload["terminal_launched"] is False
    assert launched == []  # no CMD window spawned
    assert refreshed == []  # and the shared token is never rewritten


def test_fetch_claude_usage_expired_token_short_circuits_network(monkeypatch):
    expired_at = int(time.time() * 1000) - 10 * 60 * 1000
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {})
    monkeypatch.setattr(usage_routes, "_AUTO_REFRESH_LAST_ATTEMPT", time.time())
    monkeypatch.setattr(
        usage_routes,
        "_select_best_claude_credential",
        lambda: (Path("credentials.json"), "expired-token", "refresh-token", expired_at),
    )

    def _no_network(*args, **kwargs):
        raise AssertionError("must not hit network with expired token")

    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", _no_network)

    result = usage_routes._fetch_claude_usage()

    assert result == {"error": "unauthorized", "message": "Token expired, re-login to Claude Code"}
    assert usage_routes._cached("claude") == result


def test_fetch_claude_usage_auto_refreshes_idle_expired_token(monkeypatch):
    expired_at = int(time.time() * 1000) - usage_routes._AUTO_REFRESH_GRACE_MS - 60_000
    refresh_calls: list[tuple[Path, str, str | None]] = []
    authorization: list[str | None] = []
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {})
    monkeypatch.setattr(usage_routes, "_AUTO_REFRESH_LAST_ATTEMPT", 0.0)
    monkeypatch.setattr(
        usage_routes,
        "_select_best_claude_credential",
        lambda: (Path("credentials.json"), "expired-token", "refresh-token", expired_at),
    )

    def fake_refresh(path, refresh, expected_access=None):
        refresh_calls.append((path, refresh, expected_access))
        return "refreshed-token"

    def fake_urlopen(req, timeout=0, context=None):
        authorization.append(req.get_header("Authorization"))
        return _FakeResponse(
            {
                "five_hour": {
                    "utilization": 12.0,
                    "resets_at": "2026-08-04T10:00:00+00:00",
                },
                "seven_day": {
                    "utilization": 34.0,
                    "resets_at": "2026-08-09T10:00:00+00:00",
                },
            }
        )

    monkeypatch.setattr(usage_routes, "_refresh_claude_token", fake_refresh)
    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", fake_urlopen)

    result = usage_routes._fetch_claude_usage()

    assert refresh_calls == [(Path("credentials.json"), "refresh-token", "expired-token")]
    assert authorization == ["Bearer refreshed-token"]
    assert result["five_hour"]["remaining"] == 88.0
    assert result["seven_day"]["remaining"] == 66.0


def test_fetch_claude_usage_freshly_expired_token_stays_read_only(monkeypatch):
    expired_at = int(time.time() * 1000) - usage_routes._AUTO_REFRESH_GRACE_MS + 60_000
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {})
    monkeypatch.setattr(usage_routes, "_AUTO_REFRESH_LAST_ATTEMPT", 0.0)
    monkeypatch.setattr(
        usage_routes,
        "_select_best_claude_credential",
        lambda: (Path("credentials.json"), "expired-token", "refresh-token", expired_at),
    )
    monkeypatch.setattr(
        usage_routes,
        "_refresh_claude_token",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not refresh during the owner grace period")),
    )

    result = usage_routes._fetch_claude_usage()

    assert result == {"error": "unauthorized", "message": "Token expired, re-login to Claude Code"}


def test_fetch_claude_usage_auto_refresh_cooldown_blocks_attempt(monkeypatch):
    expired_at = int(time.time() * 1000) - usage_routes._AUTO_REFRESH_GRACE_MS - 60_000
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {})
    monkeypatch.setattr(usage_routes, "_AUTO_REFRESH_LAST_ATTEMPT", time.time())
    monkeypatch.setattr(
        usage_routes,
        "_select_best_claude_credential",
        lambda: (Path("credentials.json"), "expired-token", "refresh-token", expired_at),
    )
    monkeypatch.setattr(
        usage_routes,
        "_refresh_claude_token",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not refresh during cooldown")),
    )

    result = usage_routes._fetch_claude_usage()

    assert result == {"error": "unauthorized", "message": "Token expired, re-login to Claude Code"}


def test_fetch_claude_usage_failed_auto_refresh_records_attempt(monkeypatch):
    expired_at = int(time.time() * 1000) - usage_routes._AUTO_REFRESH_GRACE_MS - 60_000
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {})
    monkeypatch.setattr(usage_routes, "_AUTO_REFRESH_LAST_ATTEMPT", 0.0)
    monkeypatch.setattr(
        usage_routes,
        "_select_best_claude_credential",
        lambda: (Path("credentials.json"), "expired-token", "refresh-token", expired_at),
    )
    monkeypatch.setattr(usage_routes, "_refresh_claude_token", lambda *args, **kwargs: None)
    before = time.time()

    result = usage_routes._fetch_claude_usage()

    assert result == {"error": "unauthorized", "message": "Token expired, re-login to Claude Code"}
    assert before <= usage_routes._AUTO_REFRESH_LAST_ATTEMPT


def test_relogin_claude_launches_terminal_when_interactive_and_refresh_fails(monkeypatch):
    """Explicit user action (interactive=True) still opens the CMD window
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

    payload, _status = usage_routes._relogin_claude(interactive=True)

    assert payload["terminal_launched"] is True
    assert launched == ["C:\\Tools\\claude.exe"]


def _stub_claude_usage(monkeypatch, raw: dict[str, object]) -> None:
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    _stub_fresh_claude_credential(monkeypatch)
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
    _stub_fresh_claude_credential(monkeypatch)

    # A 429 must NOT trigger a token refresh — that would only add load.
    def _no_refresh(*a, **k):
        raise AssertionError("token refresh must not be attempted on 429")

    monkeypatch.setattr(usage_routes, "_refresh_claude_token", _no_refresh)
    monkeypatch.setattr(
        usage_routes.urllib.request,
        "urlopen",
        lambda req, timeout=0: (_ for _ in ()).throw(_http_error(429, retry_after="90")),
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

    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", _no_network)

    # Even an explicit skip_cache refresh must honor the backoff window.
    result = usage_routes._fetch_claude_usage(skip_cache=True)

    assert result["error"] == "rate_limited"


# ── 403 scope handling & scope-preserving refresh ────────────────────────────


def test_fetch_claude_usage_403_scope_returns_scope_insufficient(monkeypatch):
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {})
    _stub_fresh_claude_credential(monkeypatch)
    body = b'{"error":{"type":"permission_error","message":"OAuth token does not meet scope requirement any_of(user:profile)"}}'
    monkeypatch.setattr(
        usage_routes.urllib.request,
        "urlopen",
        lambda req, timeout=0: (_ for _ in ()).throw(_http_error(403, body=body)),
    )

    result = usage_routes._fetch_claude_usage()

    assert result["error"] == "scope_insufficient"
    assert "claude /login" in result["message"]


def test_fetch_claude_usage_403_non_scope_stays_http_error(monkeypatch):
    # permission_error is the type for every 403 here, so a non-scope permission
    # failure must still read as a plain http_error rather than a re-login hint.
    monkeypatch.setattr(usage_routes, "_CACHE", {})
    monkeypatch.setattr(usage_routes, "_RATE_LIMIT_UNTIL", {})
    _stub_fresh_claude_credential(monkeypatch)
    body = b'{"error":{"type":"permission_error","message":"Organization policy forbids this resource"}}'
    monkeypatch.setattr(
        usage_routes.urllib.request,
        "urlopen",
        lambda req, timeout=0: (_ for _ in ()).throw(_http_error(403, body=body)),
    )

    result = usage_routes._fetch_claude_usage()

    assert result == {"error": "http_error", "message": "HTTP 403"}


def test_refresh_claude_token_does_not_send_or_persist_scopes(tmp_path: Path, monkeypatch):
    # RFC 6749 §6: an omitted scope means "everything originally granted", so
    # echoing the stored scopes could only narrow them.  Persisting a narrowed
    # set would then make the next refresh request it explicitly — a one-way
    # ratchet.  Neither may happen.
    cred = tmp_path / "creds.json"
    cred.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "old",
                    "refreshToken": "r1",
                    "scopes": ["user:inference", "user:profile"],
                }
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout=0, context=None):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse(
            {"access_token": "new-tok", "refresh_token": "r2", "expires_in": 3600, "scope": "user:inference"}
        )

    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", fake_urlopen)

    tok = usage_routes._refresh_claude_token(cred, "r1")

    assert tok == "new-tok"
    assert "scope" not in captured["body"]
    saved = json.loads(cred.read_text("utf-8"))["claudeAiOauth"]
    assert saved["accessToken"] == "new-tok"
    # A narrowed grant must not be written back over the stored scopes.
    assert saved["scopes"] == ["user:inference", "user:profile"]


def test_refresh_claude_token_does_not_write_after_persist_read_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(usage_routes, "_AUTO_REFRESH_LAST_ATTEMPT", 0.0)
    cred = tmp_path / "creds.json"
    cred.write_text(
        json.dumps(
            {
                "unrelated": {"preserve": True},
                "claudeAiOauth": {
                    "accessToken": "old",
                    "refreshToken": "r1",
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_urlopen(req, timeout=0, context=None):
        cred.unlink()
        return _FakeResponse(
            {
                "access_token": "new-token",
                "refresh_token": "r2",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", fake_urlopen)

    result = usage_routes._refresh_claude_token(cred, "r1", expected_access="old")

    assert result is None
    assert not cred.exists()


def test_refresh_claude_token_yields_to_concurrent_owner_write(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(usage_routes, "_AUTO_REFRESH_LAST_ATTEMPT", 0.0)
    cred = tmp_path / "creds.json"
    cred.write_text(
        json.dumps(
            {
                "unrelated": {"preserve": True},
                "claudeAiOauth": {
                    "accessToken": "old-token",
                    "refreshToken": "old-refresh",
                },
            }
        ),
        encoding="utf-8",
    )
    owner_data = {
        "unrelated": {"owner": "won"},
        "claudeAiOauth": {
            "accessToken": "owner-token",
            "refreshToken": "owner-refresh",
            "expiresAt": 9999999999999,
        },
    }

    def fake_urlopen(req, timeout=0, context=None):
        cred.write_text(json.dumps(owner_data), encoding="utf-8")
        return _FakeResponse(
            {
                "access_token": "automatic-token",
                "refresh_token": "automatic-refresh",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(usage_routes.urllib.request, "urlopen", fake_urlopen)

    result = usage_routes._refresh_claude_token(
        cred,
        "old-refresh",
        expected_access="old-token",
    )

    assert result == "owner-token"
    assert json.loads(cred.read_text("utf-8")) == owner_data


def test_merge_usage_snapshot_restores_window_timing_after_error(tmp_path: Path, monkeypatch):
    # The snapshot carries each provider's last good entry forward, so an
    # errored live fetch still exposes resets_at/window_seconds — the timing the
    # dashboard needs to draw the progress bar at all.
    snap = tmp_path / "usage_snapshot.json"
    monkeypatch.setattr(usage_routes, "_usage_snapshot_path", lambda: snap)
    good = {
        "provider": "claude",
        "five_hour": {"utilization": 8.0, "resets_at": "2026-07-19T10:00:00+00:00", "window_seconds": 18000},
    }
    usage_routes._save_usage_snapshot({"claude": good})

    merged = usage_routes._merge_usage_snapshot({"claude": {"error": "scope_insufficient"}})

    assert merged["claude"]["five_hour"]["resets_at"] == "2026-07-19T10:00:00+00:00"
    assert merged["snapshot_used"] == ["claude"]
    assert merged["claude"]["live_error"] == {"error": "scope_insufficient"}


def test_snapshot_preserves_current_auth_failure_and_clears_on_recovery(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(usage_routes, "_usage_snapshot_path", lambda: tmp_path / "usage.json")
    good = {"provider": "claude", "five_hour": {"utilization": 8.0}}
    usage_routes._save_usage_snapshot({"claude": good})
    failure = {"error": "unauthorized", "message": "Token expired, re-login to Claude Code"}
    merged = usage_routes._merge_usage_snapshot({"claude": failure})
    assert merged["claude"]["five_hour"] == good["five_hour"]
    assert merged["claude"]["live_error"] == failure
    usage_routes._save_usage_snapshot(merged)

    # A subsequent rate limit must replace the old auth failure, not keep the button.
    limited = usage_routes._merge_usage_snapshot({"claude": {"error": "rate_limited"}})
    assert limited["claude"]["live_error"] == {"error": "rate_limited"}
    recovered = usage_routes._merge_usage_snapshot({"claude": good})
    assert recovered["claude"] == good
    assert "snapshot_used" not in recovered


def test_refresh_claude_token_warns_when_profile_scope_dropped(tmp_path: Path, monkeypatch, caplog):
    import logging

    cred = tmp_path / "creds.json"
    cred.write_text(
        json.dumps({"claudeAiOauth": {"refreshToken": "r1", "scopes": ["user:inference", "user:profile"]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        usage_routes.urllib.request,
        "urlopen",
        lambda req, timeout=0, context=None: _FakeResponse(
            {"access_token": "new", "expires_in": 3600, "scope": "user:inference"}
        ),
    )

    with caplog.at_level(logging.WARNING):
        usage_routes._refresh_claude_token(cred, "r1")

    assert any("user:profile" in r.message for r in caplog.records)


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


# ── Jev (TypeSafe System One prepaid credits) ───────────────────────────────


def _jev_client(tmp_path: Path, monkeypatch, store: dict):
    """Router with config load/save redirected into *store*."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from core.config import models as config_models

    monkeypatch.setenv("JEV_USAGE_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setenv("ANIMAWORKS_JEV_SECRETS_PATH", str(tmp_path / "no_secrets.py"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    class _Config:
        def __init__(self):
            self.jev = store.get("jev", config_models.JevConfig())

    def _load_config():
        return _Config()

    def _save_config(config):
        store["jev"] = config.jev

    monkeypatch.setattr(config_models, "load_config", _load_config)
    monkeypatch.setattr(config_models, "save_config", _save_config)
    usage_routes._CACHE.pop("jev", None)

    app = FastAPI()
    app.include_router(usage_routes.create_usage_router(), prefix="/api")
    return TestClient(app)


def test_jev_settings_put_stamps_the_reading_time(tmp_path: Path, monkeypatch):
    store: dict = {}
    client = _jev_client(tmp_path, monkeypatch, store)

    res = client.put("/api/usage/jev/settings", json={"balance_usd": 20.0, "monthly_budget_usd": 5.0})

    assert res.status_code == 200
    body = res.json()
    assert body["balance_usd"] == 20.0
    assert body["monthly_budget_usd"] == 5.0
    # A baseline is meaningless without the moment it was read.
    assert body["balance_checked_at"]
    assert store["jev"].balance_checked_at == body["balance_checked_at"]
    assert body["usage"]["balance"]["balance_usd"] == 20.0


def test_jev_settings_put_keeps_absent_fields(tmp_path: Path, monkeypatch):
    from core.config.models import JevConfig

    store = {"jev": JevConfig(balance_usd=8.0, balance_checked_at="2026-09-01T00:00:00+09:00")}
    client = _jev_client(tmp_path, monkeypatch, store)

    res = client.put("/api/usage/jev/settings", json={"monthly_budget_usd": 3.0})

    assert res.status_code == 200
    assert res.json()["balance_usd"] == 8.0
    assert store["jev"].balance_checked_at == "2026-09-01T00:00:00+09:00"


def test_jev_settings_put_clears_with_null(tmp_path: Path, monkeypatch):
    from core.config.models import JevConfig

    store = {"jev": JevConfig(balance_usd=8.0, monthly_budget_usd=2.0)}
    client = _jev_client(tmp_path, monkeypatch, store)

    res = client.put("/api/usage/jev/settings", json={"balance_usd": None, "monthly_budget_usd": None})

    assert res.status_code == 200
    assert res.json()["balance_usd"] is None
    assert store["jev"].monthly_budget_usd is None


def test_jev_settings_put_rejects_bad_numbers(tmp_path: Path, monkeypatch):
    client = _jev_client(tmp_path, monkeypatch, {})

    assert client.put("/api/usage/jev/settings", json={"balance_usd": -1}).status_code == 400
    assert client.put("/api/usage/jev/settings", json={"monthly_budget_usd": "abc"}).status_code == 400
    assert client.put("/api/usage/jev/settings", json={"balance_checked_at": "not-a-date"}).status_code == 400


def test_jev_settings_put_invalidates_the_usage_cache(tmp_path: Path, monkeypatch):
    client = _jev_client(tmp_path, monkeypatch, {})
    usage_routes._set_cache("jev", {"provider": "jev", "month": {"budget_usd": None}})

    client.put("/api/usage/jev/settings", json={"monthly_budget_usd": 4.0})

    assert usage_routes._fetch_jev_usage()["month"]["budget_usd"] == 4.0


def test_fetch_jev_usage_survives_a_broken_ledger(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "core.jev_credits.build_status",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    usage_routes._CACHE.pop("jev", None)

    result = usage_routes._fetch_jev_usage(skip_cache=True)

    assert result["error"] == "fetch_failed"
    assert "boom" in result["message"]
