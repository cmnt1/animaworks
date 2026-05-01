from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Discord webhook manager for per-Anima outbound messages.

Each channel gets a single webhook; per-message ``username`` and ``avatar_url``
parameters make each Anima appear as a distinct identity.
"""

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.paths import get_data_dir
from core.tools._anima_icon_url import resolve_anima_icon_url
from core.tools._base import get_credential
from core.tools._discord_client import DiscordAPIError, DiscordClient
from core.tools._discord_markdown import DISCORD_MESSAGE_LIMIT

logger = logging.getLogger("animaworks.discord_webhooks")
_WEBHOOK_NAME = "AnimaWorks"
_DISCORD_THREAD_TYPES = {10, 11, 12}

# Thread-to-Anima mapping TTL
_THREAD_MAP_TTL_DAYS = 7
_OUTBOUND_CONFIRM_TTL_SECONDS = 15 * 60
_OUTBOUND_VERIFY_HISTORY_LIMIT = 10


# ── Singleton ────────────────────────────────────────────────

_instance: DiscordWebhookManager | None = None
_instance_lock = threading.Lock()


def get_webhook_manager() -> DiscordWebhookManager:
    """Return the singleton DiscordWebhookManager instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DiscordWebhookManager()
    return _instance


# ── Manager ──────────────────────────────────────────────────


