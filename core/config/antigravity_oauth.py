from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""OAuth credential reader and refresher for the Antigravity CLI integration.

Antigravity CLI (``agy``) is Google's replacement for Gemini CLI on
Google AI Pro / Ultra / Free-tier accounts (rollover deadline 2026-06-18).
Credentials are stored in the OS keyring rather than a flat JSON file:

  - Windows: Credential Manager, target ``gemini:antigravity`` (Generic)
  - macOS:   Keychain (not yet implemented here)
  - Linux:   libsecret (not yet implemented here)

The blob is JSON with shape::

    {
        "token": {
            "access_token": "ya29.…",
            "token_type": "Bearer",
            "refresh_token": "1//…",
            "expiry": "2026-05-25T15:33:57.3285795+09:00"
        },
        "auth_method": "consumer"
    }

Unlike Gemini CLI's ``oauth_creds.json``, the ``client_id``/``client_secret``
are NOT included in the credential blob — they live inside the ``agy``
binary. AnimaWorks reads its own copy of those values from the standard
credential cascade (vault → shared/credentials.json → abconfig/Cnct_Env.py
→ env var) under the keys ``ANTIGRAVITY_OAUTH_CLIENT_ID`` /
``ANTIGRAVITY_OAUTH_CLIENT_SECRET`` so refresh works without invoking
``agy``.  Values can be obtained from Antigravity's binary or from
third-party reverse-engineered ports (e.g. github.com/firdyfirdy/antigravity-auth).

