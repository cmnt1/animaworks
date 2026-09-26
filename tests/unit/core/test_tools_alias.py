"""The legacy ``core.tools`` package name must keep resolving to ``core.integrations``."""

from __future__ import annotations

import importlib


def test_submodule_alias_is_same_object() -> None:
    import core.tools._base as old_base

    import core.integrations._base as new_base

    assert old_base is new_base


def test_nested_submodule_alias() -> None:
    old = importlib.import_module("core.tools.image")
    new = importlib.import_module("core.integrations.image")
    assert old is new


def test_patch_through_alias_hits_real_module(monkeypatch) -> None:
    import core.integrations._base as base

    monkeypatch.setattr("core.tools._base._lookup_vault_credential", lambda *a, **k: "patched")
    assert base._lookup_vault_credential("x") == "patched"


def test_cli_dispatch_reexported() -> None:
    import core.integrations
    import core.tools

    assert core.tools.cli_dispatch is core.integrations.cli_dispatch
    assert callable(core.tools.cli_dispatch)
    assert core.tools.TOOL_MODULES is core.integrations.TOOL_MODULES
