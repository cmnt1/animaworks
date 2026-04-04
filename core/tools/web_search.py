# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Web Search tool for AnimaWorks.

Supports two backends:
  - **Brave Search API** (default when ``BRAVE_API_KEY`` is available)
  - **DuckDuckGo HTML lite** (API-key-free fallback)

Backend is resolved automatically at call time via ``_resolve_backend()``.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

logger = logging.getLogger("animaworks.tools.web_search")

# ── Execution Profile ─────────────────────────────────────

EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "search": {"expected_seconds": 15, "background_eligible": False},
}

# ── Backend constants ─────────────────────────────────────

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_LANG_MAP = {"ja": "jp"}

_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_DDG_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_DDG_MIN_INTERVAL = 1.0
_ddg_last_request: float = 0.0


# ── Backend resolution ────────────────────────────────────


def _resolve_backend() -> str:
    """Return ``"brave"`` if an API key is available, else ``"duckduckgo"``."""
    try:
        from core.tools._base import get_credential

        get_credential("brave", "web_search", env_var="BRAVE_API_KEY")
        return "brave"
    except Exception:
        return "duckduckgo"


# ── Brave backend ─────────────────────────────────────────


def _search_brave(
    query: str,
    count: int,
    lang: str,
    country: str = "US",
    freshness: str | None = None,
) -> list[dict[str, str]]:
    from core.tools._base import get_credential

    api_key = get_credential("brave", "web_search", env_var="BRAVE_API_KEY")
    search_lang = _BRAVE_LANG_MAP.get(lang, lang)

    params: dict[str, Any] = {
        "q": query,
        "count": count,
        "search_lang": search_lang,
        "country": country,
    }
    if freshness:
        params["freshness"] = freshness

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }

    response = httpx.get(
        _BRAVE_SEARCH_URL,
        params=params,
        headers=headers,
        timeout=30.0,
    )
    response.raise_for_status()

    data = response.json()
    results: list[dict[str, str]] = []
    for item in data.get("web", {}).get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
            }
        )
    return results


# ── DuckDuckGo backend ────────────────────────────────────


def _search_duckduckgo(
    query: str,
    count: int,
    lang: str,
) -> list[dict[str, str]]:
    global _ddg_last_request  # noqa: PLW0603

    elapsed = time.monotonic() - _ddg_last_request
    if elapsed < _DDG_MIN_INTERVAL:
        time.sleep(_DDG_MIN_INTERVAL - elapsed)

    headers = {
        "User-Agent": _DDG_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{lang},en;q=0.5" if lang else "en",
    }

    response = httpx.post(
        _DDG_HTML_URL,
        data={"q": query},
        headers=headers,
        timeout=30.0,
        follow_redirects=True,
    )
    response.raise_for_status()
    _ddg_last_request = time.monotonic()

    results = _parse_ddg_html(response.text, count)
    if not results:
        logger.warning("DuckDuckGo returned 0 results for query=%r — HTML structure may have changed", query)
    return results


