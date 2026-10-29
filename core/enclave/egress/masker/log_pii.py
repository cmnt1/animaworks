# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Masking of log/audit PII.

Port of the URL / context / audit-detail masking helpers. Numeric path IDs in
URLs become ``[ID]``, query values become ``[MASKED]``, and known sensitive
keys (plus arbitrary free-text values in audit details) are replaced with
``[MASKED]``.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "customer",
    "customer_id",
    "customer_name",
    "customer_kana",
    "account_no",
    "user_id",
    "name",
    "email",
    "phone",
    "token",
    "password",
    "birth_date",
    "dob",
    "address",
    "ssn",
    "my_number",
}

URL_VALUE_KEYS = {
    "url",
    "endpoint",
    "path",
    "uri",
    "href",
    "request_url",
    "request_uri",
}

_URL_LIKE_RE = re.compile(r"^(?:https?://|/|\?)")
_PATH_ID_RE = re.compile(r"/\d+(?=/|$)")

# Rough URL scanner used to locate URL-like tokens inside a free-text fact.
_INLINE_URL_RE = re.compile(
    r"https?://[^\s、。，！？!？（）()「」『』【】<>\"']+|"
    r"(?:^|(?<=[\s、。，）】」』]))/[^\s、。，！？!？（）()「」『』【】<>\"']*"
)


def mask_url(url: str) -> str:
    """Mask numeric path IDs and query parameter values in *url*."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    path = _PATH_ID_RE.sub("/[ID]", parts.path)

    query = parts.query
    if query:
        params = [(key, "[MASKED]") for key, _ in parse_qsl(query, keep_blank_values=True)]
        query = urlencode(params)

    return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def mask_inline_urls(text: str) -> str:
    """Mask URL-like substrings found inside a free-text fact."""
    return _INLINE_URL_RE.sub(lambda m: mask_url(m.group(0)), text)


def mask_context(context: dict[str, Any]) -> dict[str, Any]:
    """Recursively replace values of known sensitive keys with ``[MASKED]``."""
    return _mask_context_value(context)


def _mask_context_value(value: Any, key: str | int | None = None) -> Any:
    if key is not None and str(key).lower() in SENSITIVE_KEYS:
        return "[MASKED]"
    if isinstance(value, dict):
        return {k: _mask_context_value(v, k) for k, v in value.items()}
    return value


def mask_audit_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask an audit-detail dict.

    Sensitive keys become ``[MASKED]``; string values are not kept except
    URL-like values under URL keys, which are URL-masked.
    """
    return _mask_audit_value(detail)


def _mask_audit_value(value: Any, key: str | int | None = None) -> Any:
    key_name = str(key).lower() if key is not None else ""
    if key is not None and key_name in SENSITIVE_KEYS:
        return "[MASKED]"
    if isinstance(value, dict):
        return {k: _mask_audit_value(v, k) for k, v in value.items()}
    if isinstance(value, str):
        if key_name in URL_VALUE_KEYS and _URL_LIKE_RE.match(value.strip()):
            return mask_url(value)
        return "[MASKED]"
    return value
