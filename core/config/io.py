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
from core.config.vault import resolve_vault_references
from core.exceptions import ConfigError

logger = logging.getLogger("animaworks.config")

# ---------------------------------------------------------------------------
# Singleton cache
# ---------------------------------------------------------------------------

_config: AnimaWorksConfig | None = None
_config_path: Path | None = None
_config_mtime: float = 0.0
_config_vault_values: dict[tuple[str | int, ...], Any] = {}
_promotion_flag_warned: bool = False

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
    global \
        _config, \
        _config_path, \
        _config_mtime, \
        _config_vault_values, \
        _promotion_flag_warned, \
        _stale_activity_level_checked
    _config = None
    _config_path = None
    _config_mtime = 0.0
    _config_vault_values = {}
    _promotion_flag_warned = False
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


def _warn_deprecated_promotion_flags(config: AnimaWorksConfig) -> None:
    """Warn once when deprecated no-op promotion flags are set to non-defaults.

    ``auto_activate`` / ``require_approval_on_warn`` are ignored: skill
    promotion always writes to quarantine and requires human approval. The
    fields are kept in the schema only so existing config.json files validate.
    """
    global _promotion_flag_warned
    if _promotion_flag_warned:
        return
    pcfg = config.skills.promotion
    if pcfg.auto_activate or not pcfg.require_approval_on_warn:
        logger.warning(
            "config skills.promotion.auto_activate / require_approval_on_warn are "
            "deprecated no-ops and are ignored; skill promotion always requires "
            "human approval (quarantine default). Remove them from config.json.",
        )
        _promotion_flag_warned = True


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
    global _config, _config_path, _config_mtime, _config_vault_values

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
            raw_data: dict[str, Any] = json.loads(raw_text)
            data = resolve_vault_references(raw_data, path.parent)
            config = AnimaWorksConfig.model_validate(data)
            _config_vault_values = _collect_vault_reference_values(raw_data, data)
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
        _config_vault_values = {}

    _config = config
    _config_path = path
    try:
        _config_mtime = path.stat().st_mtime
    except OSError:
        _config_mtime = 0.0
    _warn_deprecated_promotion_flags(config)
    return config


def save_config(config: AnimaWorksConfig, path: Path | None = None) -> None:
    """Persist *config* to disk as pretty-printed JSON (mode 0o600).

    Updates the module-level singleton cache so subsequent :func:`load_config`
    calls return the freshly saved config.
    """
    global _config, _config_path, _config_mtime, _config_vault_values

    if path is None:
        path = get_config_path()

    path.parent.mkdir(parents=True, exist_ok=True)

    payload = config.model_dump(mode="json")
    # Loading resolves vault references for runtime use.  Preserve references
    # already present on disk when saving so a routine config update cannot
    # accidentally write the resolved secret back as plaintext.
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            payload, vault_updates = _preserve_vault_references(
                payload,
                existing,
                loaded_values=_config_vault_values if _config_path == path else {},
            )
            if vault_updates:
                _apply_vault_updates(path.parent, vault_updates)
        except (json.JSONDecodeError, OSError):
            pass
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
    _config_vault_values = _collect_vault_reference_values(payload, config.model_dump(mode="json"))


def _collect_vault_reference_values(
    references: Any,
    resolved: Any,
    path: tuple[str | int, ...] = (),
) -> dict[tuple[str | int, ...], Any]:
    """Collect resolved values corresponding to vault reference leaves."""
    if isinstance(references, dict) and set(references) == {"$vault"}:
        return {path: resolved}
    found: dict[tuple[str | int, ...], Any] = {}
    if isinstance(references, dict) and isinstance(resolved, dict):
        for key, item in references.items():
            if key in resolved:
                found.update(_collect_vault_reference_values(item, resolved[key], (*path, key)))
    elif isinstance(references, list) and isinstance(resolved, list):
        for index, item in enumerate(references):
            if index < len(resolved):
                found.update(_collect_vault_reference_values(item, resolved[index], (*path, index)))
    return found


def _preserve_vault_references(
    value: Any,
    existing: Any,
    *,
    loaded_values: dict[tuple[str | int, ...], Any],
    path: tuple[str | int, ...] = (),
) -> tuple[Any, dict[str, str]]:
    """Preserve reference leaves and identify intentional value changes."""
    if isinstance(existing, dict) and set(existing) == {"$vault"}:
        key = existing["$vault"]
        if isinstance(key, str) and key:
            updates: dict[str, str] = {}
            if path in loaded_values and value != loaded_values[path]:
                if not isinstance(value, str):
                    raise ConfigError(f"Value for vault key {key} must be a string")
                updates[key] = value
            return existing, updates
    if isinstance(value, dict) and isinstance(existing, dict):
        result: dict[str, Any] = {}
        updates: dict[str, str] = {}
        for key, item in value.items():
            result[key], child_updates = _preserve_vault_references(
                item,
                existing.get(key),
                loaded_values=loaded_values,
                path=(*path, key),
            )
            for vault_key, vault_value in child_updates.items():
                if vault_key in updates and updates[vault_key] != vault_value:
                    raise ConfigError(f"Conflicting updates for vault key: {vault_key}")
                updates[vault_key] = vault_value
        return result, updates
    if isinstance(value, list) and isinstance(existing, list):
        result_list: list[Any] = []
        updates = {}
        for index, item in enumerate(value):
            child, child_updates = _preserve_vault_references(
                item,
                existing[index] if index < len(existing) else None,
                loaded_values=loaded_values,
                path=(*path, index),
            )
            result_list.append(child)
            for vault_key, vault_value in child_updates.items():
                if vault_key in updates and updates[vault_key] != vault_value:
                    raise ConfigError(f"Conflicting updates for vault key: {vault_key}")
                updates[vault_key] = vault_value
        return result_list, updates
    return value, {}


def _apply_vault_updates(data_dir: Path, updates: dict[str, str]) -> None:
    """Atomically update changed values in the vault's shared section."""
    from core.config.vault import VaultManager

    vault = VaultManager(data_dir)
    data = vault.load_vault()
    shared = data.setdefault("shared", {})
    if not isinstance(shared, dict):
        raise ConfigError("vault.json shared section must be an object")
    for key, value in updates.items():
        shared[key] = vault.encrypt(value)
    vault.save_vault(data)


__all__ = [
    "get_config_path",
    "invalidate_cache",
    "load_config",
    "save_config",
]
