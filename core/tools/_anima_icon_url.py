# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core, licensed under Apache-2.0.

"""Anima icon URL resolution — dashboard, outbound, Slack, notifications, tools, etc.

Private helper module (``_`` prefix): not registered in :data:`~core.tools.TOOL_MODULES`.

Resolution order (first non-empty wins):

  1. **Per-Anima** ``icon_url`` in ``status.json`` — absolute URL for one specific Anima.
  2. **Env var** ``ICON_URL_TEMPLATE`` — template with ``{name}`` placeholder.
  3. **Top-level config** ``icon_url_template`` in ``config.json`` — same template syntax.
  4. **Per-channel** ``icon_path_template`` on the Slack notification channel ``config`` dict
     (legacy; kept for backward compatibility).
  5. **Internal asset** ``ANIMAWORKS_SERVER_URL`` + ``/api/animas/{name}/assets/<file>`` when
     the asset file exists on disk.
  6. ``""`` (no icon).

Templates use ``{name}`` which is replaced by the Anima directory name.  Templates starting
with ``http://`` or ``https://`` are treated as external URLs; otherwise they are internal
path segments prepended by ``ANIMAWORKS_SERVER_URL``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

__all__ = [
    "ANIMA_ICON_ASSET_FILENAME",
    "ANIMA_ICON_ASSET_FILENAME_REALISTIC",
    "DEFAULT_INTERNAL_ICON_PATH_TEMPLATE",
    "DEFAULT_INTERNAL_ICON_PATH_TEMPLATE_REALISTIC",
    "ICON_PATH_TEMPLATE_CONFIG_KEY",
    "persist_anima_icon_path_template",
    "persist_anima_icon_url_template",
    "resolve_anima_icon_identity",
    "resolve_anima_icon_url",
    "template_is_external_icon_url",
]

# ── Icon filenames (anime vs realistic; UI can switch without regenerating) ──

ANIMA_ICON_ASSET_FILENAME = "icon.png"
ANIMA_ICON_ASSET_FILENAME_REALISTIC = "icon_realistic.png"
ANIMA_BUSTUP_ASSET_FILENAME = "avatar_bustup.png"
ANIMA_BUSTUP_ASSET_FILENAME_REALISTIC = "avatar_bustup_realistic.png"

ICON_URL_TEMPLATE_CONFIG_KEY = "icon_url_template"
ICON_PATH_TEMPLATE_CONFIG_KEY = "icon_path_template"

DEFAULT_INTERNAL_ICON_PATH_TEMPLATE = "/api/animas/{name}/assets/icon.png"
DEFAULT_INTERNAL_ICON_PATH_TEMPLATE_REALISTIC = "/api/animas/{name}/assets/icon_realistic.png"

_EXTERNAL_ICON_URL_PREFIX_RE = re.compile(r"^https?://", re.IGNORECASE)

_ICON_URL_TEMPLATE_ENV_KEY = "ICON_URL_TEMPLATE"


def template_is_external_icon_url(template: str) -> bool:
    """True if *template* is intended for Slack/Chatwork/etc. (absolute ``http(s)`` URL after format)."""
    return bool(template and _EXTERNAL_ICON_URL_PREFIX_RE.match(template.strip()))


# ── Layer 1: Per-Anima icon_url from status.json ────────────────────────────


def _get_per_anima_icon_url(anima_name: str) -> str:
    """Read ``icon_url`` from the Anima's ``status.json`` (lightweight, no config load).

    Only ``http`` / ``https`` URLs are accepted; other schemes are ignored.
    """
    try:
        from core.paths import get_animas_dir

        status_path = get_animas_dir() / anima_name / "status.json"
        if not status_path.is_file():
            return ""
        data = json.loads(status_path.read_text(encoding="utf-8"))
        url = str(data.get("icon_url") or "").strip()
        if url and not _EXTERNAL_ICON_URL_PREFIX_RE.match(url):
            logger.warning("Ignoring non-http icon_url in status.json for '%s': %s", anima_name, url)
            return ""
        return url
    except Exception:
        return ""


# ── Layer 2 & 3: Global templates (env var / config.json) ───────────────────


def _get_global_icon_url_template() -> str:
    """Return the top-level ``icon_url_template`` from ``config.json``, or ``""``."""
    try:
        from core.config import load_config

        return str(load_config().icon_url_template or "").strip()
    except Exception:
        return ""


def _format_template(template: str, anima_name: str) -> str:
    """Expand ``{name}`` in a template, handling both external and internal URLs.

    Uses :meth:`str.format_map` with a fallback dict so that stray
    placeholders (e.g. ``{foo}``) do not raise :class:`KeyError`.
    """
    safe_map: dict[str, str] = {"name": anima_name}
    try:
        if template_is_external_icon_url(template):
            return template.format_map(safe_map)
        base = os.environ.get("ANIMAWORKS_SERVER_URL", "").strip().rstrip("/")
        if not base:
            return ""
        safe_map["name"] = quote(anima_name, safe="")
        path_resolved = template.format_map(safe_map)
        if not path_resolved.startswith("/"):
            path_resolved = "/" + path_resolved
        return base + path_resolved
    except (KeyError, ValueError, IndexError):
        logger.warning("Invalid icon URL template: %r", template)
        return ""


# ── Layer 4: Per-channel icon_path_template (legacy backward compat) ────────


def _icon_path_template_from_mapping(channel_config: dict[str, Any]) -> str:
    raw = channel_config.get(ICON_PATH_TEMPLATE_CONFIG_KEY) or channel_config.get(ICON_URL_TEMPLATE_CONFIG_KEY) or ""
    return str(raw).strip()


def _first_slack_icon_path_template_from_config() -> str:
    try:
        from core.config import load_config

        cfg = load_config()
        if not cfg.human_notification or not cfg.human_notification.channels:
            return ""
        for ch in cfg.human_notification.channels:
            if ch.type == "slack" and ch.enabled:
                t = _icon_path_template_from_mapping(ch.config)
                if t:
                    return t
        return ""
    except Exception:
        logger.debug("Failed to load icon path template from config", exc_info=True)
    return ""


def _get_icon_path_template(channel_config: dict[str, Any] | None) -> str:
    if channel_config is not None:
        t = _icon_path_template_from_mapping(channel_config)
        if t:
            return t
    return _first_slack_icon_path_template_from_config()


# ── Layer 5: Internal asset fallback ────────────────────────────────────────


def _icon_asset_for_url(anima_name: str) -> tuple[Path, str] | None:
    """Return ``(path, filename)`` for an existing icon-ish asset."""
    from core.paths import get_animas_dir

    assets = get_animas_dir() / anima_name / "assets"
    try:
        from core.config import load_config

        style = load_config().image_gen.image_style or "anime"
    except Exception:
        style = "anime"

    candidates = (
        (
            (ANIMA_ICON_ASSET_FILENAME_REALISTIC, ANIMA_ICON_ASSET_FILENAME),
            (ANIMA_BUSTUP_ASSET_FILENAME_REALISTIC, ANIMA_BUSTUP_ASSET_FILENAME),
        )
        if style == "realistic"
        else (
            (ANIMA_ICON_ASSET_FILENAME, ANIMA_ICON_ASSET_FILENAME_REALISTIC),
            (ANIMA_BUSTUP_ASSET_FILENAME, ANIMA_BUSTUP_ASSET_FILENAME_REALISTIC),
        )
    )
    for pair in candidates:
        for filename in pair:
            p = assets / filename
            if p.is_file():
                return (p, filename)
    return None


# ── Public API ──────────────────────────────────────────────────────────────


def resolve_anima_icon_url(
    anima_name: str,
    channel_config: dict[str, Any] | None = None,
) -> str:
    """Return a full URL for an Anima icon, or ``""`` if unavailable.

    Resolution priority (first non-empty wins):

      1. Per-Anima ``icon_url`` in ``status.json``
      2. ``ICON_URL_TEMPLATE`` env var (template with ``{name}``)
      3. ``config.json`` top-level ``icon_url_template``
      4. Per-channel ``icon_path_template`` (legacy)
      5. Internal asset path via ``ANIMAWORKS_SERVER_URL``
    """
    if not anima_name:
        return ""

    # 1. Per-Anima override
    per_anima = _get_per_anima_icon_url(anima_name)
    if per_anima:
        return per_anima

    # 2. Env var template
    env_template = os.environ.get(_ICON_URL_TEMPLATE_ENV_KEY, "").strip()
    if env_template:
        return _format_template(env_template, anima_name)

    # 3. Top-level config template
    global_template = _get_global_icon_url_template()
    if global_template:
        return _format_template(global_template, anima_name)

    # 4. Per-channel template (legacy backward compat)
    ch_template = _get_icon_path_template(channel_config)
    if ch_template:
        return _format_template(ch_template, anima_name)

    # 5. Internal asset fallback
    base = os.environ.get("ANIMAWORKS_SERVER_URL", "").strip().rstrip("/")
    asset = _icon_asset_for_url(anima_name)
    if asset is not None and base:
        _, filename = asset
        return f"{base}/api/animas/{quote(anima_name, safe='')}/assets/{filename}"

    return ""


def resolve_anima_icon_identity(
    anima_name: str,
    channel_config: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return ``(anima_display_name, icon_url)`` for APIs that take username + icon_url."""
    if not anima_name:
        return ("", "")
    return (anima_name, resolve_anima_icon_url(anima_name, channel_config))


