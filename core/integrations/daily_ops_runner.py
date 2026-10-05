# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Daily Ops Dashboard runner control CLI.

This tool is intentionally narrow: it only talks to the local Daily Ops
Dashboard runner endpoints that are safe for Anima-owned operations.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any

EXECUTION_PROFILE = {
    "start": {"expected_seconds": 10, "background_eligible": True},
    "status": {"expected_seconds": 5, "background_eligible": True},
    "stop": {"expected_seconds": 10, "background_eligible": True},
    "restart": {"expected_seconds": 15, "background_eligible": True},
    "sakura-audit-preview": {"expected_seconds": 10, "background_eligible": True},
    "sakura-approve": {"expected_seconds": 30, "background_eligible": True},
}


_RUNNER_ENDPOINTS = {
    "atc": "affiliate-auto-atc-plan",
    "frt": "affiliate-auto-frt-plan",
    "gnr": "affiliate-auto-plan",
}

_RUNNER_METHODS = {
    "atc": "Atc",
    "frt": "Frt",
    "gnr": "Gnr",
}


def _request_json(url: str, *, method: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc.reason}") from exc

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {"raw": body}
    if isinstance(payload, dict):
        payload.setdefault("http_status", status)
        return payload
    return {"http_status": status, "data": payload}


def _build_url(base_url: str, runner: str, action: str) -> str:
    base = base_url.rstrip("/")
    slug = _RUNNER_ENDPOINTS[runner]
    return f"{base}/api/runner/{slug}/{action}"


def _build_sakura_audit_url(base_url: str, runner: str, endpoint: str, limit: int) -> str:
    base = base_url.rstrip("/")
    method = _RUNNER_METHODS[runner]
    safe_limit = max(1, min(int(limit or 100), 500))
    return f"{base}/api/articles/coverage/{endpoint}?method={method}&limit={safe_limit}"


def cli_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="animaworks-tool daily_ops_runner")
    parser.add_argument(
        "action",
        choices=("start", "status", "stop", "restart", "sakura-audit-preview", "sakura-approve"),
    )
    parser.add_argument("--runner", choices=sorted(_RUNNER_ENDPOINTS), required=True)
    parser.add_argument("--dashboard-url", default="http://127.0.0.1:8787")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("-j", "--json", action="store_true")
    args = parser.parse_args(argv)

    if args.action == "sakura-audit-preview":
        method = "GET"
        url = _build_sakura_audit_url(args.dashboard_url, args.runner, "sakura-audit-queue", args.limit)
        result = _request_json(url, method=method, timeout=args.timeout)
    elif args.action == "sakura-approve":
        preview_url = _build_sakura_audit_url(args.dashboard_url, args.runner, "sakura-audit-queue", args.limit)
        approve_url = _build_sakura_audit_url(args.dashboard_url, args.runner, "sakura-approve", args.limit)
        preview = _request_json(preview_url, method="GET", timeout=args.timeout)
        approve = _request_json(approve_url, method="POST", timeout=args.timeout)
        result = {
            "ok": bool(approve.get("ok", True)),
            "preview": {
                "url": preview_url,
                "queueCount": preview.get("queueCount"),
                "beforeSummary": preview.get("beforeSummary"),
                "afterSummary": preview.get("afterSummary"),
            },
            "approve": approve,
            "updatedCount": approve.get("updatedCount"),
            "afterSummary": approve.get("afterSummary"),
            "reportText": approve.get("reportText"),
        }
        method = "POST"
        url = approve_url
    else:
        method = "POST"
        url = _build_url(args.dashboard_url, args.runner, args.action)
        result = _request_json(url, method=method, timeout=args.timeout)
    result.update(
        {
            "ok": bool(result.get("ok", True)),
            "runner": args.runner,
            "action": args.action,
            "url": url,
            "method": method,
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli_main(sys.argv[1:])
