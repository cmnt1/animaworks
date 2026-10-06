# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for log / audit PII masking (URL, context, audit detail)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from core.enclave.egress.masker.log_pii import mask_audit_detail, mask_context, mask_url

# --- mask_url ---


def test_url_masks_numeric_path_ids() -> None:
    assert mask_url("/accounts/123") == "/accounts/[ID]"


def test_url_masks_numeric_id_in_middle_segment() -> None:
    assert mask_url("/api/v1/accounts/456/records") == "/api/v1/accounts/[ID]/records"


def test_url_masks_multiple_numeric_ids() -> None:
    assert mask_url("/accounts/123/records/456") == "/accounts/[ID]/records/[ID]"


def test_url_masks_trailing_numeric_id() -> None:
    assert mask_url("/api/accounts/99999/") == "/api/accounts/[ID]/"


def test_url_masks_query_values() -> None:
    result = mask_url("https://example.com/path?token=abc&q=test")
    parts = urlsplit(result)
    params = parse_qs(parts.query)
    assert params["token"] == ["[MASKED]"]
    assert params["q"] == ["[MASKED]"]


def test_url_without_numeric_path_is_unchanged() -> None:
    assert mask_url("/api/v1/accounts/list") == "/api/v1/accounts/list"


def test_url_rebuilds_scheme_host_path_query_fragment() -> None:
    result = mask_url("https://example.com/path/42?key=val#section")
    assert result.startswith("https://example.com")
    assert "/path/[ID]" in result
    assert "#section" in result
    assert parse_qs(urlsplit(result).query)["key"] == ["[MASKED]"]


def test_url_masks_port_and_id() -> None:
    result = mask_url("https://example.com:8080/accounts/1")
    assert "example.com:8080" in result
    assert "/accounts/[ID]" in result


def test_url_query_only_relative() -> None:
    result = mask_url("?token=secret&user_id=99")
    params = parse_qs(urlsplit(result).query)
    assert params["token"] == ["[MASKED]"]
    assert params["user_id"] == ["[MASKED]"]


def test_url_query_only_without_path() -> None:
    assert parse_qs(urlsplit(mask_url("https://example.com?foo=bar")).query)["foo"] == ["[MASKED]"]


# --- mask_context ---


def test_context_masks_sensitive_keys_only() -> None:
    result = mask_context({"customer_id": "123", "name": "Taro", "unrelated": "value"})
    assert result["customer_id"] == "[MASKED]"
    assert result["name"] == "[MASKED]"
    assert result["unrelated"] == "value"


def test_context_masks_uppercase_sensitive_keys() -> None:
    result = mask_context({"Customer_ID": "123", "EMAIL": "a@b.com"})
    assert result["Customer_ID"] == "[MASKED]"
    assert result["EMAIL"] == "[MASKED]"


def test_context_keeps_key_order() -> None:
    result = mask_context({"z": 1, "customer_id": 2, "a": 3})
    assert list(result) == ["z", "customer_id", "a"]


def test_context_handles_empty_and_non_sensitive() -> None:
    assert mask_context({}) == {}
    assert mask_context({"title": "Mr.", "count": 42}) == {"title": "Mr.", "count": 42}


# --- mask_audit_detail ---


def test_audit_detail_masks_urls_and_free_text_recursively() -> None:
    result = mask_audit_detail(
        {
            "url": "/accounts/123?token=dummy&name=sample",
            "endpoint": "/orders/456?auth=dummy",
            "message": "failed for sample customer 000-0000",
            "memo": "free text content",
            "unknown": "more text",
            "status_code": 500,
            "nested": {"customer_name": "Sample", "safe": "kept", "retryable": True},
        }
    )
    assert "/accounts/[ID]" in result["url"]
    assert parse_qs(urlsplit(result["url"]).query)["token"] == ["[MASKED]"]
    assert "/orders/[ID]" in result["endpoint"]
    assert result["message"] == "[MASKED]"
    assert result["memo"] == "[MASKED]"
    assert result["unknown"] == "[MASKED]"
    assert result["status_code"] == 500
    assert result["nested"]["customer_name"] == "[MASKED]"
    assert result["nested"]["safe"] == "[MASKED]"
    assert result["nested"]["retryable"] is True


def test_audit_detail_free_text_with_url_is_still_masked() -> None:
    result = mask_audit_detail({"error": "GET /accounts/123?token=dummy failed"})
    assert result["error"] == "[MASKED]"
