from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Secret-safe discovery of per-Anima Slack credential key names."""

import json
import os
import re
from pathlib import Path


def _object_keys(path: Path, *, nested: str | None = None) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
        # vault移行後の credentials.json は0バイト残骸のことがある。空は空ストア扱い。
        if not text.strip():
            return set()
        value = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid credential store {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in credential store {path}")
    if nested is not None:
        value = value.get(nested, {})
    return set(value) if isinstance(value, dict) else set()


def discover_slack_credential_candidates(
    data_dir: Path,
    source: str,
) -> list[dict[str, str]]:
    """Return source credential locations and key names, never values."""
    data_dir = Path(data_dir)
    wanted = {f"{base}__{source}" for base in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN")}
    found: set[tuple[str, str]] = set()

    vault_path = data_dir / "vault.json"
    if vault_path.is_file():
        keys = _object_keys(vault_path, nested="shared")
        found.update(("vault.json", key) for key in wanted if key in keys)

    credentials_path = data_dir / "shared" / "credentials.json"
    if credentials_path.is_file():
        keys = _object_keys(credentials_path)
        found.update(("shared/credentials.json", key) for key in wanted if key in keys)

    env_path = data_dir / ".env"
    if env_path.is_file():
        key_pattern = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
        try:
            with env_path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.lstrip().startswith("#"):
                        continue
                    match = key_pattern.match(line)
                    if match and match.group(1) in wanted:
                        found.add((".env", match.group(1)))
        except OSError as exc:
            raise ValueError(f"Could not inspect {env_path}: {exc}") from exc

    found.update(("environment", key) for key in wanted if key in os.environ)
    return [{"storage": storage, "key": key} for storage, key in sorted(found)]
