# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""CLI handlers for the ``animaworks config`` subcommand."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from core.config.models import (
    AnimaModelConfig,
    AnimaWorksConfig,
    CredentialConfig,
    get_config_path,
    load_config,
    update_config,
)
from core.paths import get_animas_dir

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _flatten_dict(d: dict, prefix: str = "") -> list[tuple[str, Any]]:
    """Recursively flatten a nested dict to dot-notation key-value pairs."""
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, full_key))
        else:
            items.append((full_key, v))
    return items


def _mask_secret(key: str, value: Any) -> str:
    """Mask API key values, showing only the first 8 characters.

    If *key* ends with ``api_key`` and *value* is a non-empty string, return
    the first 8 characters followed by ``...``.  Otherwise return ``str(value)``.
    """
    if key.endswith("api_key") and isinstance(value, str) and value:
        return value[:8] + "..."
    return str(value)


def _coerce_value(value: str) -> Any:
    """Coerce a CLI string value to the appropriate Python type.

    Conversion order:
    - ``"null"`` / ``"none"`` (case-insensitive) -> ``None``
    - ``"true"`` / ``"false"`` (case-insensitive) -> ``bool``
    - Integer literal -> ``int``
    - Float literal -> ``float``
    - Otherwise -> ``str``
    """
    lower = value.lower()
    if lower in ("null", "none"):
        return None
    if lower == "true":
        return True
    if lower == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _set_nested(d: dict, keys: list[str], value: Any) -> None:
    """Set a value in a nested dict by key path, creating intermediate dicts."""
    for key in keys[:-1]:
        if key not in d or not isinstance(d[key], dict):
            d[key] = {}
        d = d[key]
    d[keys[-1]] = value


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_config_dispatch(args: argparse.Namespace) -> None:
    """Entry point for ``animaworks config``.

    If ``--interactive`` is set, launch the interactive wizard.
    Otherwise, if no subcommand was given, print the help text.
    """
    from core.infra.runtime_init import ensure_runtime_dir

    ensure_runtime_dir()

    if getattr(args, "interactive", False):
        _interactive_setup()
        return

    if not getattr(args, "config_command", None):
        # No subcommand provided -- print help.
        args.config_parser.print_help()
        return


def cmd_config_get(args: argparse.Namespace) -> None:
    """Print a single configuration value identified by a dot-notation key."""
    from core.infra.runtime_init import ensure_runtime_dir

    ensure_runtime_dir()

    config = load_config()
    data = config.model_dump()

    key: str = args.key
    show_secrets: bool = getattr(args, "show_secrets", False)

    current: Any = data
    for part in key.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            print(f"Error: key '{key}' not found in configuration", file=sys.stderr)
            sys.exit(1)

    display = current if show_secrets else _mask_secret(key, current)
    print(display)


def cmd_config_set(args: argparse.Namespace) -> None:
    """Set a configuration value identified by a dot-notation key."""
    from core.infra.runtime_init import ensure_runtime_dir

    ensure_runtime_dir()

    key: str = args.key
    raw_value: str = args.value
    coerced = _coerce_value(raw_value)

    parts = key.split(".")

    _MODEL_FIELDS = {
        "model",
        "fallback_model",
        "max_tokens",
        "credential",
        "context_threshold",
        "context_absolute_ceiling",
        "task_compaction_tokens",
        "task_compaction_max",
        "max_session_age_hours",
        "conversation_history_threshold",
        "execution_mode",
        "thinking",
    }
    if len(parts) >= 3 and parts[0] == "animas" and parts[2] in _MODEL_FIELDS:
        anima_name = parts[1]
        field = parts[2]
        print(
            f"Warning: 'animas.{anima_name}.{field}' は非推奨です。\n"
            f"  status.json に書き込みます。今後は 'animaworks anima set-model' を使用してください。",
            file=sys.stderr,
        )
        # Redirect to status.json (SSoT)
        anima_dir = get_animas_dir() / anima_name
        from core.platform.status_store import update_status

        update_status(anima_dir, lambda status: status.__setitem__(field, coerced))
        print(f"Set {anima_name}/status.json {field} = {_mask_secret(key, coerced)}")
        return

    def set_config_value(config: AnimaWorksConfig) -> AnimaWorksConfig:
        data = config.model_dump()
        # Auto-create scaffold for new anima entries (e.g. "animas.newperson.model")
        if len(parts) >= 3 and parts[0] == "animas":
            anima_name = parts[1]
            if anima_name not in data.get("animas", {}):
                data.setdefault("animas", {})[anima_name] = AnimaModelConfig().model_dump()

        # Auto-create scaffold for new credential entries
        if len(parts) >= 3 and parts[0] == "credentials":
            cred_name = parts[1]
            if cred_name not in data.get("credentials", {}):
                data.setdefault("credentials", {})[cred_name] = CredentialConfig().model_dump()

        _set_nested(data, parts, coerced)
        return AnimaWorksConfig.model_validate(data)

    update_config(set_config_value)

    display_value = _mask_secret(key, coerced)
    print(f"Set {key} = {display_value}")