def _parse_ddg_html(html_text: str, max_results: int) -> list[dict[str, str]]:
    """Parse DuckDuckGo HTML lite search results."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.warning("bs4 not installed, falling back to regex parsing")
        return _parse_ddg_regex(html_text, max_results)

    soup = BeautifulSoup(html_text, "html.parser")
    results: list[dict[str, str]] = []

    for div in soup.select(".result"):
        if len(results) >= max_results:
            break

        classes = " ".join(div.get("class", []))
        if "result--ad" in classes:
            continue

        a_tag = div.select_one("a.result__a")
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        raw_href = a_tag.get("href", "")
        url = _extract_ddg_url(raw_href)
        if not url or not url.startswith("http"):
            continue

        snippet_el = div.select_one(".result__snippet")
        desc = snippet_el.get_text(strip=True) if snippet_el else ""

        results.append(
            {
                "title": title,
                "url": url,
                "description": desc,
            }
        )

    return results


def _extract_ddg_url(raw_href: str) -> str:
    """Extract the actual URL from a DuckDuckGo redirect link."""
    if not raw_href:
        return ""
    parsed = urlparse(raw_href)
    qs = parse_qs(parsed.query)
    uddg = qs.get("uddg")
    if uddg:
        url = uddg[0]
        if "duckduckgo.com/y.js" in url:
            return ""
        return url
    if raw_href.startswith("http"):
        return raw_href
    return ""


def _parse_ddg_regex(html_text: str, max_results: int) -> list[dict[str, str]]:
    """Fallback regex parser when bs4 is unavailable."""
    results: list[dict[str, str]] = []

    block_re = re.compile(
        r'<div\s+[^>]*class="[^"]*web-result[^"]*"[^>]*>(.*?)</div>\s*</div>',
        re.DOTALL | re.IGNORECASE,
    )
    link_re = re.compile(
        r'<a\s+[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    snippet_re = re.compile(
        r'class="result__snippet"[^>]*>(.*?)</[a-z]',
        re.DOTALL | re.IGNORECASE,
    )

    for block_match in block_re.finditer(html_text):
        if len(results) >= max_results:
            break
        block = block_match.group(1)

        link_match = link_re.search(block)
        if not link_match:
            continue

        raw_href = html.unescape(link_match.group(1))
        url = _extract_ddg_url(raw_href)
        if not url or not url.startswith("http"):
            continue

        title = _strip_html(link_match.group(2))

        snippet_match = snippet_re.search(block)
        desc = _strip_html(snippet_match.group(1)) if snippet_match else ""

        results.append(
            {
                "title": title,
                "url": url,
                "description": desc,
            }
        )

    return results


# ── Public API ────────────────────────────────────────────


def search(
    query: str,
    count: int = 10,
    lang: str = "ja",
    country: str = "US",
    freshness: str | None = None,
    **_kwargs: Any,
) -> list[dict[str, str]]:
    """Search the web and return a list of result dicts.

    Backend is selected automatically: Brave if ``BRAVE_API_KEY`` is set,
    otherwise DuckDuckGo HTML lite (no key required).

    Each dict contains ``title``, ``url``, and ``description`` keys.
    """
    count = min(max(count, 1), 20)
    backend = _resolve_backend()

    if backend == "brave":
        logger.debug("web_search: using Brave backend")
        return _search_brave(query, count, lang, country=country, freshness=freshness)

    logger.debug("web_search: using DuckDuckGo backend (no BRAVE_API_KEY)")
    return _search_duckduckgo(query, count, lang)


# ── Text formatting helpers ───────────────────────────────


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def format_results(results: list[dict[str, str]]) -> str:
    """Format search results as human-readable text."""
    if not results:
        return "No results found."

    lines: list[str] = []
    for i, item in enumerate(results, 1):
        title = item.get("title", "No title")
        url = item.get("url", "")
        desc = _strip_html(item.get("description", "No description"))
        lines.append(f"{i}. {title}")
        lines.append(f"   {url}")
        lines.append(f"   {desc}")
        lines.append("")

    return "\n".join(lines)


# ── Tool schema / dispatch ────────────────────────────────


def get_tool_schemas() -> list[dict]:
    """Return Anthropic tool_use schemas for the web_search tool."""
    return []


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call by schema name."""
    if name == "web_search":
        args.pop("anima_dir", None)
        if "limit" in args:
            args["count"] = args.pop("limit")
        return search(**args)
    raise ValueError(f"Unknown tool: {name}")


# ── CLI entry point ───────────────────────────────────────


def cli_main(argv: list[str] | None = None) -> None:
    """Thin CLI entry point for web_search."""
    parser = argparse.ArgumentParser(
        description="Search the web (Brave API or DuckDuckGo fallback)",
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=10,
        help="Number of results (1-20, default: 10)",
    )
    parser.add_argument(
        "-l",
        "--lang",
        default="ja",
        help="Search language (e.g. ja, en)",
    )
    parser.add_argument(
        "-f",
        "--freshness",
        choices=["pd", "pw", "pm", "py"],
        help="Freshness filter (Brave only): pd=24h, pw=1week, pm=1month, py=1year",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--backend",
        choices=["brave", "duckduckgo", "auto"],
        default="auto",
        help="Search backend (default: auto)",
    )

    args = parser.parse_args(argv)

    if args.backend == "auto":
        results = search(
            query=args.query,
            count=args.count,
            lang=args.lang,
            freshness=args.freshness,
        )
    elif args.backend == "brave":
        results = _search_brave(
            query=args.query,
            count=min(max(args.count, 1), 20),
            lang=args.lang,
            freshness=args.freshness,
        )
    else:
        results = _search_duckduckgo(
            query=args.query,
            count=min(max(args.count, 1), 20),
            lang=args.lang,
        )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(format_results(results))