class DiscordWebhookManager:
    """Manages per-channel webhooks and thread-to-Anima mappings."""


    def __init__(self) -> None:
        self._webhooks: dict[str, dict[str, str]] = {}  # channel_id → {id, token}
        self._thread_map: dict[str, dict[str, Any]] = {}  # message_id → {anima, ts}
        self._lock = threading.Lock()
        self._client: DiscordClient | None = None
        self._load_persisted()

    def _ensure_client(self) -> DiscordClient:
        if self._client is None:
            token = get_credential("discord", "discord", env_var="DISCORD_BOT_TOKEN")
            self._client = DiscordClient(token=token)
        return self._client

    # ── Webhook CRUD ─────────────────────────────────────────

    def _get_or_create_webhook(self, channel_id: str) -> tuple[str, str]:
        """Return (webhook_id, webhook_token) for a channel, creating if needed."""
        with self._lock:
            cached = self._webhooks.get(channel_id)
            if cached:
                return cached["id"], cached["token"]

        client = self._ensure_client()

        # Check existing webhooks first
        try:
            existing = client.list_webhooks(channel_id)
            for wh in existing:
                if wh.get("name") == _WEBHOOK_NAME and wh.get("token"):
                    wh_id = str(wh["id"])
                    wh_token = wh["token"]
                    with self._lock:
                        self._webhooks[channel_id] = {"id": wh_id, "token": wh_token}
                    self._persist()
                    return wh_id, wh_token
        except DiscordAPIError:
            logger.debug("Failed to list webhooks for channel %s", channel_id, exc_info=True)

        # Create new
        try:
            result = client.create_webhook(channel_id, _WEBHOOK_NAME)
            wh_id = str(result["id"])
            wh_token = result["token"]
            with self._lock:
                self._webhooks[channel_id] = {"id": wh_id, "token": wh_token}
            self._persist()
            logger.info("Created webhook for channel %s: %s", channel_id, wh_id)
            return wh_id, wh_token
        except DiscordAPIError as exc:
            log = logger.debug if exc.status == 404 else logger.exception
            log("Failed to create webhook for channel %s", channel_id, exc_info=True)
            raise

    def _resolve_parent_for_thread_channel(self, client: DiscordClient, channel_id: str) -> str | None:
        """Return parent channel ID when *channel_id* is actually a thread."""
        try:
            channel = client.get_channel(channel_id)
        except DiscordAPIError:
            logger.debug("Failed to inspect Discord channel %s", channel_id, exc_info=True)
            return None

        parent_id = channel.get("parent_id")
        try:
            channel_type = int(channel.get("type", -1))
        except (TypeError, ValueError):
            channel_type = -1
        if parent_id and channel_type in _DISCORD_THREAD_TYPES:
            return str(parent_id)
        return None

    def send_as_anima(
        self,
        channel_id: str,
        anima_name: str,
        content: str,
        *,
        thread_id: str | None = None,
        components: list[dict[str, Any]] | None = None,
    ) -> str:
        """Send a message to a Discord channel appearing as a specific Anima.

        Args:
            channel_id: The channel to post in (must be a real channel, not a thread).
            anima_name: Display name for the webhook message.
            content: Message text.
            thread_id: If set, post inside this thread (the thread's snowflake ID).

        Returns the sent message ID (snowflake string). If a recent identical
        delivery is already confirmed, returns that existing message ID.
        """
        content_hash = _content_hash(content)
        client = self._ensure_client()

        try:
            wh_id, wh_token = self._get_or_create_webhook(channel_id)
        except DiscordAPIError as exc:
            parent_id = None
            if exc.status == 404 and not thread_id:
                parent_id = self._resolve_parent_for_thread_channel(client, channel_id)
            if not parent_id:
                raise
            logger.warning(
                "Discord webhook target %s is a thread; retrying via parent channel %s",
                channel_id,
                parent_id,
            )
            thread_id = channel_id
            channel_id = parent_id
            wh_id, wh_token = self._get_or_create_webhook(channel_id)

        existing_msg_id = self._lookup_recent_confirmed_outbound(
            channel_id,
            anima_name,
            content_hash,
            thread_id=thread_id,
        )
        if existing_msg_id:
            logger.info(
                "Skipping confirmed duplicate Discord webhook send: anima=%s channel=%s thread=%s id=%s",
                anima_name,
                channel_id,
                thread_id or "",
                existing_msg_id,
            )
            return existing_msg_id

        avatar_url = resolve_anima_icon_url(anima_name)

        # Split long messages
        chunks = _split_message(content)
        last_msg_id = ""
        last_i = len(chunks) - 1
        recorded_after_error: set[str] = set()

        for i, chunk in enumerate(chunks):
            comp = components if (i == last_i and components) else None
            try:
                result = client.execute_webhook(
                    wh_id,
                    wh_token,
                    chunk,
                    username=anima_name,
                    avatar_url=avatar_url or None,
                    thread_id=thread_id,
                    components=comp,
                )
                last_msg_id = str(result.get("id", ""))
            except DiscordAPIError as exc:
                if exc.status == 404:
                    # Webhook deleted — recreate and retry
                    with self._lock:
                        self._webhooks.pop(channel_id, None)
                    wh_id, wh_token = self._get_or_create_webhook(channel_id)
                    result = client.execute_webhook(
                        wh_id,
                        wh_token,
                        chunk,
                        username=anima_name,
                        avatar_url=avatar_url or None,
                        thread_id=thread_id,
                        components=comp,
                    )
                    last_msg_id = str(result.get("id", ""))
                else:
                    confirmed_msg_id = self._confirm_recent_webhook_delivery(
                        client,
                        channel_id,
                        anima_name,
                        chunk,
                        thread_id=thread_id,
                    )
                    if confirmed_msg_id:
                        self.record_thread_mapping(
                            confirmed_msg_id,
                            anima_name,
                            channel_id=channel_id,
                            thread_id=thread_id,
                            content_hash=content_hash,
                            delivery_status="confirmed_after_error",
                        )
                        logger.warning(
                            "Discord webhook send reported an error, but recent history confirms delivery: "
                            "anima=%s channel=%s thread=%s id=%s error=%s",
                            anima_name,
                            channel_id,
                            thread_id or "",
                            confirmed_msg_id,
                            exc,
                        )
                        last_msg_id = confirmed_msg_id
                        recorded_after_error.add(confirmed_msg_id)
                        continue
                    raise

        # Record thread mapping for reply routing
        if last_msg_id and last_msg_id not in recorded_after_error:
            self.record_thread_mapping(
                last_msg_id,
                anima_name,
                channel_id=channel_id,
                thread_id=thread_id,
                content_hash=content_hash,
                delivery_status="confirmed",
            )

        return last_msg_id

    # ── Thread-to-Anima mapping ──────────────────────────────

    def record_thread_mapping(
        self,
        message_id: str,
        anima_name: str,
        *,
        channel_id: str | None = None,
        thread_id: str | None = None,
        content_hash: str | None = None,
        delivery_status: str | None = None,
    ) -> None:
        """Record that a message was sent by an Anima for reply routing."""
        entry: dict[str, Any] = {
            "anima": anima_name,
            "ts": time.time(),
        }
        if channel_id:
            entry["channel_id"] = channel_id
        if thread_id:
            entry["thread_id"] = thread_id
        if content_hash:
            entry["content_hash"] = content_hash
        if delivery_status:
            entry["delivery_status"] = delivery_status
        with self._lock:
            self._thread_map[message_id] = entry
        self._persist_thread_map()

    def lookup_thread_anima(self, message_id: str) -> str | None:
        """Look up which Anima sent a message (for reply routing)."""
        with self._lock:
            entry = self._thread_map.get(message_id)
            if not entry:
                return None
            # Check TTL
            age_days = (time.time() - entry["ts"]) / 86400
            if age_days > _THREAD_MAP_TTL_DAYS:
                del self._thread_map[message_id]
                return None
            return entry["anima"]

    # ── Persistence ──────────────────────────────────────────

    def _lookup_recent_confirmed_outbound(
        self,
        channel_id: str,
        anima_name: str,
        content_hash: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        """Return a recent confirmed duplicate message ID, if one is known."""
        now = time.time()
        expected_thread = thread_id or ""
        best_msg_id = ""
        best_ts = 0.0
        with self._lock:
            for msg_id, entry in self._thread_map.items():
                if not isinstance(entry, dict):
                    continue
                if entry.get("anima") != anima_name:
                    continue
                if entry.get("channel_id") != channel_id:
                    continue
                if (entry.get("thread_id") or "") != expected_thread:
                    continue
                if entry.get("content_hash") != content_hash:
                    continue
                if entry.get("delivery_status") not in {"confirmed", "confirmed_after_error"}:
                    continue
                ts = float(entry.get("ts") or 0)
                if now - ts > _OUTBOUND_CONFIRM_TTL_SECONDS:
                    continue
                if ts > best_ts:
                    best_msg_id = str(msg_id)
                    best_ts = ts
        return best_msg_id or None

    def _confirm_recent_webhook_delivery(
        self,
        client: DiscordClient,
        channel_id: str,
        anima_name: str,
        content: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        """Check recent Discord history after an ambiguous send failure."""
        history_channel = thread_id or channel_id
        expected_hash = _content_hash(content)
        now = time.time()
        try:
            messages = client.channel_history(history_channel, limit=_OUTBOUND_VERIFY_HISTORY_LIMIT)
        except Exception:
            logger.debug("Failed to verify recent Discord webhook delivery", exc_info=True)
            return None

        for message in messages:
            if _content_hash(str(message.get("content") or "")) != expected_hash:
                continue
            if not _message_matches_anima(message, anima_name):
                continue
            msg_ts = _discord_timestamp_to_epoch(message.get("timestamp"))
            if msg_ts is not None and abs(now - msg_ts) > _OUTBOUND_CONFIRM_TTL_SECONDS:
                continue
            msg_id = message.get("id")
            if msg_id:
                return str(msg_id)
        return None

    def _webhooks_path(self) -> Path:
        return get_data_dir() / "run" / "discord_webhooks.json"

    def _thread_map_path(self) -> Path:
        return get_data_dir() / "run" / "discord_thread_map.json"

    def _load_persisted(self) -> None:
        """Load cached webhook and thread map data from disk."""
        try:
            p = self._webhooks_path()
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._webhooks = data
        except Exception:
            logger.debug("Failed to load webhook cache", exc_info=True)

        try:
            p = self._thread_map_path()
            if p.is_file():
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    # Prune expired entries
                    now = time.time()
                    cutoff = now - (_THREAD_MAP_TTL_DAYS * 86400)
                    self._thread_map = {
                        k: v for k, v in data.items() if isinstance(v, dict) and v.get("ts", 0) > cutoff
                    }
        except Exception:
            logger.debug("Failed to load thread map", exc_info=True)

    def _persist(self) -> None:
        """Save webhook cache to disk (mode 0o600 — contains tokens)."""
        try:
            p = self._webhooks_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                snapshot = dict(self._webhooks)
            _atomic_write_json(p, snapshot)
        except Exception:
            logger.debug("Failed to persist webhook cache", exc_info=True)

    def _persist_thread_map(self) -> None:
        """Save thread map to disk (mode 0o600 — contains routing data)."""
        try:
            p = self._thread_map_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                snapshot = dict(self._thread_map)
            _atomic_write_json(p, snapshot)
        except Exception:
            logger.debug("Failed to persist thread map", exc_info=True)


# ── Helpers ──────────────────────────────────────────────────


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON to *path* atomically via temp file + rename (mode 0o600)."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _content_hash(content: str) -> str:
    normalized = " ".join(str(content).split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _message_matches_anima(message: dict[str, Any], anima_name: str) -> bool:
    author = message.get("author")
    if not isinstance(author, dict):
        return False
    username = str(author.get("username") or "")
    global_name = str(author.get("global_name") or "")
    return username == anima_name or global_name == anima_name


def _discord_timestamp_to_epoch(value: Any) -> float | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return None


def _split_message(content: str) -> list[str]:
    """Split content into chunks that fit Discord's message limit."""
    if len(content) <= DISCORD_MESSAGE_LIMIT:
        return [content]
    chunks: list[str] = []
    while content:
        if len(content) <= DISCORD_MESSAGE_LIMIT:
            chunks.append(content)
            break
        # Try to split at a newline
        cut = content.rfind("\n", 0, DISCORD_MESSAGE_LIMIT)
        if cut <= 0:
            cut = DISCORD_MESSAGE_LIMIT
        chunks.append(content[:cut])
        content = content[cut:].lstrip("\n")
    return chunks