def cmd_config_list(args: argparse.Namespace) -> None:
    """List configuration values as flat dot-notation key = value pairs."""
    from core.infra.runtime_init import ensure_runtime_dir

    ensure_runtime_dir()

    config = load_config()
    data = config.model_dump()

    section: str | None = getattr(args, "section", None)
    show_secrets: bool = getattr(args, "show_secrets", False)

    flat = _flatten_dict(data)

    if section:
        flat = [(k, v) for k, v in flat if k.startswith(section)]

    for k, v in flat:
        display = v if show_secrets else _mask_secret(k, v)
        print(f"{k} = {display}")


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------


def _interactive_setup() -> None:
    """Interactive configuration wizard driven by ``input()``."""
    from core.infra.runtime_init import ensure_runtime_dir

    ensure_runtime_dir()

    config_path = get_config_path()
    config = load_config(config_path) if config_path.is_file() else AnimaWorksConfig()
    original_credentials = dict(config.credentials)
    credentials: dict[str, CredentialConfig] = dict(config.credentials)

    # Step 1: Set up the default (anthropic) credential
    print("=== AnimaWorks Configuration Wizard ===")
    print()
    print("Step 1: Credential setup")
    print("-" * 40)

    default_cred = credentials.get("anthropic", CredentialConfig())
    api_key = input(
        f"Anthropic API key [{_mask_secret('api_key', default_cred.api_key) if default_cred.api_key else '(not set)'}]: "
    ).strip()
    if api_key:
        default_cred.api_key = api_key

    base_url = input(f"Base URL [{default_cred.base_url or '(default)'}]: ").strip()
    if base_url:
        default_cred.base_url = base_url if base_url.lower() not in ("none", "") else None

    credentials["anthropic"] = default_cred

    # Step 2: Additional credentials
    print()
    print("Step 2: Additional credentials")
    print("-" * 40)

    while True:
        add_more = input("Add another credential? [y/N]: ").strip().lower()
        if add_more != "y":
            break

        cred_name = input("  Credential name (e.g. ollama, openai): ").strip()
        if not cred_name:
            continue
        cred_api_key = input(f"  API key for '{cred_name}': ").strip()
        cred_base_url = input(f"  Base URL for '{cred_name}' [(default)]: ").strip()

        credentials[cred_name] = CredentialConfig(
            api_key=cred_api_key,
            base_url=cred_base_url if cred_base_url else None,
        )

    credential_updates = {
        name: credential
        for name, credential in credentials.items()
        if name not in original_credentials or credential != original_credentials[name]
    }

    # Step 3: Anima configuration
    print()
    print("Step 3: Anima configuration")
    print("-" * 40)

    animas_dir = get_animas_dir()
    detected_animas: list[str] = []
    if animas_dir.is_dir():
        detected_animas = sorted(d.name for d in animas_dir.iterdir() if d.is_dir())

    cred_names = list(credentials.keys())

    status_updates: dict[str, dict[str, str]] = {}
    from core.platform.status_store import read_status, update_status

    for anima_name in detected_animas:
        print(f"\n  Anima: {anima_name}")
        anima_dir = animas_dir / anima_name
        status_data = read_status(anima_dir)
        current_model = status_data.get("model", "") or ""
        current_cred = status_data.get("credential", "") or ""

        model = input(f"    Model [{current_model or '(use default)'}]: ").strip()
        if cred_names:
            print(f"    Available credentials: {', '.join(cred_names)}")
        cred = input(f"    Credential [{current_cred or '(use default)'}]: ").strip()

        updates = {}
        if model:
            updates["model"] = model
        if cred:
            updates["credential"] = cred
        if updates:
            status_updates[anima_name] = updates

    # Step 4: Save
    print()

    def save_wizard_changes(current: AnimaWorksConfig) -> None:
        current.credentials.update(credential_updates)
        for anima_name in detected_animas:
            current.animas.setdefault(anima_name, AnimaModelConfig())

    update_config(save_wizard_changes)
    for anima_name, updates in status_updates.items():
        update_status(animas_dir / anima_name, lambda status, values=updates: status.update(values))
    print(f"Configuration saved to {get_config_path()}")


# ---------------------------------------------------------------------------
# Export sections
# ---------------------------------------------------------------------------
