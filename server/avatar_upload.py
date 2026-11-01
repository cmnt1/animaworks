from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Upload Anima avatar PNGs to the Xserver VPS for public hosting.

Avatars are copied over SSH (tar) to ``/srv/OneDriveBiz/WebSite/animaworks-avatars/``
and served by nginx at ``https://www.skmt2.net/animaworks-avatars/{name}.png``.
(Until 2026-10 they were FTP-uploaded to the Xserver rental server.)

Overridable via environment: AVATAR_SSH_DEST, AVATAR_SSH_KEY, AVATAR_REMOTE_DIR, AVATAR_PUBLIC_BASE_URL.

This module is called:
  - At server startup (all avatars)
  - After asset adoption / avatar regeneration (single anima)
"""

import io
import logging
import os
import subprocess
import tarfile
from pathlib import Path

logger = logging.getLogger("animaworks.avatar_upload")

_AVATAR_DIR = Path(__file__).resolve().parents[1] / "assets" / "platform-avatars"
# Legacy fallback for migration
_LEGACY_AVATAR_DIR = Path(__file__).resolve().parents[1] / "assets" / "slack-avatars"
_SSH_DEST = os.environ.get("AVATAR_SSH_DEST", "cmnt@xserver-vps")
_SSH_KEY = os.environ.get("AVATAR_SSH_KEY", str(Path.home() / ".ssh" / "xserver_vps"))
_REMOTE_DIR = os.environ.get("AVATAR_REMOTE_DIR", "/srv/OneDriveBiz/WebSite/animaworks-avatars")
_PUBLIC_BASE_URL = os.environ.get("AVATAR_PUBLIC_BASE_URL", "https://www.skmt2.net/animaworks-avatars")


def _upload_files(png_files: list[Path]) -> list[str]:
    """Copy PNGs to the VPS in one ssh call (tar stream). Returns uploaded anima names."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for p in png_files:
            info = tar.gettarinfo(str(p), arcname=f"{p.stem}.png")
            info.mode = 0o644
            with open(p, "rb") as f:
                tar.addfile(info, f)
    cmd = [
        "ssh",
        "-i",
        _SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=20",
        _SSH_DEST,
        f"tar -xf - -C {_REMOTE_DIR}",
    ]
    res = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, timeout=120)
    if res.returncode != 0:
        raise RuntimeError(
            f"ssh avatar upload failed (rc={res.returncode}): {res.stderr.decode('utf-8', 'replace')[-300:]}"
        )
    return [p.stem for p in png_files]


def upload_avatar(anima_name: str) -> str:
    """Upload a single anima's avatar PNG to the VPS.

    Returns the public URL on success, or empty string on failure.
    """
    png_path = _AVATAR_DIR / f"{anima_name}.png"
    if not png_path.is_file():
        # Legacy fallback
        png_path = _LEGACY_AVATAR_DIR / f"{anima_name}.png"
    if not png_path.is_file():
        logger.debug("No avatar PNG for '%s' at %s", anima_name, png_path)
        return ""
    try:
        _upload_files([png_path])
        url = f"{_PUBLIC_BASE_URL}/{anima_name}.png"
        logger.info("Uploaded avatar for '%s' -> %s", anima_name, url)
        return url
    except Exception:
        logger.warning("Avatar upload failed for '%s'", anima_name, exc_info=True)
        return ""


def upload_all_avatars() -> dict[str, str]:
    """Upload all avatar PNGs found in assets/platform-avatars/ (or legacy slack-avatars/).

    Returns dict of {anima_name: public_url} for successful uploads.
    """
    png_files: list[Path] = []
    seen: set[str] = set()
    for d in (_AVATAR_DIR, _LEGACY_AVATAR_DIR):
        if d.is_dir():
            for p in d.glob("*.png"):
                if p.stem not in seen:
                    png_files.append(p)
                    seen.add(p.stem)
    if not png_files:
        logger.info("No avatar PNGs found in %s", _AVATAR_DIR)
        return {}
    try:
        names = _upload_files(png_files)
    except Exception:
        logger.warning("Avatar upload to VPS failed", exc_info=True)
        return {}
    results = {n: f"{_PUBLIC_BASE_URL}/{n}.png" for n in names}
    logger.info("Uploaded %d/%d avatar(s) to VPS", len(results), len(png_files))
    return results


def get_avatar_public_url(anima_name: str) -> str:
    """Return the public URL for an anima's avatar (without uploading)."""
    return f"{_PUBLIC_BASE_URL}/{anima_name}.png"
