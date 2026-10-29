from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Authenticated client for requests from AnimaWorks workers to the root host."""

import os
import threading
from typing import Any
from urllib.parse import urljoin


class HostAPIClient:
    """Centralize root URL resolution and per-process internal authentication."""

    def __init__(self) -> None:
        self._clients: dict[tuple[str, tuple[tuple[str, str], ...], str], Any] = {}
        self._clients_lock = threading.Lock()
        self._pid = os.getpid()

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make one request to the host, adding this process's internal token.

        The returned ``httpx.Response`` is not automatically raised so callers
        can preserve endpoint-specific HTTP error handling.
        """
        import httpx

        from core.internal_api import internal_api_headers
        from core.platform.env import server_url

        base_url = server_url()
        url = path if path.startswith(("http://", "https://")) else urljoin(f"{base_url}/", path.lstrip("/"))
        provided_headers = kwargs.pop("headers", None) or {}
        headers = {**internal_api_headers(), **provided_headers}
        return httpx.request(method.upper(), url, headers=headers, **kwargs)

    def get(self, path: str, **kwargs: Any) -> Any:
        """Send a GET request to the root host."""
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        """Send a POST request to the root host."""
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        """Send a PUT request to the root host."""
        return self.request("PUT", path, **kwargs)

    def http_client(self, *, base_url: str | None = None, timeout: Any = 30.0) -> Any:
        """Return a cached keep-alive ``httpx.Client`` with the same auth policy."""
        import httpx

        from core.internal_api import internal_api_headers
        from core.platform.env import server_url

        resolved_base = (base_url or server_url()).rstrip("/")
        headers = internal_api_headers()
        cache_key = (resolved_base, tuple(sorted(headers.items())), repr(timeout))
        with self._clients_lock:
            pid = os.getpid()
            if pid != self._pid:
                self._clients = {}
                self._pid = pid
            client = self._clients.get(cache_key)
            if client is None or getattr(client, "is_closed", False):
                client = httpx.Client(base_url=resolved_base, timeout=timeout, headers=headers)
                self._clients[cache_key] = client
            return client


def response_detail(response: Any) -> str:
    """Return a useful detail string from an unsuccessful host API response."""
    try:
        payload = response.json()
    except Exception:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(payload, dict):
        detail = payload.get("detail", payload.get("error", payload))
        return str(detail)
    return str(payload)


host_api = HostAPIClient()

__all__ = ["HostAPIClient", "host_api", "response_detail"]
