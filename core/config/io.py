# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Configuration I/O: singleton cache, load, and save."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config.schemas import AnimaWorksConfig
from core.exceptions import ConfigError

logger = logging.getLogger("animaworks.config")

# ---------------------------------------------------------------------------
# Singleton cache
# ---------------------------------------------------------------------------

_config: AnimaWorksConfig | None = None
_config_path: Path | None = None
_config_mtime: float = 0.0

# Guard so stale-activity-level repair runs at most once per process.
_stale_activity_level_checked: bool = False

# Low-value band that indicates the Governor previously wrote a throttled
# value into config.json (legacy behaviour, now deprecated).  The Governor
# itself is authoritative at runtime via ``usage_governor_state.json``.
_STALE_ACTIVITY_LOWER: int = 10
_STALE_ACTIVITY_UPPER: int = 90
_STALE_ACTIVITY_REPLACEMENT: int = 100


def invalidate_cache() -> None:
    """Reset the module-level singleton cache."""
    global _config, _config_path, _config_mtime, _stale_activity_level_checked
    _config = None
    _config_path = None
    _config_mtime = 0.0
    _stale_activity_level_checked = False


def _read_governor_activity_level(data_dir: Path) -> int | None:
    """Return ``governor_activity_level`` from usage_governor_state.json, or None."""
    state_path = data_dir / "usage_governor_state.json"
    if not state_path.is_file():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        val = data.get("governor_activity_level")
        if isinstance(val, (int, float)):
            return int(val)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return None


def _maybe_repair_stale_activity_level(
    config: AnimaWorksConfig,
    config_path: Path,
    raw_data: dict[str, Any],
) -> AnimaWorksConfig:
    """Detect and repair a stale low ``activity_level`` in config.json.

    Historically the UsageGovernor wrote its computed level back into
    ``config.json``.  With the Governor now authoritative via
    ``usage_governor_state.json``, a stuck low value (e.g. ``20``) masks the
    Governor's healthier value through ``min(config, governor)`` arithmetic.
    When the Governor is currently healthy and the config value sits in the
    throttled band, rewrite it to 100 and leave a NOTICE audit trail.
    """
    global _stale_activity_level_checked

    if _stale_activity_level_checked:
        return config
    _stale_activity_level_checked = True

    if "activity_level" not in raw_data:
        return config

    current = config.activity_level
    if not (_STALE_ACTIVITY_LOWER <= current <= _STALE_ACTIVITY_UPPER):
        return config

    data_dir = config_path.parent
    governor_level = _read_governor_activity_level(data_dir)
    if governor_level is None or governor_level <= current:
        return config

    logger.warning(
        "NOTICE: stale activity_level=%d in %s (Governor currently at %d); "
        "rewriting to %d. Governor is authoritative at runtime.",
        current,
        config_path,
        governor_level,
        _STALE_ACTIVITY_REPLACEMENT,
    )

    try:
        run_dir = data_dir / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        audit_path = run_dir / "activity_level_audit.log"
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        audit_line = (
            f"{timestamp} NOTICE stale_activity_level_repair "
            f"before={current} after={_STALE_ACTIVITY_REPLACEMENT} "
            f"governor={governor_level} path={config_path}\n"
        )
        with audit_path.open("a", encoding="utf-8") as fh:
            fh.write(audit_line)
    except OSError as exc:
        logger.debug("Failed to write activity_level audit: %s", exc)

    config.activity_level = _STALE_ACTIVITY_REPLACEMENT
    try:
        save_config(config, config_path)
    except Exception as exc:  # noqa: BLE001 - best-effort repair
        logger.warning("Failed to persist repaired activity_level: %s", exc)

    return config


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def get_config_path(data_dir: Path | None = None) -> Path:
    """Return the path to config.json inside *data_dir*.

    If *data_dir* is not given, it is resolved via ``core.paths.get_data_dir``
    (imported lazily to avoid circular imports).
    """
    if data_dir is None:
        from core.paths import get_data_dir

        data_dir = get_data_dir()
    return data_dir / "config.json"


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------


def load_config(path: Path | None = None) -> AnimaWorksConfig:
    """Load configuration from disk, returning cached instance when possible.

    If *path* is ``None``, :func:`get_config_path` determines the location.
    When the file does not exist the default configuration is returned.

    The cache is automatically invalidated when the file's mtime changes,
    so external edits (org_sync, manual changes) are picked up without
    requiring a server restart.
    """
    global _config, _config_path, _config_mtime

    if path is None:
        path = get_config_path()

    # Check whether the on-disk file has been modified since last load.
    if _config is not None and _config_path == path:
        try:
            disk_mtime = path.stat().st_mtime
        except OSError:
            disk_mtime = 0.0
        if disk_mtime == _config_mtime:
            return _config
        logger.debug("Config file changed on disk (mtime %.3f → %.3f); reloading", _config_mtime, disk_mtime)

    if path.is_file():
        logger.debug("Loading config from %s", path)
        try:
            raw_text = path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(raw_text)
            config = AnimaWorksConfig.model_validate(data)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse %s: %s", path, exc)
            raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
        except ConfigError:
            raise
        except Exception as exc:
            logger.error("Failed to load config from %s: %s", path, exc)
            raise ConfigError(f"Failed to load config from {path}: {exc}") from exc
        config = _maybe_repair_stale_activity_level(config, path, data)
    else:
        logger.info("Config file not found at %s; using defaults", path)
        config = AnimaWorksConfig()

    _config = config
    _config_path = path
    try:
        _config_mtime = path.stat().st_mtime
    except OSError:
        _config_mtime = 0.0
    return config


def save_config(config: AnimaWorksConfig, path: Path | None = None) -> None:
    """Persist *config* to disk as pretty-printed JSON (mode 0o600).

    Updates the module-level singleton cache so subsequent :func:`load_config`
    calls return the freshly saved config.
    """
    global _config, _config_path, _config_mtime

    if path is None:
        path = get_config_path()

    path.parent.mkdir(parents=True, exist_ok=True)

    payload = config.model_dump(mode="json")
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    # Atomic write: write to a PID-unique sibling temp file then rename so
    # that concurrent writers (multiple anima workers) never clobber each
    # other's temp file.  Each process writes to .config.json.<PID>.tmp,
    # then renames it to config.json atomically.
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)

    logger.debug("Config saved to %s", path)

    _config = config
    _config_path = path
    try:
        _config_mtime = path.stat().st_mtime
    except OSError:
        _config_mtime = 0.0


__all__ = [
    "get_config_path",
    "invalidate_cache",
    "load_config",
    "save_config",
]
