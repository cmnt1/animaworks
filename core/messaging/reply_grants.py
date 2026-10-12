from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Short-lived grants for replying to external message threads."""

import json
import logging
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.platform.atomic_io import atomic_write_json
from core.platform.locks import locked_path

logger = logging.getLogger(__name__)

_REPLY_GRANTS_FILENAME = "external_reply_grants.json"
_DEFAULT_TTL_HOURS = 24
MAX_REPLY_GRANTS = 200


def _store_path(anima_dir: Path) -> Path:
    return Path(anima_dir) / "state" / _REPLY_GRANTS_FILENAME


def _lock_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.lock")


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _read_entries(path: Path, now: datetime) -> tuple[list[dict[str, str]], bool]:
    """Read, validate, and prune stored entries; return whether rewrite is needed."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], False
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read reply grants at %s: %s", path, exc)
        return [], True

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Corrupt reply grant JSON at %s; treating as empty: %s", path, exc)
        return [], True

    if not isinstance(payload, dict) or not isinstance(payload.get("grants", []), list):
        logger.warning("Invalid reply grant data at %s; treating as empty", path)
        return [], True

    raw_entries = payload.get("grants", [])
    entries: list[dict[str, str]] = []
    changed = "grants" not in payload
    for item in raw_entries:
        if not isinstance(item, dict):
            changed = True
            continue

        platform = item.get("platform")
        channel_id = item.get("channel_id")
        thread_ts = item.get("thread_ts")
        granted_at = item.get("granted_at")
        expires_at = item.get("expires_at")
        granted_dt = _parse_timestamp(granted_at)
        expires_dt = _parse_timestamp(expires_at)
        if (
            not isinstance(platform, str)
            or not platform
            or not isinstance(channel_id, str)
            or not channel_id
            or not isinstance(thread_ts, str)
            or not thread_ts
            or granted_dt is None
            or expires_dt is None
            or expires_dt <= now
        ):
            changed = True
            continue

        entry = {
            "platform": platform,
            "channel_id": channel_id,
            "thread_ts": thread_ts,
            "granted_at": granted_dt.isoformat(),
            "expires_at": expires_dt.isoformat(),
        }
        if item != entry:
            changed = True
        entries.append(entry)

    entries.sort(key=lambda entry: _parse_timestamp(entry["granted_at"]) or now)
    if len(entries) > MAX_REPLY_GRANTS:
        entries = entries[-MAX_REPLY_GRANTS:]
        changed = True
    return entries, changed


def _write_entries(path: Path, entries: list[dict[str, str]]) -> None:
    atomic_write_json(path, {"grants": entries}, indent=2, ensure_ascii=False)


def record_reply_grant(
    anima_dir: Path,
    platform: str,
    channel_id: str,
    thread_ts: str,
    ttl_hours: float = _DEFAULT_TTL_HOURS,
) -> bool:
    """Record or refresh a grant for one platform channel/thread pair.

    Returns False for invalid input or when the grant could not be persisted.
    Storage errors are logged and never propagated to message delivery callers.
    """
    if not all(isinstance(value, str) and value for value in (platform, channel_id, thread_ts)):
        logger.warning("Skipping reply grant with empty platform, channel, or thread")
        return False

    try:
        ttl = float(ttl_hours)
        if not math.isfinite(ttl) or ttl <= 0:
            raise ValueError("ttl_hours must be a positive finite number")
        granted_dt = datetime.now(UTC)
        expires_dt = granted_dt + timedelta(hours=ttl)
    except (OverflowError, TypeError, ValueError) as exc:
        logger.warning("Skipping invalid reply grant TTL: %s", exc)
        return False

    entry = {
        "platform": platform,
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "granted_at": granted_dt.isoformat(),
        "expires_at": expires_dt.isoformat(),
    }
    path = _store_path(Path(anima_dir))
    key = (platform, channel_id, thread_ts)

    try:
        with locked_path(_lock_path(path), exclusive=True, thread_lock=True):
            entries, _ = _read_entries(path, granted_dt)
            entries = [
                current
                for current in entries
                if (current["platform"], current["channel_id"], current["thread_ts"]) != key
            ]
            entries.append(entry)
            entries.sort(key=lambda current: _parse_timestamp(current["granted_at"]) or granted_dt)
            if len(entries) > MAX_REPLY_GRANTS:
                entries = entries[-MAX_REPLY_GRANTS:]
            _write_entries(path, entries)
        return True
    except Exception as exc:
        logger.warning(
            "Failed to record reply grant for anima=%s platform=%s: %s",
            Path(anima_dir).name,
            platform,
            exc,
            exc_info=True,
        )
        return False


def has_reply_grant(
    anima_dir: Path,
    platform: str,
    channel_id: str,
    thread_ts: str,
) -> bool:
    """Return whether an unexpired grant matches exactly; fail closed on errors."""
    if not all(isinstance(value, str) and value for value in (platform, channel_id, thread_ts)):
        return False

    path = _store_path(Path(anima_dir))
    try:
        if not path.exists():
            return False
    except OSError as exc:
        logger.warning("Failed to inspect reply grant store at %s: %s", path, exc)
        return False

    now = datetime.now(UTC)
    key = (platform, channel_id, thread_ts)
    try:
        with locked_path(_lock_path(path), exclusive=True, thread_lock=True):
            entries, changed = _read_entries(path, now)
            matched = any((entry["platform"], entry["channel_id"], entry["thread_ts"]) == key for entry in entries)
            if changed:
                try:
                    _write_entries(path, entries)
                except OSError:
                    # Sandboxed CLI processes may have read-only access to state.
                    # The in-memory expiry check remains valid for this request.
                    logger.debug("Could not persist reply grant cleanup at %s", path, exc_info=True)
            return matched
    except Exception:
        # Atomic replacement makes an unlocked read a complete old or new
        # snapshot, which supports read-only sandboxes that cannot open/create
        # the adjacent lock file. Writes always require the lock above.
        logger.debug("Could not lock reply grant store at %s; reading snapshot", path, exc_info=True)
        try:
            entries, _ = _read_entries(path, now)
            return any((entry["platform"], entry["channel_id"], entry["thread_ts"]) == key for entry in entries)
        except Exception as exc:
            logger.warning("Failed to check reply grant at %s: %s", path, exc, exc_info=True)
            return False


def reply_grant_ok_for_action(
    anima_dir: Path | None,
    tool_name: str,
    action: str | None,
    args: dict[str, Any],
) -> bool:
    """Check whether tool arguments target a granted Slack reply thread.

    Slack channel names are deliberately not resolved here; only an exact
    channel ID match can use the grant, and no network request is made.
    """
    if anima_dir is None or tool_name != "slack" or action is None:
        return False

    normalized_action = action.replace("-", "_")
    if normalized_action == "send":
        channel_id = args.get("channel")
    elif normalized_action == "channel_post":
        channel_id = args.get("channel_id")
    else:
        return False

    thread_ts = args.get("thread_ts")
    if not isinstance(channel_id, str) or not channel_id or not isinstance(thread_ts, str) or not thread_ts:
        return False

    try:
        return has_reply_grant(Path(anima_dir), "slack", channel_id, thread_ts)
    except Exception as exc:
        logger.warning("Failed to resolve Slack reply grant: %s", exc, exc_info=True)
        return False
