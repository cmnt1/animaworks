# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core, licensed under Apache-2.0.

"""Anima icon URL resolution — dashboard, outbound, Slack, notifications, tools, etc.

Private helper module (``_`` prefix): not registered in :data:`~core.tools.TOOL_MODULES`.

Each Slack (human notification) channel may set ``icon_path_template`` on its ``config`` object.

**Template kind (by prefix):**

- If the template **starts with** ``http://`` or ``https://``, it is treated as an **externally
  reachable URL** after ``str.format(name=...)``. Use for icons that **Slack, Chatwork, and other
  external services** must fetch over the internet (e.g. CDN).
- **Otherwise** the value is a **path template for internal use** (AnimaWorks **frontend** can
  load it when the app and API share origin or VPN). Resolve by prepending ``ANIMAWORKS_SERVER_URL``;
  the on-disk file under ``get_animas_dir() / anima_name / assets/icon.png`` (anime) or
  ``.../icon_realistic.png`` (realistic) must exist when this URL is required for outbound/notifications
  that attach ``icon_url``.

Resolution order:

  1. If ``channel_config`` is passed (e.g. the ``config`` dict for the Slack channel currently
     sending), ``icon_path_template`` / legacy ``icon_url_template`` on **that** dict are used first.
  2. Otherwise ``icon_path_template`` from the **first enabled** Slack channel under
     ``human_notification.channels`` (via :func:`load_config`).
  3. If no template: same-origin style URL from ``ANIMAWORKS_SERVER_URL`` + ``/api/animas/.../icon.png``
     or ``.../icon_realistic.png`` (per :attr:`~core.config.schemas.ImageGenConfig.image_style`) when the file exists.
  4. External templates: ``{name}`` is the Anima directory name (unquoted in the URL string for
     typical CDN patterns).
  5. Internal path templates: ``{name}`` is passed through :func:`urllib.parse.quote` for path segments.

When icons are generated, :func:`persist_anima_icon_path_template` stores the default internal
path (``icon.png`` or ``icon_realistic.png`` under ``assets/``, matching image style) as ``icon_path_template``.
"""

from __future__ import annotations

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

ICON_URL_TEMPLATE_CONFIG_KEY = "icon_url_template"
ICON_PATH_TEMPLATE_CONFIG_KEY = "icon_path_template"

DEFAULT_INTERNAL_ICON_PATH_TEMPLATE = "/api/animas/{name}/assets/icon.png"
DEFAULT_INTERNAL_ICON_PATH_TEMPLATE_REALISTIC = "/api/animas/{name}/assets/icon_realistic.png"

_EXTERNAL_ICON_URL_PREFIX_RE = re.compile(r"^https?://", re.IGNORECASE)


def template_is_external_icon_url(template: str) -> bool:
    """True if *template* is intended for Slack/Chatwork/etc. (absolute ``http(s)`` URL after format)."""
    return bool(template and _EXTERNAL_ICON_URL_PREFIX_RE.match(template.strip()))


def _icon_path_template_from_mapping(channel_config: dict[str, Any]) -> str:
    raw = channel_config.get(ICON_PATH_TEMPLATE_CONFIG_KEY) or channel_config.get(ICON_URL_TEMPLATE_CONFIG_KEY) or ""
    return str(raw).strip()


def _icon_asset_for_url(anima_name: str) -> tuple[Path, str] | None:
    """Return ``(path, filename)`` for an existing icon asset (anime and/or realistic)."""
    from core.paths import get_animas_dir

    assets = get_animas_dir() / anima_name / "assets"
    try:
        from core.config import load_config

        style = load_config().image_gen.image_style or "anime"
    except Exception:
        style = "anime"

    if style == "realistic":
        for path, filename in (
            (assets / ANIMA_ICON_ASSET_FILENAME_REALISTIC, ANIMA_ICON_ASSET_FILENAME_REALISTIC),
            (assets / ANIMA_ICON_ASSET_FILENAME, ANIMA_ICON_ASSET_FILENAME),
        ):
            if path.is_file():
                return (path, filename)
    else:
        for path, filename in (
            (assets / ANIMA_ICON_ASSET_FILENAME, ANIMA_ICON_ASSET_FILENAME),
            (assets / ANIMA_ICON_ASSET_FILENAME_REALISTIC, ANIMA_ICON_ASSET_FILENAME_REALISTIC),
        ):
            if path.is_file():
                return (path, filename)
    return None


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


def resolve_anima_icon_url(
    anima_name: str,
    channel_config: dict[str, Any] | None = None,
) -> str:
    """Return a full ``https`` URL for an Anima icon, or ``\"\"`` if unavailable.

    *anima_name* is the Anima directory name; on-disk path is ``get_animas_dir() / anima_name``.
    """
    if not anima_name:
        return ""
    base = os.environ.get("ANIMAWORKS_SERVER_URL", "").strip().rstrip("/")

    template = _get_icon_path_template(channel_config)

    if template:
        if template_is_external_icon_url(template):
            return template.format(name=anima_name)
        if not base:
            return ""
        path_resolved = template.format(name=quote(anima_name, safe=""))
        if not path_resolved.startswith("/"):
            path_resolved = "/" + path_resolved
        return base.rstrip("/") + path_resolved

    if not base:
        return ""
    asset = _icon_asset_for_url(anima_name)
    if asset is None:
        return ""
    _, filename = asset
    return f"{base.rstrip('/')}/api/animas/{quote(anima_name, safe='')}/assets/{filename}"


def resolve_anima_icon_identity(
    anima_name: str,
    channel_config: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return ``(anima_display_name, icon_url)`` for APIs that take username + icon_url."""
    if not anima_name:
        return ("", "")
    return (anima_name, resolve_anima_icon_url(anima_name, channel_config))


def persist_anima_icon_path_template() -> None:
    """Persist default internal ``icon_path_template`` on each enabled Slack channel.

    Called after icon generation. Path follows :attr:`~core.config.schemas.ImageGenConfig.image_style`
    (``icon.png`` vs ``icon_realistic.png``). Removes legacy ``icon_url_template`` when updating.
    """
    from core.config import load_config, save_config

    cfg = load_config()
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
        if cur != want:
            ch.config[ICON_PATH_TEMPLATE_CONFIG_KEY] = want
            ch.config.pop(ICON_URL_TEMPLATE_CONFIG_KEY, None)
            changed = True
    if changed:
        save_config(cfg)


# Backward-compatible name (older call sites / patches).
persist_anima_icon_url_template = persist_anima_icon_path_template
