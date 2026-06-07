# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Bluesky search tool for AnimaWorks.

Uses the public Bluesky AppView API by default:
https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import httpx

# ── Execution Profile ─────────────────────────────────────

EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "search": {"expected_seconds": 20, "background_eligible": False},
    "author_feed": {"expected_seconds": 20, "background_eligible": False},
}

DEFAULT_BASE_URL = "https://public.api.bsky.app"
DEFAULT_SERVICE_URL = "https://bsky.social"
USER_AGENT = "AnimaWorks/1.0 (+https://github.com/animaworks)"


class BlueskyClient:
    """Small client for public Bluesky AppView feed endpoints."""

    def __init__(self, base_url: str | None = None, service_url: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("BSKY_APPVIEW_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.service_url = (service_url or os.environ.get("BSKY_SERVICE_URL") or DEFAULT_SERVICE_URL).rstrip("/")
        self._access_jwt: str | None = None

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/xrpc/{endpoint}"
        clean_params = {k: v for k, v in params.items() if v not in (None, "")}
        response = httpx.get(url, params=clean_params, headers={"User-Agent": USER_AGENT}, timeout=30.0)

        if response.status_code == 429:
            raise RuntimeError("Bluesky rate limit exceeded. Try again later.")
        if response.status_code in (401, 403):
            auth_response = self._authenticated_request(endpoint, clean_params)
            if auth_response is not None:
                return auth_response
            raise RuntimeError(
                "Bluesky endpoint requires authentication or denied the request "
                f"({response.status_code}). Set BSKY_IDENTIFIER and BSKY_APP_PASSWORD "
                f"to retry via authenticated bsky.social API. Response: {response.text[:200]}"
            )

        response.raise_for_status()
        return response.json()

    def _authenticated_request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any] | None:
        access_jwt = self._ensure_access_jwt()
        if not access_jwt:
            return None

        response = httpx.get(
            f"{self.service_url}/xrpc/{endpoint}",
            params=params,
            headers={
                "Authorization": f"Bearer {access_jwt}",
                "User-Agent": USER_AGENT,
            },
            timeout=30.0,
        )
        if response.status_code == 429:
            raise RuntimeError("Bluesky rate limit exceeded. Try again later.")
        response.raise_for_status()
        return response.json()

    def _ensure_access_jwt(self) -> str | None:
        if self._access_jwt:
            return self._access_jwt

        identifier = _strip_at(_optional_credential("BSKY_IDENTIFIER"))
        password = _optional_credential("BSKY_APP_PASSWORD")
        if not identifier or not password:
            return None

        response = httpx.post(
            f"{self.service_url}/xrpc/com.atproto.server.createSession",
            json={"identifier": identifier, "password": password},
            headers={"User-Agent": USER_AGENT},
            timeout=30.0,
        )
        if response.status_code == 429:
            raise RuntimeError("Bluesky session rate limit exceeded. Try again later.")
        if response.status_code in (401, 403):
            raise RuntimeError("Bluesky authentication failed. Check BSKY_IDENTIFIER and BSKY_APP_PASSWORD.")
        response.raise_for_status()
        data = response.json()
        access_jwt = data.get("accessJwt")
        if not access_jwt:
            raise RuntimeError("Bluesky authentication response did not include accessJwt.")
        self._access_jwt = str(access_jwt)
        return self._access_jwt

    def search_posts(
        self,
        query: str,
        limit: int = 25,
        sort: str = "latest",
        since: str | None = None,
        until: str | None = None,
        lang: str | None = None,
        author: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search Bluesky posts and return normalized post records."""
        if not query.strip():
            raise ValueError("query is required")
        if sort not in {"latest", "top"}:
            raise ValueError("sort must be 'latest' or 'top'")

        params: dict[str, Any] = {
            "q": query,
            "limit": _clamp_limit(limit),
            "sort": sort,
            "since": since,
            "until": until,
            "lang": lang,
            "author": _strip_at(author),
            "tag": _strip_hash(tag),
        }
        data = self._request("app.bsky.feed.searchPosts", params)
        return [_normalize_post(post) for post in data.get("posts", [])]

    def get_author_feed(
        self,
        actor: str,
        limit: int = 25,
        include_replies: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch recent posts from an actor handle or DID."""
        if not actor.strip():
            raise ValueError("actor is required")

        data = self._request(
            "app.bsky.feed.getAuthorFeed",
            {
                "actor": _strip_at(actor),
                "limit": _clamp_limit(limit),
                "filter": "posts_and_author_threads" if include_replies else "posts_no_replies",
            },
        )
        posts: list[dict[str, Any]] = []
        for item in data.get("feed", []):
            post = item.get("post")
            if isinstance(post, dict):
                posts.append(_normalize_post(post))
        return posts


def _clamp_limit(limit: int) -> int:
    return min(max(int(limit), 1), 100)


def _strip_at(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().lstrip("@") or None


def _strip_hash(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().lstrip("#") or None


def _optional_credential(key: str) -> str | None:
    try:
        from core.tools._base import resolve_env_style_credential

        return resolve_env_style_credential(key)
    except Exception:
        return os.environ.get(key) or None


def _post_url(uri: str, handle: str) -> str:
    parts = uri.split("/")
    rkey = parts[-1] if parts else ""
    profile = handle or (parts[2] if uri.startswith("at://") and len(parts) > 2 else "")
    if not profile or not rkey:
        return ""
    return f"https://bsky.app/profile/{profile}/post/{rkey}"


def _normalize_post(post: dict[str, Any]) -> dict[str, Any]:
    author = post.get("author") if isinstance(post.get("author"), dict) else {}
    record = post.get("record") if isinstance(post.get("record"), dict) else {}
    handle = str(author.get("handle") or "")
    uri = str(post.get("uri") or "")
    return {
        "uri": uri,
        "cid": post.get("cid", ""),
        "url": _post_url(uri, handle),
        "text": record.get("text", ""),
        "created_at": record.get("createdAt", ""),
        "indexed_at": post.get("indexedAt", ""),
        "author_handle": handle,
        "author_display_name": author.get("displayName", ""),
        "author_did": author.get("did", ""),
        "like_count": post.get("likeCount", 0),
        "repost_count": post.get("repostCount", 0),
        "reply_count": post.get("replyCount", 0),
        "quote_count": post.get("quoteCount", 0),
    }


def format_posts(posts: list[dict[str, Any]], verbose: bool = False) -> str:
    """Format normalized Bluesky posts as text."""
    if not posts:
        return "No Bluesky posts found."

    lines: list[str] = []
    for i, post in enumerate(posts, 1):
        author = post.get("author_handle", "")
        created = str(post.get("created_at", ""))[:16]
        lines.append(f"[{i}] @{author} - {created}")
        text = str(post.get("text", "")).replace("\n", "\n  ")
        lines.append(f"  {text}")
        url = post.get("url")
        if url:
            lines.append(f"  {url}")
        if verbose:
            lines.append(
                "  "
                f"[Likes: {post.get('like_count', 0):,} | "
                f"Reposts: {post.get('repost_count', 0):,} | "
                f"Replies: {post.get('reply_count', 0):,} | "
                f"Quotes: {post.get('quote_count', 0):,}]"
            )
        lines.append("")
    return "\n".join(lines)


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return Anthropic tool_use schemas for Bluesky tools."""
    return [
        {
            "name": "bluesky_search",
            "description": (
                "Search public Bluesky posts via the Bluesky AppView API. "
                "Useful for market chatter, company/ticker mentions, and news discussion signals."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string."},
                    "limit": {"type": "integer", "description": "Maximum posts to return, 1-100. Default: 25."},
                    "sort": {"type": "string", "enum": ["latest", "top"], "description": "Sort mode. Default: latest."},
                    "since": {"type": "string", "description": "Optional ISO datetime lower bound."},
                    "until": {"type": "string", "description": "Optional ISO datetime upper bound."},
                    "lang": {"type": "string", "description": "Optional language code, e.g. ja or en."},
                    "author": {"type": "string", "description": "Optional author handle without or with @."},
                    "tag": {"type": "string", "description": "Optional hashtag without or with #."},
                },
                "required": ["query"],
            },
        },
        {
            "name": "bluesky_author_feed",
            "description": "Fetch recent public Bluesky posts from a handle or DID.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "actor": {"type": "string", "description": "Bluesky handle or DID."},
                    "limit": {"type": "integer", "description": "Maximum posts to return, 1-100. Default: 25."},
                    "include_replies": {
                        "type": "boolean",
                        "description": "Include replies and threads. Default: false.",
                    },
                },
                "required": ["actor"],
            },
        },
    ]


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call by schema name."""
    args.pop("anima_dir", None)
    client = BlueskyClient()
    if name == "bluesky_search":
        return client.search_posts(
            query=args["query"],
            limit=args.get("limit", 25),
            sort=args.get("sort", "latest"),
            since=args.get("since"),
            until=args.get("until"),
            lang=args.get("lang"),
            author=args.get("author"),
            tag=args.get("tag"),
        )
    if name == "bluesky_author_feed":
        return client.get_author_feed(
            actor=args["actor"],
            limit=args.get("limit", 25),
            include_replies=bool(args.get("include_replies", False)),
        )
    raise ValueError(f"Unknown tool: {name}")


def cli_main(argv: list[str] | None = None) -> None:
    """CLI entry point for Bluesky search."""
    parser = argparse.ArgumentParser(description="Search public Bluesky posts")
    sub = parser.add_subparsers(dest="command")

    search_parser = sub.add_parser("search", help="Search public posts")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("-n", "--limit", type=int, default=25, help="Number of posts (1-100)")
    search_parser.add_argument("--sort", choices=["latest", "top"], default="latest")
    search_parser.add_argument("--since", help="ISO datetime lower bound")
    search_parser.add_argument("--until", help="ISO datetime upper bound")
    search_parser.add_argument("--lang", help="Language code, e.g. ja or en")
    search_parser.add_argument("--author", help="Restrict to author handle")
    search_parser.add_argument("--tag", help="Restrict to hashtag")
    search_parser.add_argument("-j", "--json", action="store_true", help="Output JSON")
    search_parser.add_argument("-v", "--verbose", action="store_true", help="Show engagement metrics")

    feed_parser = sub.add_parser("author-feed", help="Fetch posts from an actor")
    feed_parser.add_argument("actor", help="Bluesky handle or DID")
    feed_parser.add_argument("-n", "--limit", type=int, default=25, help="Number of posts (1-100)")
    feed_parser.add_argument("--include-replies", action="store_true", help="Include replies and threads")
    feed_parser.add_argument("-j", "--json", action="store_true", help="Output JSON")
    feed_parser.add_argument("-v", "--verbose", action="store_true", help="Show engagement metrics")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.error("command is required: search or author-feed")

    client = BlueskyClient()
    if args.command == "search":
        posts = client.search_posts(
            query=args.query,
            limit=args.limit,
            sort=args.sort,
            since=args.since,
            until=args.until,
            lang=args.lang,
            author=args.author,
            tag=args.tag,
        )
    else:
        posts = client.get_author_feed(
            actor=args.actor,
            limit=args.limit,
            include_replies=args.include_replies,
        )

    if args.json:
        print(json.dumps(posts, ensure_ascii=False, indent=2))
    else:
        print(format_posts(posts, verbose=args.verbose))
