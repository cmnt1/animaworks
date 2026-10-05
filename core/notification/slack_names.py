from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Process-wide Slack user-name cache and mention resolution.

Shared by the Socket Mode gateway (server) and reply routing (core), so the
cache lives here in core and the server imports it.
"""

import logging
import re
import threading

logger = logging.getLogger(__name__)

_USER_NAME_CACHE_MAX = 500
_cache_lock = threading.Lock()
user_name_cache: dict[str, str] = {}


def cache_user_name(uid: str, name: str) -> None:
    """Thread-safe bounded insert into the user-name cache."""
    with _cache_lock:
        if len(user_name_cache) >= _USER_NAME_CACHE_MAX and uid not in user_name_cache:
            try:
                user_name_cache.pop(next(iter(user_name_cache)))
            except StopIteration:
                pass
        user_name_cache[uid] = name


def get_cached_user_name(uid: str) -> str | None:
    """Thread-safe lookup from the user-name cache."""
    with _cache_lock:
        return user_name_cache.get(uid)


def user_name_snapshot() -> dict[str, str]:
    """Return a copy of the cache that is safe to read without the lock."""
    with _cache_lock:
        return dict(user_name_cache)


def resolve_slack_mentions(text: str, token: str) -> str:
    """Resolve <@U...> mentions and Slack markup to human-readable text.

    Extracts all user IDs, resolves unknown ones via Slack API (cached),
    then applies clean_slack_markup() for full conversion.
    """
    if not text:
        return text
    user_ids = set(re.findall(r"<@(U[A-Z0-9]+)>", text))
    unknown = {uid for uid in user_ids if get_cached_user_name(uid) is None}
    if unknown and token:
        try:
            from core.integrations.slack import SlackClient

            client = SlackClient(token=token)
            for uid in unknown:
                cache_user_name(uid, client.resolve_user_name(uid))
        except Exception:
            logger.debug("Failed to resolve Slack user mentions", exc_info=True)
    from core.integrations._slack_markdown import clean_slack_markup

    return clean_slack_markup(text, cache=user_name_snapshot())
