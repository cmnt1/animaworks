# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Executable pins for deliberate divergences from upstream.

These are not behaviour tests: they exist so that an upstream merge that
silently reverts a fork decision fails loudly instead of shipping.  Each test
names the entry in ``docs/fork-policy.md`` it enforces.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES = _REPO_ROOT / "templates"
_LOCALES = ("en", "ja", "ko")

# Every role template must carry the Notion opt-out.
_NOTION_DENIED_ROLE_DIRS = ("administration", "engineer", "general", "manager", "ops", "researcher", "writer")


def _permission_files() -> list[Path]:
    files: list[Path] = []
    for locale in _LOCALES:
        for role in _NOTION_DENIED_ROLE_DIRS:
            path = _TEMPLATES / locale / "roles" / role / "permissions.json"
            if path.is_file():
                files.append(path)
    return files


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestNotionDisabledByDefault:
    """docs/fork-policy.md #2 — Notion access was removed in fork 745ab66b."""

    def test_permission_files_are_discovered(self) -> None:
        # Guard against the glob silently matching nothing after a restructure.
        assert len(_permission_files()) >= len(_NOTION_DENIED_ROLE_DIRS)

    @pytest.mark.parametrize("path", _permission_files(), ids=lambda p: f"{p.parent.parent.parent.name}/{p.parent.name}")
    def test_notion_stays_denied(self, path: Path) -> None:
        external = _load(path).get("external_tools", {})
        deny = set(external.get("deny", []))
        allow = set(external.get("allow", []))

        assert "notion" in deny, (
            f"{path.relative_to(_REPO_ROOT)} dropped the Notion opt-out. "
            "Upstream ships Notion enabled; this fork moved the workflow to Obsidian. "
            "See docs/fork-policy.md #2."
        )
        # `deny` wins in core/tooling/permissions.py, so an `allow` entry would
        # be inert — but leaving it in place misrepresents the policy.
        assert "notion" not in allow, (
            f"{path.relative_to(_REPO_ROOT)} re-added Notion to external_tools.allow. "
            "See docs/fork-policy.md #2."
        )


class TestAnimasPageIsFirstClass:
    """docs/fork-policy.md #3 — upstream folds list views into the org chart."""

    def test_router_keeps_fork_redirects(self) -> None:
        router = (_REPO_ROOT / "server" / "static" / "modules" / "router.js").read_text(encoding="utf-8")

        assert '"/processes": "#/animas"' in router, (
            "/processes must redirect to our Anima management page, not upstream's '#/'. "
            "See docs/fork-policy.md #3."
        )
        assert '"/server": "#/scheduler"' in router, (
            "/server must redirect to our scheduler page, not upstream's '#/'. See docs/fork-policy.md #3."
        )
        assert 'routes["/animas"]' in router, "The /animas route must stay registered. See docs/fork-policy.md #3."

    def test_sidebar_keeps_fork_entries(self) -> None:
        index_html = (_REPO_ROOT / "server" / "static" / "index.html").read_text(encoding="utf-8")

        assert 'data-route="/animas"' in index_html, (
            "The Anima Management nav entry must stay. See docs/fork-policy.md #3."
        )
        assert 'data-route="/sns-search"' in index_html, (
            "The fork-only SNS Search nav entry must stay. See docs/fork-policy.md #3."
        )


class TestProcessModelDefault:
    """docs/fork-policy.md #1 — upstream defaults this to phase3."""

    def test_missing_status_resolves_to_legacy(self, tmp_path: Path) -> None:
        from core.config.resolver import resolve_process_model_config

        resolved = resolve_process_model_config(tmp_path / "anima")

        assert resolved.valid
        assert resolved.process_model == "legacy", (
            "Syncing upstream must not switch a running fleet's process topology. See docs/fork-policy.md #1."
        )


class TestLivenessProbeIsWindowsSafe:
    """docs/fork-policy.md #4 — os.kill(pid, 0) terminates processes on Windows."""

    def test_processing_lease_does_not_probe_with_os_kill(self) -> None:
        path = _REPO_ROOT / "core" / "platform" / "processing_lease.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        # AST rather than a substring scan so prose explaining *why* we avoid
        # os.kill does not trip the check.
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "kill"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "os"
        ]

        assert not calls, (
            "Liveness probing must use the psutil-backed is_process_alive: on Windows "
            "os.kill maps to TerminateProcess and would kill the process being checked. "
            "See docs/fork-policy.md #4."
        )
