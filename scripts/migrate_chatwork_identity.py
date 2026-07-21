#!/usr/bin/env python3
from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Migrate legacy Chatwork credentials/cache/config to the identity model.

Idempotent deploy-time helper. Never prints token values.

Usage::

    python scripts/migrate_chatwork_identity.py            # dry-run (default)
    python scripts/migrate_chatwork_identity.py --apply
    python scripts/migrate_chatwork_identity.py --apply --finalize
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

# Vault key renames (source → destination). Old keys are kept unless --finalize.
_VAULT_KEY_COPIES: tuple[tuple[str, str], ...] = (
    ("CHATWORK_API_TOKEN", "CHATWORK_API_TOKEN__owner"),
    ("CHATWORK_API_TOKEN_WRITE", "CHATWORK_API_TOKEN__kotoha"),
    ("CHATWORK_API_TOKEN_WRITE__mei", "CHATWORK_API_TOKEN__mei"),
)

_LEGACY_KEYS_TO_DELETE: tuple[str, ...] = (
    "CHATWORK_API_TOKEN",
    "CHATWORK_API_TOKEN_WRITE",
    "CHATWORK_API_TOKEN_WRITE__mei",
)

_DEFAULT_GRANTS: dict[str, dict[str, str]] = {
    "mei": {"owner": "read"},
    "aoi": {"haato_ai": "readwrite"},
}

_HAATO_TOKEN_REL = Path("credentials") / "hhc-chatwork-bot-token"


def _print(msg: str) -> None:
    print(msg)


def _vault_has(vault: Any, key: str) -> bool:
    return vault.get("shared", key) is not None


def step_vault_key_copies(*, vault: Any, data_dir: Path, apply: bool) -> None:
    """(a) Copy legacy vault keys to identity-style keys (no overwrite)."""
    for src, dst in _VAULT_KEY_COPIES:
        if _vault_has(vault, dst):
            _print(f"SKIP vault copy {src} → {dst}: destination already exists")
            continue
        value = vault.get("shared", src)
        if value is None:
            _print(f"SKIP vault copy {src} → {dst}: source key not found")
            continue
        if apply:
            vault.store("shared", dst, value)
            _print(f"APPLY vault copy {src} → {dst}")
        else:
            _print(f"DRY-RUN vault copy {src} → {dst}")

    # haato_ai bot token from file (if present and destination empty)
    haato_dst = "CHATWORK_API_TOKEN__haato_ai"
    if _vault_has(vault, haato_dst):
        _print(f"SKIP vault register {haato_dst}: destination already exists")
        return

    token_path = data_dir / _HAATO_TOKEN_REL
    if not token_path.is_file():
        _print(
            f"SKIP vault register {haato_dst}: "
            f"file not found ({_HAATO_TOKEN_REL.as_posix()})"
        )
        return

    try:
        raw = token_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        _print(f"SKIP vault register {haato_dst}: cannot read file ({exc})")
        return

    if not raw:
        _print(f"SKIP vault register {haato_dst}: file is empty")
        return

    if apply:
        vault.store("shared", haato_dst, raw)
        _print(f"APPLY vault register {haato_dst} from {_HAATO_TOKEN_REL.as_posix()}")
    else:
        _print(f"DRY-RUN vault register {haato_dst} from {_HAATO_TOKEN_REL.as_posix()}")


def step_config_grants(*, config_path: Path, apply: bool) -> None:
    """(b) Write default chatwork_tool.grants when unset."""
    if not config_path.is_file():
        if apply:
            payload = {"version": 1, "chatwork_tool": {"grants": _DEFAULT_GRANTS}}
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            _print(
                f"APPLY config.json: created with chatwork_tool.grants "
                f"defaults at {config_path}"
            )
        else:
            _print(
                f"DRY-RUN config.json: would create with chatwork_tool.grants "
                f"defaults at {config_path}"
            )
        return

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _print(f"SKIP config.json grants: cannot read/parse ({exc})")
        return

    if not isinstance(raw, dict):
        _print("SKIP config.json grants: root is not an object")
        return

    tool_cfg = raw.get("chatwork_tool")
    if isinstance(tool_cfg, dict):
        grants = tool_cfg.get("grants")
        if isinstance(grants, dict) and grants:
            _print("SKIP config.json grants: already configured")
            return

    if not apply:
        _print("DRY-RUN config.json: write default chatwork_tool.grants")
        return

    if not isinstance(tool_cfg, dict):
        raw["chatwork_tool"] = {"grants": dict(_DEFAULT_GRANTS)}
    else:
        tool_cfg["grants"] = dict(_DEFAULT_GRANTS)
        raw["chatwork_tool"] = tool_cfg

    config_path.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _print("APPLY config.json: wrote default chatwork_tool.grants")


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _fetch_account_id(token: str) -> str | None:
    """Call Chatwork /me; return account_id string or None on failure."""
    try:
        from core.tools._chatwork_client import ChatworkClient

        me = ChatworkClient(api_token=token).me()
    except Exception as exc:
        _print(f"SKIP cache migrate: Chatwork /me failed ({exc})")
        return None

    if not isinstance(me, dict):
        _print("SKIP cache migrate: /me response is not an object")
        return None
    account_id = me.get("account_id")
    if account_id in (None, ""):
        _print("SKIP cache migrate: /me returned no account_id")
        return None
    return str(account_id)


