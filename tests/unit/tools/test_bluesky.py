"""Tests for core/tools/bluesky.py — Bluesky search tool."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from core.tools.bluesky import (
    BlueskyClient,
    _normalize_post,
    cli_main,
    dispatch,
    format_posts,
    get_tool_schemas,
)


def _post() -> dict:
    return {
        "uri": "at://did:plc:abc/app.bsky.feed.post/3abc",
        "cid": "cid123",
        "indexedAt": "2026-06-04T01:00:00Z",
        "author": {
            "did": "did:plc:abc",
            "handle": "market.example.com",
            "displayName": "Market Desk",
        },
        "record": {
            "text": "Market update",
            "createdAt": "2026-06-04T00:59:00Z",
        },
        "likeCount": 10,
        "repostCount": 2,
        "replyCount": 1,
        "quoteCount": 3,
    }


def _response(json_data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=json_data,
        request=httpx.Request("GET", "https://public.api.bsky.app/xrpc/test"),
    )


class TestBlueskyClient:
    def test_search_posts_success(self):
        client = BlueskyClient()
        with patch("core.tools.bluesky.httpx.get", return_value=_response({"posts": [_post()]})) as mock_get:
            posts = client.search_posts("$NVDA", limit=200, author="@market.example.com", tag="#stocks")

        assert len(posts) == 1
        assert posts[0]["text"] == "Market update"
        assert posts[0]["author_handle"] == "market.example.com"
        assert posts[0]["url"] == "https://bsky.app/profile/market.example.com/post/3abc"
        params = mock_get.call_args.kwargs["params"]
        assert params["limit"] == 100
        assert params["author"] == "market.example.com"
        assert params["tag"] == "stocks"

    def test_search_posts_rejects_empty_query(self):
        client = BlueskyClient()
        with pytest.raises(ValueError, match="query is required"):
            client.search_posts("")

    def test_search_posts_rejects_unknown_sort(self):
        client = BlueskyClient()
        with pytest.raises(ValueError, match="sort"):
            client.search_posts("market", sort="newest")

    def test_get_author_feed_success(self):
        client = BlueskyClient()
        with patch("core.tools.bluesky.httpx.get", return_value=_response({"feed": [{"post": _post()}]})) as mock_get:
            posts = client.get_author_feed("@market.example.com", include_replies=True)

        assert len(posts) == 1
        params = mock_get.call_args.kwargs["params"]
        assert params["actor"] == "market.example.com"
        assert params["filter"] == "posts_and_author_threads"

    def test_rate_limit_error(self):
        client = BlueskyClient()
        with patch("core.tools.bluesky.httpx.get", return_value=_response({}, status_code=429)), \
             pytest.raises(RuntimeError, match="rate limit"):
            client.search_posts("market")

    def test_auth_required_error(self):
        client = BlueskyClient()
        with patch("core.tools.bluesky.httpx.get", return_value=_response({}, status_code=401)), \
             patch("core.tools.bluesky._optional_credential", return_value=None), \
             pytest.raises(RuntimeError, match="requires authentication"):
            client.search_posts("market")

    def test_auth_fallback_when_public_endpoint_denies(self):
        client = BlueskyClient()
        denied = _response({}, status_code=403)
        authed = _response({"posts": [_post()]})
        session = httpx.Response(
            200,
            json={"accessJwt": "jwt-token"},
            request=httpx.Request("POST", "https://bsky.social/xrpc/com.atproto.server.createSession"),
        )

        with patch("core.tools.bluesky._optional_credential", side_effect=["@alice.bsky.social", "app-pass"]), \
             patch("core.tools.bluesky.httpx.post", return_value=session) as mock_post, \
             patch("core.tools.bluesky.httpx.get", side_effect=[denied, authed]) as mock_get:
            posts = client.search_posts("market")

        assert len(posts) == 1
        mock_post.assert_called_once()
        assert mock_post.call_args.kwargs["json"]["identifier"] == "alice.bsky.social"
        auth_headers = mock_get.call_args_list[1].kwargs["headers"]
        assert auth_headers["Authorization"] == "Bearer jwt-token"


class TestNormalizePost:
    def test_normalize_post(self):
        post = _normalize_post(_post())
        assert post["uri"] == "at://did:plc:abc/app.bsky.feed.post/3abc"
        assert post["created_at"] == "2026-06-04T00:59:00Z"
        assert post["like_count"] == 10
        assert post["quote_count"] == 3

    def test_normalize_post_handles_missing_author(self):
        post = _normalize_post({"uri": "at://did:plc:abc/app.bsky.feed.post/3abc"})
        assert post["author_handle"] == ""
        assert post["url"] == "https://bsky.app/profile/did:plc:abc/post/3abc"


class TestFormattingAndDispatch:
    def test_format_posts(self):
        output = format_posts([_normalize_post(_post())], verbose=True)
        assert "@market.example.com" in output
        assert "Market update" in output
        assert "Likes:" in output

    def test_get_tool_schemas(self):
        names = {schema["name"] for schema in get_tool_schemas()}
        assert names == {"bluesky_search", "bluesky_author_feed"}

    def test_dispatch_search(self):
        with patch.object(BlueskyClient, "search_posts", return_value=[{"text": "ok"}]) as mock_search:
            result = dispatch("bluesky_search", {"query": "market", "limit": 3, "anima_dir": "/x"})
        assert result == [{"text": "ok"}]
        mock_search.assert_called_once()

    def test_dispatch_author_feed(self):
        with patch.object(BlueskyClient, "get_author_feed", return_value=[{"text": "ok"}]) as mock_feed:
            result = dispatch("bluesky_author_feed", {"actor": "market.example.com"})
        assert result == [{"text": "ok"}]
        mock_feed.assert_called_once()

    def test_cli_accepts_json_after_search_subcommand(self, capsys):
        with patch.object(BlueskyClient, "search_posts", return_value=[{"text": "ok"}]):
            cli_main(["search", "market", "-j"])
        out = capsys.readouterr().out
        assert '"text": "ok"' in out
