from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Upload Slack avatar PNGs to XSERVER for public hosting.

Avatars are uploaded via FTP to ``xs642990.xsrv.jp/public_html/animaworks-avatars/``
making them publicly accessible at ``https://xs642990.xsrv.jp/animaworks-avatars/{name}.png``.

This module is called:
  - At server startup (all avatars)
  - After asset adoption / avatar regeneration (single anima)
"""

import ftplib
import logging
import os
from pathlib import Path

logger = logging.getLogger("animaworks.slack_avatar_upload")

_SLACK_AVATAR_DIR = Path(__file__).resolve().parents[1] / "assets" / "slack-avatars"
_FTP_REMOTE_DIR = "/xs642990.xsrv.jp/public_html/animaworks-avatars"
_PUBLIC_BASE_URL = "https://xs642990.xsrv.jp/animaworks-avatars"


def _get_xserver_config() -> dict | None:
    """Load XSERVER FTP credentials from credentials cascade.

    Resolution order:
      1. Environment variables (XSERVER_FTP_HOST, _USER, _PASS)
      2. config.json ``credentials.xserver_ftp``
      3. Legacy abconfig bridge (if available)
    """
    host = os.environ.get("XSERVER_FTP_HOST")
    user = os.environ.get("XSERVER_FTP_USER")
    password = os.environ.get("XSERVER_FTP_PASS")

    if not all((host, user, password)):
        try:
            from core.tools._base import get_credential

            host = host or get_credential("xserver_ftp", "xserver", "ftp_host", "XSERVER_FTP_HOST")
            user = user or get_credential("xserver_ftp", "xserver", "ftp_user", "XSERVER_FTP_USER")
            password = password or get_credential("xserver_ftp", "xserver", "ftp_pass", "XSERVER_FTP_PASS")
        except Exception:
            pass

    if not all((host, user, password)):
        logger.debug("XSERVER FTP credentials not found in env/config")
        return None

    return {"ftp_host": host, "ftp_user": user, "ftp_pass": password}


def _ensure_remote_dir(ftp: ftplib.FTP, path: str) -> None:
    """Create remote directory if it doesn't exist."""
    try:
        ftp.cwd(path)
    except ftplib.error_perm:
        ftp.mkd(path)
        ftp.cwd(path)


def upload_avatar(anima_name: str) -> str:
    """Upload a single anima's avatar PNG to XSERVER.

    Returns the public URL on success, or empty string on failure.
    """
    png_path = _SLACK_AVATAR_DIR / f"{anima_name}.png"
    if not png_path.is_file():
        logger.debug("No avatar PNG for '%s' at %s", anima_name, png_path)
        return ""

    xconf = _get_xserver_config()
    if not xconf:
        logger.warning("XSERVER config not available; cannot upload avatar for '%s'", anima_name)
        return ""

    try:
        ftp = ftplib.FTP(xconf["ftp_host"], timeout=30)
        ftp.login(xconf["ftp_user"], xconf["ftp_pass"])
        _ensure_remote_dir(ftp, _FTP_REMOTE_DIR)

        remote_filename = f"{anima_name}.png"
        with open(png_path, "rb") as f:
            ftp.storbinary(f"STOR {remote_filename}", f)

        ftp.quit()

        url = f"{_PUBLIC_BASE_URL}/{anima_name}.png"
        logger.info("Uploaded avatar for '%s' -> %s", anima_name, url)
        return url

    except Exception:
        logger.warning("FTP upload failed for avatar '%s'", anima_name, exc_info=True)
        return ""


def upload_all_avatars() -> dict[str, str]:
    """Upload all avatar PNGs found in assets/slack-avatars/.

    Returns dict of {anima_name: public_url} for successful uploads.
    """
    if not _SLACK_AVATAR_DIR.is_dir():
        logger.info("No slack-avatars directory at %s", _SLACK_AVATAR_DIR)
        return {}

    png_files = list(_SLACK_AVATAR_DIR.glob("*.png"))
    if not png_files:
        logger.info("No avatar PNGs found in %s", _SLACK_AVATAR_DIR)
        return {}

    xconf = _get_xserver_config()
    if not xconf:
        logger.warning("XSERVER config not available; skipping avatar upload")
        return {}

    results: dict[str, str] = {}

    try:
        ftp = ftplib.FTP(xconf["ftp_host"], timeout=30)
        ftp.login(xconf["ftp_user"], xconf["ftp_pass"])
        _ensure_remote_dir(ftp, _FTP_REMOTE_DIR)

        for png_path in png_files:
            anima_name = png_path.stem
            try:
                with open(png_path, "rb") as f:
                    ftp.storbinary(f"STOR {anima_name}.png", f)
                url = f"{_PUBLIC_BASE_URL}/{anima_name}.png"
                results[anima_name] = url
                logger.debug("Uploaded avatar: %s -> %s", anima_name, url)
            except Exception:
                logger.warning("Failed to upload avatar for '%s'", anima_name, exc_info=True)

        ftp.quit()

    except Exception:
        logger.warning("FTP connection failed for avatar upload", exc_info=True)

    if results:
        logger.info(
            "Uploaded %d/%d avatar(s) to XSERVER", len(results), len(png_files)
        )

    return results


def get_avatar_public_url(anima_name: str) -> str:
    """Return the public URL for an anima's avatar (without uploading)."""
    return f"{_PUBLIC_BASE_URL}/{anima_name}.png"
