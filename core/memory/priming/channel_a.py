from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Channel A: Sender profile lookup."""

import logging
from pathlib import Path

from core.config.file_access_policy import find_denied_root, load_denied_roots
from core.i18n import t
from core.integrations._async_compat import run_sync
from core.memory.peer_profiles import peer_profile_path

logger = logging.getLogger("animaworks.priming")

_PEER_PROFILE_MAX_CHARS = 800


async def channel_a_sender_profile(anima_dir: Path, sender_name: str) -> str:
    """Load shared user context and this Anima's notes about the sender."""
    from core.paths import get_shared_dir

    shared_users_dir = get_shared_dir() / "users"
    try:
        profile_path = (shared_users_dir / sender_name / "index.md").resolve()
        if not profile_path.is_relative_to(shared_users_dir.resolve()):
            logger.warning("Channel A: path traversal in sender_name=%s", sender_name)
            return ""
    except (OSError, RuntimeError, ValueError):
        logger.warning("Channel A: invalid sender_name=%s", sender_name)
        return ""

    denied_roots = load_denied_roots(anima_dir)
    profile = ""
    if find_denied_root(profile_path, denied_roots) is not None:
        logger.debug("Channel A: sender profile denied for sender=%s", sender_name)
    elif profile_path.is_file():
        try:
            profile = await run_sync(profile_path.read_text, encoding="utf-8")
        except Exception as exc:
            logger.warning("Channel A: Failed to read profile for %s: %s", sender_name, exc)

    peer_path = peer_profile_path(anima_dir, sender_name)
    peer_profile = ""
    if peer_path is not None and peer_path.is_file():
        if find_denied_root(peer_path, denied_roots) is None:
            try:
                peer_profile = await run_sync(peer_path.read_text, encoding="utf-8")
            except Exception as exc:
                logger.warning("Channel A: Failed to read peer notes for %s: %s", sender_name, exc)

    if not peer_profile.strip():
        if profile:
            logger.debug("Channel A: Loaded sender profile for %s (%d chars)", sender_name, len(profile))
        else:
            logger.debug("Channel A: No profile found for sender=%s", sender_name)
        return profile

    # Only this Anima's notes are capped here; the engine budgets the whole channel.
    peer_section = f"{t('priming.peer_notes_header')}\n{peer_profile.strip()[:_PEER_PROFILE_MAX_CHARS]}"
    # Notes go first: the engine truncates this channel from the tail.
    combined = f"{peer_section}\n\n{profile.strip()}" if profile.strip() else peer_section
    logger.debug("Channel A: Loaded sender and peer profiles for %s (%d chars)", sender_name, len(combined))
    return combined