This module is **dedicated to the Antigravity CLI flow** and is fully
isolated from the Workspace-side Google OAuth (Gmail, Calendar, Tasks).
"""

import ctypes
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("animaworks.config.antigravity_oauth")

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Cloud Code Assist project discovery (loadCodeAssist endpoint).  Free-tier
# users receive a per-account managed project (e.g. ``circular-verve-0h50h``)
# that differs from the fixed AI Pro common id.  We discover and cache the
# right one at first use.
_LOAD_CODE_ASSIST_URL = (
    "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
)

# Minimal client metadata accepted by loadCodeAssist.  Values are
# informational only; the API does not enforce specific values.
_CLIENT_METADATA = {
    "ideType": "IDE_UNSPECIFIED",
    "ideVersion": "0.0.0",
    "pluginVersion": "0.0.0",
    "platform": "PLATFORM_UNSPECIFIED",
    "pluginType": "GEMINI",
    "ideName": "animaworks",
    "updateChannel": "stable",
}

# Windows Credential Manager target name written by agy.
_WIN_TARGET = "gemini:antigravity"

# Default project ID for personal Google AI Pro accounts that don't own a
# GCP project (same as for Gemini CLI).
DEFAULT_PROJECT_ID = "276287556352"

# Refresh access_token slightly ahead of true expiry so in-flight requests
# don't race against expiration.
_TOKEN_EXPIRY_BUFFER_SEC = 60


@dataclass
class AntigravityCredentials:
    """Parsed contents of the keyring credential blob."""

    access_token: str
    refresh_token: str
    expiry_dt: datetime  # tz-aware datetime
    token_type: str = "Bearer"
    auth_method: str = "consumer"

    def is_expired(self, buffer_sec: int = _TOKEN_EXPIRY_BUFFER_SEC) -> bool:
        """Return True when access_token expires within ``buffer_sec`` seconds."""
        return self.expiry_dt.timestamp() <= (time.time() + buffer_sec)


# ── Windows Credential Manager helpers (via Win32 advapi32) ─────────────────


_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_CRED_PERSIST_ENTERPRISE = 3


if sys.platform == "win32":
    from ctypes import wintypes

    class _CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIAL)),
    ]
    _advapi32.CredReadW.restype = wintypes.BOOL
    _advapi32.CredWriteW.argtypes = [
        ctypes.POINTER(_CREDENTIAL),
        wintypes.DWORD,
    ]
    _advapi32.CredWriteW.restype = wintypes.BOOL
    _advapi32.CredFree.argtypes = [ctypes.c_void_p]
    _advapi32.CredFree.restype = None


def _win_cred_read(target: str) -> tuple[str, str] | None:
    """Read a Generic credential from Windows Credential Manager.

    Returns ``(username, blob_text)`` or ``None`` if missing/error.
    """
    if sys.platform != "win32":
        return None
    cred_ptr = ctypes.POINTER(_CREDENTIAL)()
    ok = _advapi32.CredReadW(
        target, _CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr)
    )
    if not ok:
        err = ctypes.get_last_error()
        if err == 1168:  # ERROR_NOT_FOUND
            return None
        logger.warning(
            "CredRead(%s) failed: error=%d", target, err
        )
        return None
    try:
        cred = cred_ptr.contents
        username = cred.UserName or ""
        blob_bytes = ctypes.string_at(
            cred.CredentialBlob, cred.CredentialBlobSize
        )
        text = blob_bytes.decode("utf-8", errors="replace")
        return username, text
    finally:
        _advapi32.CredFree(cred_ptr)


def _win_cred_write(target: str, username: str, blob_text: str) -> bool:
    """Write a Generic credential to Windows Credential Manager.

    Returns True on success.
    """
    if sys.platform != "win32":
        return False
    blob_bytes = blob_text.encode("utf-8")
    blob_buf = (ctypes.c_byte * len(blob_bytes))(*blob_bytes)
    cred = _CREDENTIAL(
        Flags=0,
        Type=_CRED_TYPE_GENERIC,
        TargetName=target,
        Comment=None,
        LastWritten=wintypes.FILETIME(0, 0),
        CredentialBlobSize=len(blob_bytes),
        CredentialBlob=ctypes.cast(blob_buf, ctypes.POINTER(ctypes.c_byte)),
        Persist=_CRED_PERSIST_LOCAL_MACHINE,
        AttributeCount=0,
        Attributes=None,
        TargetAlias=None,
        UserName=username,
    )
    ok = _advapi32.CredWriteW(ctypes.byref(cred), 0)
    if not ok:
        err = ctypes.get_last_error()
        logger.warning("CredWrite(%s) failed: error=%d", target, err)
        return False
    return True


# ── Credential blob parse / serialize ───────────────────────────────────────


def _parse_blob(blob_text: str) -> AntigravityCredentials | None:
    """Parse the JSON blob written by agy into our dataclass."""
    try:
        data = json.loads(blob_text)
    except json.JSONDecodeError as exc:
        logger.warning("Antigravity credential blob is not JSON: %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    token = data.get("token")
    if not isinstance(token, dict):
        return None
    try:
        expiry_str = str(token["expiry"])
        expiry_dt = datetime.fromisoformat(expiry_str)
        return AntigravityCredentials(
            access_token=str(token["access_token"]),
            refresh_token=str(token["refresh_token"]),
            expiry_dt=expiry_dt,
            token_type=str(token.get("token_type", "Bearer")),
            auth_method=str(data.get("auth_method", "consumer")),
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Antigravity credential blob missing fields: %s", exc)
        return None


def _serialize_blob(creds: AntigravityCredentials) -> str:
    """Serialize credentials back into agy's JSON envelope format."""
    return json.dumps(
        {
            "token": {
                "access_token": creds.access_token,
                "token_type": creds.token_type,
                "refresh_token": creds.refresh_token,
                "expiry": creds.expiry_dt.isoformat(),
            },
            "auth_method": creds.auth_method,
        },
        separators=(",", ":"),
    )


# ── Public API ──────────────────────────────────────────────────────────────


def load_credentials() -> AntigravityCredentials | None:
    """Read and parse Antigravity credentials from the OS keyring."""
    if sys.platform != "win32":
        logger.debug(
            "Antigravity credential reader: %s not yet implemented", sys.platform
        )
        return None
    pair = _win_cred_read(_WIN_TARGET)
    if pair is None:
        return None
    _username, blob_text = pair
    return _parse_blob(blob_text)


def save_credentials(creds: AntigravityCredentials) -> bool:
    """Write refreshed credentials back to the OS keyring."""
    if sys.platform != "win32":
        return False
    blob_text = _serialize_blob(creds)
    return _win_cred_write(_WIN_TARGET, "antigravity", blob_text)


