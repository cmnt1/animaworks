# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from core.platform.env import SERVER_URL_ENV, get_env

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────

_DEFAULT_GATEWAY_URL = "http://localhost:18500"
_ENV_GATEWAY_URL = "ANIMAWORKS_GATEWAY_URL"


# ── Public API ────────────────────────────────────────────


def resolve_gateway_url(args: argparse.Namespace) -> str:
    """Resolve the gateway URL from CLI args or environment variable.

    Priority: ``--gateway-url`` flag > configured server URL >
    ``ANIMAWORKS_GATEWAY_URL`` (legacy) > default.
    """
    if getattr(args, "gateway_url", None):
        return args.gateway_url
    return get_env(SERVER_URL_ENV) or get_env(_ENV_GATEWAY_URL) or _DEFAULT_GATEWAY_URL


def gateway_request(
    args: argparse.Namespace,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
    raw_response: bool = False,
) -> Any:
    """Make an HTTP request to the gateway, handling connection errors.

    Args:
        args: Parsed CLI namespace (used to resolve gateway URL).
        method: HTTP method (``GET``, ``POST``, etc.).
        path: URL path appended to the gateway base (e.g. ``/api/animas``).
        json: Optional JSON body for the request.
        headers: Optional request headers, for authenticated internal endpoints.
        timeout: Request timeout in seconds.
        raw_response: Return the ``httpx.Response`` and propagate request errors so
            the caller can preserve command-specific status handling and fallbacks.

    Returns:
        Parsed JSON response body, or the raw response when ``raw_response`` is
        true.

    Raises:
        SystemExit: On connection error, timeout, or HTTP error in JSON mode.
        httpx.HTTPError: In raw response mode, request errors are propagated to
            the caller.
    """
    import httpx

    gateway = resolve_gateway_url(args)
    url = f"{gateway}{path}"
    logger.debug("Gateway %s %s (timeout=%.1fs)", method, url, timeout)

    try:
        request_kwargs: dict[str, Any] = {"json": json, "timeout": timeout}
        if headers is not None:
            request_kwargs["headers"] = headers
        resp = httpx.request(method, url, **request_kwargs)
        return resp if raw_response else resp.json()
    except httpx.ConnectError:
        if raw_response:
            raise
        print(f"Cannot connect to gateway at {gateway}. Use --local for direct mode.")
        sys.exit(1)
    except httpx.TimeoutException:
        if raw_response:
            raise
        print(f"Request timed out after {timeout}s.")
        sys.exit(1)
    except httpx.HTTPError as exc:
        if raw_response:
            raise
        print(f"HTTP error: {exc}")
        sys.exit(1)
