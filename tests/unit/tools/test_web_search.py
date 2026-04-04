"""Tests for core/tools/web_search.py — dual-backend Web Search tool."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from core.tools.web_search import (
    _DDG_HTML_URL,
    _extract_ddg_url,
    _resolve_backend,
    _strip_html,
    dispatch,
    format_results,
    get_tool_schemas,
    search,
)

# ── Helper fixtures ───────────────────────────────────────────────

_SAMPLE_DDG_HTML = """\
<html><body>
<div class="result results_links results_links_deep web-result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F1&rut=abc">Result 1</a>
  <a class="result__snippet">Desc 1</a>
</div>
<div class="result results_links results_links_deep web-result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2F2&rut=def">Result 2</a>
  <a class="result__snippet">Desc <b>2</b></a>
</div>
</body></html>
"""

_SAMPLE_BRAVE_JSON = {
    "web": {
        "results": [
            {"title": "Brave Result 1", "url": "https://brave.example.com/1", "description": "Brave desc 1"},
            {"title": "Brave Result 2", "url": "https://brave.example.com/2", "description": "Brave desc 2"},
        ]
    }
}


def _make_ddg_response(html_body: str = _SAMPLE_DDG_HTML, status: int = 200) -> httpx.Response:
    """Build a mock httpx.Response with DDG search HTML."""
    return httpx.Response(status, text=html_body, request=httpx.Request("POST", _DDG_HTML_URL))


def _make_brave_response(data: dict | None = None, status: int = 200) -> httpx.Response:
    """Build a mock httpx.Response with Brave JSON."""
    import json

    body = json.dumps(data or _SAMPLE_BRAVE_JSON)
    return httpx.Response(
        status,
        text=body,
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://api.search.brave.com/res/v1/web/search"),
    )


# ── _resolve_backend ─────────────────────────────────────────────


class TestResolveBackend:
    def test_brave_when_key_available(self):
        with patch("core.tools._base.get_credential", return_value="fake-key"):
            assert _resolve_backend() == "brave"

    def test_duckduckgo_when_no_key(self):
        with patch("core.tools._base.get_credential", side_effect=Exception("no key")):
            assert _resolve_backend() == "duckduckgo"


# ── search() with backend routing ────────────────────────────────


class TestSearch:
    def test_uses_brave_when_available(self):
        with (
            patch("core.tools.web_search._resolve_backend", return_value="brave"),
            patch("core.tools.web_search._search_brave") as mock_brave,
        ):
            mock_brave.return_value = [{"title": "B", "url": "U", "description": "D"}]
            results = search("test query")
            mock_brave.assert_called_once()
            assert results[0]["title"] == "B"

    def test_falls_back_to_ddg(self):
        with (
            patch("core.tools.web_search._resolve_backend", return_value="duckduckgo"),
            patch("core.tools.web_search._search_duckduckgo") as mock_ddg,
        ):
            mock_ddg.return_value = [{"title": "D", "url": "U", "description": "D"}]
            search("test query")
            mock_ddg.assert_called_once()

    def test_count_clamped_min(self):
        with (
            patch("core.tools.web_search._resolve_backend", return_value="duckduckgo"),
            patch("core.tools.web_search.httpx.post", return_value=_make_ddg_response()),
        ):
            results = search("test", count=-5)
            assert isinstance(results, list)

    def test_count_clamped_max(self):
        with (
            patch("core.tools.web_search._resolve_backend", return_value="duckduckgo"),
            patch("core.tools.web_search.httpx.post", return_value=_make_ddg_response()),
        ):
            results = search("test", count=100)
            assert isinstance(results, list)


# ── DuckDuckGo-specific tests ────────────────────────────────────


class TestDuckDuckGo:
    def test_successful_search(self):
        mock_resp = _make_ddg_response()
        with (
            patch("core.tools.web_search._resolve_backend", return_value="duckduckgo"),
            patch("core.tools.web_search.httpx.post", return_value=mock_resp),
        ):
            results = search("python programming")
        assert len(results) == 2
        assert results[0]["title"] == "Result 1"
        assert results[0]["url"] == "https://example.com/1"

    def test_http_error_propagated(self):
        error_resp = _make_ddg_response(status=500)
        with (
            patch("core.tools.web_search._resolve_backend", return_value="duckduckgo"),
            patch("core.tools.web_search.httpx.post", return_value=error_resp),
            pytest.raises(httpx.HTTPStatusError),
        ):
            search("test")

    def test_empty_results(self):
        mock_resp = _make_ddg_response("<html><body></body></html>")
        with (
            patch("core.tools.web_search._resolve_backend", return_value="duckduckgo"),
            patch("core.tools.web_search.httpx.post", return_value=mock_resp),
        ):
            results = search("obscure query")
        assert results == []

    def test_ads_skipped(self):
        html_with_ad = """\
