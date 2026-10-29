from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_host_api_uses_anima_token_and_configured_server_url(monkeypatch) -> None:
    from core.host_api import HostAPIClient

    monkeypatch.setenv("ANIMAWORKS_SERVER_URL", "http://root.test:18500/")
    monkeypatch.setenv("ANIMAWORKS_INTERNAL_AUTH", "alice.per-anima-token")
    response = MagicMock()

    with patch("httpx.request", return_value=response) as request:
        result = HostAPIClient().post(
            "/api/internal/example",
            json={"value": 1},
            timeout=5.0,
        )

    assert result is response
    request.assert_called_once_with(
        "POST",
        "http://root.test:18500/api/internal/example",
        headers={"X-AnimaWorks-Internal-Auth": "alice.per-anima-token"},
        json={"value": 1},
        timeout=5.0,
    )


def test_host_api_keep_alive_client_inherits_auth(monkeypatch) -> None:
    from core.host_api import HostAPIClient

    monkeypatch.setenv("ANIMAWORKS_INTERNAL_AUTH", "alice.per-anima-token")
    host = HostAPIClient()

    with patch("httpx.Client") as client_factory:
        client = host.http_client(base_url="http://root.test/api/internal/vector", timeout=12.0)

    assert client is client_factory.return_value
    client_factory.assert_called_once_with(
        base_url="http://root.test/api/internal/vector",
        timeout=12.0,
        headers={"X-AnimaWorks-Internal-Auth": "alice.per-anima-token"},
    )
