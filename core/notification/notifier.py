from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""HumanNotifier — fan-out notifications to multiple channels.

``HumanNotifier`` owns a list of ``NotificationChannel`` instances and
sends a notification to all of them in parallel via ``asyncio.gather``.
"""

import asyncio
import json
import logging
import os
import time
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from core.config.models import HumanNotificationConfig, NotificationChannelConfig
from core.notification.interactive import InteractionRequest

logger = logging.getLogger("animaworks.notification")

# ── Priority mapping ────────────────────────────────────────

PRIORITY_LEVELS = ("low", "normal", "high", "urgent")
_UNKNOWN_GOVERNOR_NOTICE_COOLDOWN_SECONDS = 15 * 60
_unknown_governor_notice_at: dict[str, float] = {}


def _known_anima_names() -> set[str]:
    """Return current registry names for notification safety checks."""
    try:
        from core.paths import get_animas_dir, get_data_dir

        animas_dir = get_animas_dir()
        disk_names = (
            {
                anima_dir.name
                for anima_dir in animas_dir.iterdir()
                if anima_dir.is_dir() and (anima_dir / "status.json").is_file()
            }
            if animas_dir.is_dir()
            else set()
        )

        config_path = get_data_dir() / "config.json"
        config_names: set[str] | None = None
        if config_path.is_file():
            data = json.loads(Path(config_path).read_text("utf-8-sig"))
            animas = data.get("animas")
            if isinstance(animas, dict):
                config_names = {str(name) for name in animas}
        return disk_names.intersection(config_names) if config_names else disk_names
    except Exception:
        logger.debug("Failed to read Anima registry for notification guard", exc_info=True)
        return set()


def _is_governor_notification(subject: str, body: str) -> bool:
    return subject.startswith("Governor") and body.startswith("Governor:")


def _notification_callsite() -> str:
    """Return a compact stack for tracing unexpected notification sources."""
    frames = traceback.extract_stack(limit=12)[:-2]
    return " <- ".join(f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames[-8:])


def _should_report_unknown_governor(anima_name: str) -> bool:
    now = time.time()
    last = _unknown_governor_notice_at.get(anima_name, 0.0)
    if now - last < _UNKNOWN_GOVERNOR_NOTICE_COOLDOWN_SECONDS:
        return False
    _unknown_governor_notice_at[anima_name] = now
    return True


# ── Abstract base ───────────────────────────────────────────


class NotificationChannel(ABC):
    """Abstract base for a human notification channel."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    @property
    @abstractmethod
    def channel_type(self) -> str:
        """Return the channel type identifier (e.g. 'slack')."""

    @abstractmethod
    async def send(
        self,
        subject: str,
        body: str,
        priority: str = "normal",
        *,
        anima_name: str = "",
        interaction: InteractionRequest | None = None,
    ) -> str:
        """Send a notification. Returns a status message."""

    def _resolve_env(self, key: str) -> str:
        """Resolve a config value that may reference an env var via ``*_env`` suffix."""
        env_key = self._config.get(key)
        if not env_key:
            return ""
        return os.environ.get(env_key, "")

    def _resolve_credential_with_vault(
        self,
        config_key: str,
        anima_name: str = "",
        fallback_env: str = "",
    ) -> str:
        """Resolve credential from env → per-anima vault/shared → generic vault/shared.

        Follows the same resolution cascade as
        ``core.notification.channels.slack``.
        """
        token = self._resolve_env(config_key)
        if token:
            return token

        env_key = self._config.get(config_key, fallback_env)
        if not env_key:
            return ""

        from core.tools._base import _lookup_shared_credentials, _lookup_vault_credential

        if anima_name:
            per_key = f"{env_key}__{anima_name}"
            val = _lookup_vault_credential(per_key) or _lookup_shared_credentials(per_key) or ""
            if val:
                return val

        return _lookup_vault_credential(env_key) or _lookup_shared_credentials(env_key) or ""


# ── Factory ─────────────────────────────────────────────────

_CHANNEL_REGISTRY: dict[str, type[NotificationChannel]] = {}


def register_channel(channel_type: str):
    """Decorator to register a channel implementation."""

    def decorator(cls: type[NotificationChannel]):
        _CHANNEL_REGISTRY[channel_type] = cls
        return cls

    return decorator