<html><body>
<div class="result result--ad">
  <a class="result__a" href="https://ad.example.com">Ad</a>
  <a class="result__snippet">Ad desc</a>
</div>
<div class="result results_links web-result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Freal.example.com">Real</a>
  <a class="result__snippet">Real desc</a>
</div>
</body></html>
"""
        mock_resp = _make_ddg_response(html_with_ad)
        with (
            patch("core.tools.web_search._resolve_backend", return_value="duckduckgo"),
            patch("core.tools.web_search.httpx.post", return_value=mock_resp),
        ):
            results = search("test")
        assert len(results) == 1
        assert results[0]["title"] == "Real"


# ── Brave-specific tests ─────────────────────────────────────────


class TestBrave:
    def test_successful_search(self):
        mock_resp = _make_brave_response()
        with (
            patch("core.tools.web_search._resolve_backend", return_value="brave"),
            patch("core.tools._base.get_credential", return_value="fake-key"),
            patch("core.tools.web_search.httpx.get", return_value=mock_resp),
        ):
            results = search("test")
        assert len(results) == 2
        assert results[0]["title"] == "Brave Result 1"
        assert results[0]["url"] == "https://brave.example.com/1"

    def test_http_error_propagated(self):
        error_resp = _make_brave_response(status=500)
        with (
            patch("core.tools.web_search._resolve_backend", return_value="brave"),
            patch("core.tools._base.get_credential", return_value="fake-key"),
            patch("core.tools.web_search.httpx.get", return_value=error_resp),
            pytest.raises(httpx.HTTPStatusError),
        ):
            search("test")


# ── _extract_ddg_url ──────────────────────────────────────────────


class TestExtractDdgUrl:
    def test_extracts_uddg_param(self):
        assert _extract_ddg_url("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com&rut=abc") == "https://example.com"

    def test_direct_http_url(self):
        assert _extract_ddg_url("https://example.com") == "https://example.com"

    def test_empty_string(self):
        assert _extract_ddg_url("") == ""

    def test_ad_redirect_skipped(self):
        assert _extract_ddg_url("//duckduckgo.com/l/?uddg=https%3A%2F%2Fduckduckgo.com%2Fy.js%3Ffoo") == ""


# ── _strip_html ───────────────────────────────────────────────────


class TestStripHtml:
    def test_strips_tags(self):
        assert _strip_html("<b>bold</b> text") == "bold text"

    def test_unescapes_entities(self):
        assert _strip_html("a &amp; b &lt; c") == "a & b < c"

    def test_empty_string(self):
        assert _strip_html("") == ""

    def test_nested_tags(self):
        assert _strip_html("<div><p>hello</p></div>") == "hello"


# ── format_results ────────────────────────────────────────────────


class TestFormatResults:
    def test_no_results(self):
        assert format_results([]) == "No results found."

    def test_formats_results(self):
        results = [
            {"title": "Test Title", "url": "https://test.com", "description": "A test desc"},
        ]
        output = format_results(results)
        assert "1. Test Title" in output
        assert "https://test.com" in output
        assert "A test desc" in output

    def test_html_stripped_from_description(self):
        results = [
            {"title": "T", "url": "U", "description": "<em>highlighted</em> text"},
        ]
        output = format_results(results)
        assert "<em>" not in output
        assert "highlighted text" in output


# ── dispatch ──────────────────────────────────────────────────────


class TestDispatch:
    """Dispatch function parameter mapping tests."""

    @patch("core.tools.web_search.search")
    def test_limit_mapped_to_count(self, mock_search):
        mock_search.return_value = [{"title": "T", "url": "U", "description": "D"}]
        dispatch("web_search", {"query": "test", "limit": 3})
        mock_search.assert_called_once_with(query="test", count=3)

    @patch("core.tools.web_search.search")
    def test_count_passed_directly(self, mock_search):
        mock_search.return_value = []
        dispatch("web_search", {"query": "test", "count": 7})
        mock_search.assert_called_once_with(query="test", count=7)

    @patch("core.tools.web_search.search")
    def test_anima_dir_stripped(self, mock_search):
        mock_search.return_value = []
        dispatch("web_search", {"query": "test", "anima_dir": "/tmp/a"})
        mock_search.assert_called_once_with(query="test")

    def test_unknown_tool_raises(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            dispatch("nonexistent", {})


# ── get_tool_schemas ──────────────────────────────────────────────


class TestGetToolSchemas:
    def test_returns_empty_list(self):
        schemas = get_tool_schemas()
        assert isinstance(schemas, list)
        assert schemas == []
