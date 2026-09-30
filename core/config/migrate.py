# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Migrate legacy permissions.md files to permissions.json."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from core.config.models import (
    CommandsPermission,
    ExternalToolsPermission,
    PermissionsConfig,
    ToolCreationPermission,
)

logger = logging.getLogger("animaworks.config_migrate")

# ── Permissions MD → JSON migration ──────────────────────────────────────────


def migrate_permissions_md_to_json(anima_dir: Path) -> PermissionsConfig:
    """Migrate permissions.md to permissions.json.

    Parses the MD file best-effort and creates a structured JSON.
    Falls back to open defaults for unparseable sections.
    Renames the old file to permissions.md.bak.
    """
    md_path = anima_dir / "permissions.md"
    json_path = anima_dir / "permissions.json"

    if not md_path.is_file():
        config = PermissionsConfig()
        _write_permissions_json(json_path, config)
        return config

    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Cannot read permissions.md at %s: %s", md_path, exc)
        config = PermissionsConfig()
        _write_permissions_json(json_path, config)
        return config

    file_roots = _extract_file_roots(text)
    commands = _extract_commands(text)
    external_tools = _extract_external_tools(text)
    tool_creation = _extract_tool_creation(text)

    config = PermissionsConfig(
        file_roots=file_roots,
        commands=commands,
        external_tools=external_tools,
        tool_creation=tool_creation,
    )

    _write_permissions_json(json_path, config)

    # Rename old file
    bak_path = md_path.with_suffix(".md.bak")
    try:
        md_path.rename(bak_path)
        logger.info("Migrated permissions.md → permissions.json for %s (backup: %s)", anima_dir.name, bak_path.name)
    except OSError as exc:
        logger.warning("Failed to rename permissions.md to .bak: %s", exc)

    return config


def _write_permissions_json(path: Path, config: PermissionsConfig) -> None:
    """Write PermissionsConfig as pretty-printed JSON."""
    import json as _json

    path.write_text(
        _json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _extract_file_roots(text: str) -> list[str]:
    """Extract file_roots from permissions.md text.

    If a file section exists but contains no absolute paths, returns ``[]``
    (anima_dir only — restrictive).  If no file section is found at all,
    returns ``["/"]`` (open default).
    """
    _HEADERS = ("ファイル操作", "読める場所", "File Operations", "Readable Locations")
    roots: list[str] = []
    found_section = False
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if any(h in stripped for h in _HEADERS):
            found_section = True
            in_section = True
            continue
        if in_section and stripped.startswith("#"):
            break
        if in_section and stripped.startswith("-"):
            item = stripped.lstrip("- ").split(":")[0].strip()
            if item.startswith("/"):
                roots.append(item)
    if roots:
        return roots
    if found_section:
        return []  # section exists but no paths → restrict to anima_dir
    return ["/"]  # no section at all → open default


def _extract_commands(text: str) -> CommandsPermission:
    """Extract command permissions from permissions.md text."""
    from core.config.models import CommandsPermission

    # Check for denied commands
    deny: list[str] = []
    in_denied = False
    for line in text.splitlines():
        stripped = line.strip()
        if "実行できないコマンド" in stripped or "Denied Commands" in stripped:
            in_denied = True
            continue
        if in_denied and stripped.startswith("#"):
            break
        if in_denied and stripped:
            for part in stripped.lstrip("-* ").split(","):
                part = part.strip()
                if part:
                    deny.append(part)

    # Check for allowed commands
    allow: list[str] = []
    in_allowed = False
    for line in text.splitlines():
        stripped = line.strip()
        if any(
            h in stripped for h in ("コマンド実行", "実行できるコマンド", "Executable Commands", "Command Execution")
        ):
            in_allowed = True
            continue
        if in_allowed and stripped.startswith("#"):
            break
        if in_allowed and stripped.startswith("-"):
            item = stripped.lstrip("- ").split(":")[0].strip()
            if item and not item.startswith("/"):
                allow.append(item)

    if allow:
        return CommandsPermission(allow_all=False, allow=allow, deny=deny)
    return CommandsPermission(allow_all=True, deny=deny)


def _extract_external_tools(text: str) -> ExternalToolsPermission:
    """Extract external tool permissions from permissions.md text."""
    from core.config.models import ExternalToolsPermission

    if "外部ツール" not in text and "External Tools" not in text:
        return ExternalToolsPermission(allow_all=True)

    _ALLOW_RE = re.compile(
        r"[-*]?\s*(\w+)\s*:\s*(OK|yes|enabled|true|全権限|読み取り.*)\s*$",
        re.IGNORECASE,
    )
    _ALL_RE = re.compile(r"[-*]?\s*all\s*:\s*(OK|yes|enabled|true)\s*$", re.IGNORECASE)
    _DENY_RE = re.compile(r"[-*]?\s*(\w+)\s*:\s*(no|deny|disabled|false)\s*$", re.IGNORECASE)

    has_all = False
    allow: list[str] = []
    deny: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if _ALL_RE.match(stripped):
            has_all = True
            continue
        m_deny = _DENY_RE.match(stripped)
        if m_deny:
            deny.append(m_deny.group(1))
            continue
        m_allow = _ALLOW_RE.match(stripped)
        if m_allow:
            allow.append(m_allow.group(1))

    if has_all:
        return ExternalToolsPermission(allow_all=True, allow=allow, deny=deny)
    if allow:
        return ExternalToolsPermission(allow_all=False, allow=allow, deny=deny)
    return ExternalToolsPermission(allow_all=True, deny=deny)


def _extract_tool_creation(text: str) -> ToolCreationPermission:
    """Extract tool creation permissions from permissions.md text."""
    from core.config.models import ToolCreationPermission

    personal = True
    shared = False
    kw_patterns = ("ツール作成", "Tool Creation")
    if not any(kw in text for kw in kw_patterns):
        return ToolCreationPermission(personal=personal, shared=shared)

    _perm_re = re.compile(
        r"[-*]?\s*(個人ツール|personal|共有ツール|shared)\s*:\s*(OK|yes|enabled|true|no|deny|disabled|false)\s*$",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        m = _perm_re.match(line.strip())
        if m:
            key = m.group(1).lower()
            val = m.group(2).lower() in ("ok", "yes", "enabled", "true")
            if key in ("個人ツール", "personal"):
                personal = val
            elif key in ("共有ツール", "shared"):
                shared = val

    return ToolCreationPermission(personal=personal, shared=shared)