def step_cache_migrate(*, vault: Any, cache_dir: Path, apply: bool) -> None:
    """(c) Move legacy messages.db under account_id/ and update identity_map."""
    old_db = cache_dir / "messages.db"
    if not old_db.is_file():
        _print(f"SKIP cache migrate: no legacy DB at {old_db}")
        return

    owner_token = vault.get("shared", "CHATWORK_API_TOKEN__owner")
    if not owner_token:
        # After vault copies, dry-run may not have written yet — also check legacy
        owner_token = vault.get("shared", "CHATWORK_API_TOKEN")
    if not owner_token:
        _print(
            "SKIP cache migrate: CHATWORK_API_TOKEN__owner "
            "(and legacy CHATWORK_API_TOKEN) not in vault"
        )
        return

    if not apply:
        _print(
            f"DRY-RUN cache migrate: would call /me and move {old_db} "
            f"to {cache_dir}/<account_id>/messages.db and update identity_map.json"
        )
        return

    account_id = _fetch_account_id(owner_token)
    if account_id is None:
        return

    dest_dir = cache_dir / account_id
    dest_db = dest_dir / "messages.db"
    if dest_db.exists():
        _print(
            f"SKIP cache migrate: destination already exists at {dest_db} "
            f"(leaving legacy {old_db} in place)"
        )
        # Still ensure identity_map entry if missing.
    else:
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_db), str(dest_db))
        _print(f"APPLY cache migrate: moved {old_db} → {dest_db}")

    map_path = cache_dir / "identity_map.json"
    identity_map: dict[str, str] = {}
    if map_path.is_file():
        try:
            raw_map = json.loads(map_path.read_text(encoding="utf-8"))
            if isinstance(raw_map, dict):
                identity_map = {str(k): str(v) for k, v in raw_map.items()}
        except (OSError, json.JSONDecodeError):
            identity_map = {}

    fp = _token_fingerprint(owner_token)
    if identity_map.get(fp) == account_id:
        _print(f"SKIP identity_map: {fp} already maps to {account_id}")
    else:
        identity_map[fp] = account_id
        tmp = map_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(identity_map, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        tmp.replace(map_path)
        _print(f"APPLY identity_map: registered token fingerprint → {account_id}")


def step_finalize(*, vault: Any, apply: bool, finalize: bool) -> None:
    """(d) Optionally delete legacy vault keys after verification."""
    if not finalize:
        _print("SKIP finalize: pass --finalize to delete legacy vault keys")
        return

    for key in _LEGACY_KEYS_TO_DELETE:
        if not _vault_has(vault, key):
            _print(f"SKIP finalize delete {key}: not present")
            continue
        if apply:
            vault.delete("shared", key)
            _print(f"APPLY finalize delete {key}")
        else:
            _print(f"DRY-RUN finalize delete {key}")


def run_migration(
    *,
    data_dir: Path,
    cache_dir: Path | None = None,
    apply: bool = False,
    finalize: bool = False,
    vault: Any | None = None,
) -> int:
    """Execute migration steps. Returns process exit code (always 0 on soft skips)."""
    if vault is None:
        from core.config.vault import get_vault_manager

        vault = get_vault_manager(data_dir)

    if cache_dir is None:
        from core.tools._chatwork_cache import DEFAULT_CACHE_DIR

        cache_dir = DEFAULT_CACHE_DIR

    mode = "APPLY" if apply else "DRY-RUN"
    _print(f"=== migrate_chatwork_identity ({mode}) data_dir={data_dir} ===")

    step_vault_key_copies(vault=vault, data_dir=data_dir, apply=apply)
    step_config_grants(config_path=data_dir / "config.json", apply=apply)
    step_cache_migrate(vault=vault, cache_dir=cache_dir, apply=apply)
    step_finalize(vault=vault, apply=apply, finalize=finalize)

    _print("=== done ===")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate Chatwork vault keys, config grants, and message cache "
        "to the identity model (idempotent)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default is dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without writing (default)",
    )
    parser.add_argument(
        "--finalize",
        action="store_true",
        help="Also delete legacy vault keys after copies (use after verification)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Override data directory (default: core.paths.get_data_dir())",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Override Chatwork cache directory "
        "(default: core.tools._chatwork_cache.DEFAULT_CACHE_DIR)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    # --dry-run is the default; --apply wins when both are passed.
    apply = bool(args.apply)

    if args.data_dir is not None:
        data_dir = args.data_dir
    else:
        from core.paths import get_data_dir

        data_dir = get_data_dir()

    # When --data-dir is given, construct a dedicated VaultManager so we do not
    # pollute the process-wide singleton (important for tests and one-shot runs).
    vault = None
    if args.data_dir is not None:
        from core.config.vault import VaultManager

        vault = VaultManager(data_dir)

    return run_migration(
        data_dir=data_dir,
        cache_dir=args.cache_dir,
        apply=apply,
        finalize=bool(args.finalize),
        vault=vault,
    )


if __name__ == "__main__":
    raise SystemExit(main())
