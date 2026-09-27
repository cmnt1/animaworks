from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

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


async def test_usage_response_contains_only_provider_fields(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(usage_routes.create_usage_router(), prefix="/api")
    monkeypatch.setattr(usage_routes, "_fetch_claude_usage", lambda **kwargs: {"provider": "claude"})
    monkeypatch.setattr(usage_routes, "_fetch_openai_usage", lambda **kwargs: {"provider": "openai"})
    monkeypatch.setattr(usage_routes, "_fetch_nanogpt_usage", lambda **kwargs: {"provider": "nanogpt"})
    monkeypatch.setattr(usage_routes, "_merge_usage_snapshot", lambda payload: payload)
    monkeypatch.setattr(usage_routes, "_usage_snapshot_path", lambda: tmp_path / "usage_snapshot.json")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/usage?skip_cache=true")

    assert response.status_code == 200
    assert set(response.json()) == {"claude", "openai", "nanogpt", "cached_at", "snapshot_path"}
