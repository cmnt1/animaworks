# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI handlers and interactive wizard for ``animaworks config``."""

from __future__ import annotations

import argparse
import sys

from core.config.models import AnimaWorksConfig, CredentialConfig, get_config_path, load_config
from core.config.ops import (
    _coerce_value,
    _mask_secret,
    get_config_value,
    legacy_model_status_target,
    list_config_values,
    save_config_wizard,
    set_config_value,
)
from core.i18n import t
from core.paths import get_animas_dir
from core.platform.status_store import read_status


def cmd_config_dispatch(args: argparse.Namespace) -> None:
    """Entry point for ``animaworks config``."""
    from core.infra.runtime_init import ensure_runtime_dir

    ensure_runtime_dir()

    if getattr(args, "interactive", False):
        _interactive_setup(args)
        return

    if not getattr(args, "config_command", None):
        args.config_parser.print_help()


def cmd_config_get(args: argparse.Namespace) -> None:
    """Print a configuration value identified by a dot-notation key."""
    from core.infra.runtime_init import ensure_runtime_dir

    ensure_runtime_dir()

    key: str = args.key
    show_secrets: bool = getattr(args, "show_secrets", False)
    try:
        value = get_config_value(key)
    except KeyError:
        print(f"Error: key '{key}' not found in configuration", file=sys.stderr)
        sys.exit(1)

    display = value if show_secrets else _mask_secret(key, value)
    print(display)


def cmd_config_set(args: argparse.Namespace) -> None:
    """Set a configuration value identified by a dot-notation key."""
    from core.infra.runtime_init import ensure_runtime_dir

    ensure_runtime_dir()

    key: str = args.key
    value = _coerce_value(args.value)
    target = legacy_model_status_target(key)
    if target is not None:
        anima_name, status_field = target
        if status_field == "heartbeat_interval_minutes":
            print(t("config.status_heartbeat_override", anima=anima_name, field=status_field), file=sys.stderr)
        elif status_field in {"supervisor", "speciality"}:
            print(t("config.status_org_setting", anima=anima_name, field=status_field), file=sys.stderr)
        else:
            print(
                t("config.status_field_deprecated", path=f"animas.{anima_name}.{status_field}"),
                file=sys.stderr,
            )

    from core.paths import get_data_dir

    if (get_data_dir() / "server.pid").exists():
        try:
            from cli._gateway import gateway_request

            response = gateway_request(
                args,
                "PUT",
                "/api/system/config/value",
                json={"key": key, "value": value},
                timeout=30.0,
                raw_response=True,
            )
            response.raise_for_status()
        except Exception as exc:
            print(f"Error: Failed to update config through running server: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        set_config_value(key, value)
    if target is not None:
        anima_name, status_field = target
        print(f"Set {anima_name}/status.json {status_field} = {_mask_secret(key, value)}")
        return

    print(f"Set {key} = {_mask_secret(key, value)}")


def cmd_config_list(args: argparse.Namespace) -> None:
    """List configuration values as flat dot-notation key-value pairs."""
    from core.infra.runtime_init import ensure_runtime_dir

    ensure_runtime_dir()

    show_secrets: bool = getattr(args, "show_secrets", False)
    for key, value in list_config_values(getattr(args, "section", None)):
        display = value if show_secrets else _mask_secret(key, value)
        print(f"{key} = {display}")


def _interactive_setup(args: argparse.Namespace | None = None) -> None:
    """Run the interactive configuration wizard."""
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
        detected_animas = sorted(directory.name for directory in animas_dir.iterdir() if directory.is_dir())

    credential_names = list(credentials.keys())
    status_updates: dict[str, dict[str, str]] = {}

    for anima_name in detected_animas:
        print(f"\n  Anima: {anima_name}")
        anima_dir = animas_dir / anima_name
        status_data = read_status(anima_dir)
        current_model = status_data.get("model", "") or ""
        current_credential = status_data.get("credential", "") or ""

        model = input(f"    Model [{current_model or '(use default)'}]: ").strip()
        if credential_names:
            print(f"    Available credentials: {', '.join(credential_names)}")
        credential = input(f"    Credential [{current_credential or '(use default)'}]: ").strip()

        updates = {}
        if model:
            updates["model"] = model
        if credential:
            updates["credential"] = credential
        if updates:
            status_updates[anima_name] = updates

    # Step 4: Save
    print()
    from core.paths import get_data_dir

    if (get_data_dir() / "server.pid").exists():
        try:
            from cli._gateway import gateway_request

            response = gateway_request(
                args or argparse.Namespace(),
                "PUT",
                "/api/system/config/wizard",
                json={
                    "credentials": {
                        name: credential.model_dump(mode="json") for name, credential in credential_updates.items()
                    },
                    "anima_names": detected_animas,
                    "status_updates": status_updates,
                },
                timeout=30.0,
                raw_response=True,
            )
            response.raise_for_status()
        except Exception as exc:
            print(f"Error: Failed to save config through running server: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        save_config_wizard(credential_updates, detected_animas, status_updates, animas_dir)
    print(f"Configuration saved to {get_config_path()}")