# ── Persist helper (called after icon generation) ───────────────────────────


def persist_anima_icon_path_template() -> None:
    """Persist default internal ``icon_path_template`` on each enabled Slack channel.

    **Skips entirely** when a higher-priority source is configured:
    - ``ICON_URL_TEMPLATE`` env var is set, OR
    - ``config.json`` top-level ``icon_url_template`` is set.

    Also skips individual channels whose template is already an external URL
    (e.g. GitHub raw) to avoid overwriting user-configured CDN/public-repo URLs.
    """
    if os.environ.get(_ICON_URL_TEMPLATE_ENV_KEY, "").strip():
        return

    from core.config import load_config, save_config

    cfg = load_config()
    if cfg.icon_url_template:
        return
    if not cfg.human_notification or not cfg.human_notification.channels:
        return
    style = cfg.image_gen.image_style or "anime"
    want = (
        DEFAULT_INTERNAL_ICON_PATH_TEMPLATE_REALISTIC if style == "realistic" else DEFAULT_INTERNAL_ICON_PATH_TEMPLATE
    )
    changed = False
    for ch in cfg.human_notification.channels:
        if ch.type != "slack" or not ch.enabled:
            continue
        cur = _icon_path_template_from_mapping(ch.config)
        if template_is_external_icon_url(cur):
            continue
        if cur != want:
            ch.config[ICON_PATH_TEMPLATE_CONFIG_KEY] = want
            ch.config.pop(ICON_URL_TEMPLATE_CONFIG_KEY, None)
            changed = True
    if changed:
        save_config(cfg)


# Backward-compatible name (older call sites / patches).
persist_anima_icon_url_template = persist_anima_icon_path_template