def create_channel(channel_config: NotificationChannelConfig) -> NotificationChannel:
    """Create a channel instance from config."""
    cls = _CHANNEL_REGISTRY.get(channel_config.type)
    if cls is None:
        raise ValueError(f"Unknown notification channel type: {channel_config.type}")
    return cls(channel_config.config)


# ── HumanNotifier ───────────────────────────────────────────


class HumanNotifier:
    """Fan-out notifier that sends to all configured channels in parallel."""

    def __init__(self, channels: list[NotificationChannel]) -> None:
        self._channels = channels

    @classmethod
    def from_config(cls, config: HumanNotificationConfig) -> HumanNotifier:
        """Build a notifier from the global HumanNotificationConfig."""
        # Import channel modules to trigger registration
        _ensure_channels_registered()

        channels: list[NotificationChannel] = []
        for ch_config in config.channels:
            if not ch_config.enabled:
                continue
            try:
                channels.append(create_channel(ch_config))
            except ValueError:
                logger.warning(
                    "Skipping unknown notification channel: %s",
                    ch_config.type,
                )
        return cls(channels)

    @property
    def channel_count(self) -> int:
        return len(self._channels)

    async def notify(
        self,
        subject: str,
        body: str,
        priority: str = "normal",
        *,
        anima_name: str = "",
        interaction: InteractionRequest | None = None,
    ) -> list[str]:
        """Send notification to all channels in parallel.

        Returns a list of status messages (one per channel).
        Failed channels return error strings instead of raising.
        """
        if not self._channels:
            return ["No notification channels configured"]

        if _is_governor_notification(subject, body):
            logger.warning(
                "Governor human notification requested: anima=%s subject=%s callsite=%s",
                anima_name,
                subject[:80],
                _notification_callsite(),
            )

        if anima_name and _is_governor_notification(subject, body):
            known_names = _known_anima_names()
            if known_names and anima_name not in known_names:
                callsite = _notification_callsite()
                logger.warning(
                    "Suppressed governor human notification for unknown Anima: %s callsite=%s",
                    anima_name,
                    callsite,
                )
                if not _should_report_unknown_governor(anima_name):
                    return [f"Suppressed governor notification for unknown Anima: {anima_name}"]
                subject = "AnimaWorks Governor通知を抑止"
                body = (
                    f"存在しないAnima名 `{anima_name}` のGovernor通知を抑止しました。\n\n"
                    f"元本文:\n{body[:800]}\n\n"
                    f"callsite: `{callsite}`"
                )
                priority = "high"
                anima_name = ""

        if priority not in PRIORITY_LEVELS:
            priority = "normal"

        results = await asyncio.gather(
            *[
                ch.send(subject, body, priority, anima_name=anima_name, interaction=interaction)
                for ch in self._channels
            ],
            return_exceptions=True,
        )

        status: list[str] = []
        for ch, result in zip(self._channels, results, strict=False):
            if isinstance(result, BaseException):
                msg = f"{ch.channel_type}: ERROR - {result}"
                logger.error("Notification failed for %s: %s", ch.channel_type, result)
                status.append(msg)
            else:
                status.append(str(result))

        failed_count = sum(1 for s in status if "ERROR" in s)
        if failed_count > 0:
            logger.warning(
                "Human notification partial failure: subject=%s priority=%s channels=%d failed=%d success=%d",
                subject[:50],
                priority,
                len(self._channels),
                failed_count,
                len(self._channels) - failed_count,
            )
        else:
            logger.info(
                "Human notification sent: subject=%s priority=%s channels=%d",
                subject[:50],
                priority,
                len(self._channels),
            )
        return status


_builtins_registered = False


def _ensure_channels_registered() -> None:
    """Import all built-in channel modules so they register themselves."""
    global _builtins_registered
    if _builtins_registered:
        return
    _builtins_registered = True
    # Import triggers @register_channel decorators
    import core.notification.channels.chatwork  # noqa: F401
    import core.notification.channels.discord  # noqa: F401
    import core.notification.channels.line  # noqa: F401
    import core.notification.channels.ntfy  # noqa: F401
    import core.notification.channels.slack  # noqa: F401
    import core.notification.channels.telegram  # noqa: F401