def _get_client_credentials() -> tuple[str, str] | None:
    """Resolve Antigravity OAuth client_id / client_secret from the cascade.

    Looks up via ``resolve_env_style_credential`` (vault → shared creds →
    abconfig Cnct_Env.py → env var).  Returns ``None`` when either value
    is missing.
    """
    from core.tools._base import resolve_env_style_credential

    cid = resolve_env_style_credential("ANTIGRAVITY_OAUTH_CLIENT_ID")
    csecret = resolve_env_style_credential("ANTIGRAVITY_OAUTH_CLIENT_SECRET")
    if not cid or not csecret:
        return None
    return cid, csecret


def refresh_access_token(
    creds: AntigravityCredentials,
) -> AntigravityCredentials | None:
    """Exchange the refresh_token for a new access_token via Google OAuth2.

    On success writes the updated credentials back to the keyring so the
    ``agy`` CLI also sees the refreshed token.
    """
    client = _get_client_credentials()
    if client is None:
        logger.warning(
            "Antigravity refresh aborted: ANTIGRAVITY_OAUTH_CLIENT_ID / "
            "ANTIGRAVITY_OAUTH_CLIENT_SECRET not configured (set in "
            "abconfig/secrets_local.py via Cnct_Env.py)"
        )
        return None
    client_id, client_secret = client
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": creds.refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        _GOOGLE_TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body_text = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            body_text = "<unreadable>"
        logger.warning(
            "Antigravity token refresh failed (HTTP %s): %s",
            exc.code,
            body_text,
        )
        return None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("Antigravity token refresh error: %s", exc)
        return None

    new_access = str(payload.get("access_token", ""))
    if not new_access:
        logger.warning("Antigravity token refresh returned empty access_token")
        return None
    expires_in_sec = int(payload.get("expires_in", 3600))
    new_expiry = datetime.fromtimestamp(
        time.time() + expires_in_sec, tz=creds.expiry_dt.tzinfo
    )

    updated = AntigravityCredentials(
        access_token=new_access,
        # Google occasionally rotates refresh_token; prefer the new one.
        refresh_token=str(payload.get("refresh_token", creds.refresh_token)),
        expiry_dt=new_expiry,
        token_type=str(payload.get("token_type", creds.token_type)),
        auth_method=creds.auth_method,
    )
    # Best-effort write-back so ``agy`` CLI also picks up the refresh.
    save_credentials(updated)
    return updated


_PROJECT_CACHE: dict[str, str] = {}


def discover_project_id(access_token: str) -> str | None:
    """Call ``loadCodeAssist`` to fetch the user's managed project id.

    Free-tier and Pro users receive different project ids (e.g. free tier
    gets a per-account managed slug like ``circular-verve-0h50h``); the
    fixed default is correct only for some account types.  Caches the
    result keyed by access_token prefix so repeated calls within the same
    session are cheap.
    """
    cache_key = access_token[:16]
    if cache_key in _PROJECT_CACHE:
        return _PROJECT_CACHE[cache_key]

    body = json.dumps({"metadata": _CLIENT_METADATA}).encode("utf-8")
    req = urllib.request.Request(
        _LOAD_CODE_ASSIST_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body_text = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            body_text = "<unreadable>"
        logger.warning(
            "loadCodeAssist failed (HTTP %s): %s", exc.code, body_text
        )
        return None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("loadCodeAssist error: %s", exc)
        return None

    project_id = payload.get("cloudaicompanionProject")
    if isinstance(project_id, str) and project_id:
        _PROJECT_CACHE[cache_key] = project_id
        return project_id
    return None


def get_valid_access_token() -> tuple[str, str] | None:
    """Return ``(access_token, project_id)`` ready for API use.

    Loads credentials, refreshes if expired, and resolves the project id
    in this priority order:
      1. ``GEMINI_PRO_PROJECT_ID`` env var (explicit override)
      2. ``loadCodeAssist`` discovery (per-account managed project)
      3. ``DEFAULT_PROJECT_ID`` fallback (AI Pro common project)

    Returns ``None`` when credentials are missing or refresh fails.
    """
    creds = load_credentials()
    if creds is None:
        return None
    if creds.is_expired():
        refreshed = refresh_access_token(creds)
        if refreshed is None:
            return None
        creds = refreshed
    override = os.environ.get("GEMINI_PRO_PROJECT_ID", "").strip()
    if override:
        return creds.access_token, override
    discovered = discover_project_id(creds.access_token)
    if discovered:
        return creds.access_token, discovered
    return creds.access_token, DEFAULT_PROJECT_ID
