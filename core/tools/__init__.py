from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Compatibility entry point for the old ``core.tools`` package name.

The external-tool integrations now live in :mod:`core.integrations`. This
alias stays for runtime ``common_tools/`` and ``common_skills/`` files that
import ``core.tools._base`` and for ``animaworks-tool`` console scripts
installed by older releases (``core.tools:cli_dispatch``). New code should
import from ``core.integrations``.

``import core.tools.<sub>`` resolves to the very same module object as
``core.integrations.<sub>``, so patches and module state are shared.
"""

import importlib
import importlib.abc
import importlib.util
import sys
from types import ModuleType

from core.integrations import *  # noqa: F403
from core.integrations import (  # noqa: F401
    TOOL_MODULES,
    cli_dispatch,
    discover_common_tools,
    discover_core_tools,
    discover_personal_tools,
)

_OLD = __name__
_NEW = "core.integrations"


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, target: str) -> None:
        self._target = target

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        return importlib.import_module(self._target)

    def exec_module(self, module: ModuleType) -> None:
        return None


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self, fullname: str, path: object = None, target: object = None
    ) -> importlib.machinery.ModuleSpec | None:
        if not fullname.startswith(_OLD + "."):
            return None
        return importlib.util.spec_from_loader(fullname, _AliasLoader(_NEW + fullname[len(_OLD) :]))


if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _AliasFinder())
