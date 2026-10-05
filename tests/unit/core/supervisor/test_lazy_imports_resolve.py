"""Function-local imports are invisible to import-time tests; check them statically.

2026-09-02: task_runner.execute_task_contract imported sentinels that the
supervisor teardown had removed from pending_executor. Unit tests never
executed that function, so every TaskExec child died with ImportError in
production. This test resolves each function-local ``from core... import``
(and ``cli``/``server``) across the whole codebase against the real module,
so module moves cannot leave a stale lazy import behind.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
_PACKAGES = ("core", "cli", "server")


def _local_import_froms() -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for pkg in _PACKAGES:
        for path in sorted((_ROOT / pkg).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = str(path.relative_to(_ROOT))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                for sub in ast.walk(node):
                    if isinstance(sub, ast.ImportFrom) and sub.level == 0 and sub.module:
                        if sub.module.split(".")[0] in _PACKAGES:
                            found.extend((rel, sub.module, alias.name) for alias in sub.names)
                    elif isinstance(sub, ast.Import):
                        found.extend(
                            (rel, alias.name, "") for alias in sub.names if alias.name.split(".")[0] in _PACKAGES
                        )
    return sorted(set(found))


def _import(module: str):
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.split(".")[0] not in _PACKAGES:
            pytest.skip(f"optional dependency missing: {exc.name}")
        raise


@pytest.mark.parametrize(("filename", "module", "name"), _local_import_froms())
def test_function_local_import_resolves(filename: str, module: str, name: str) -> None:
    mod = _import(module)
    if not name or name == "*" or hasattr(mod, name):
        return
    # ``from pkg import submodule`` works even before the submodule is an attribute.
    _import(f"{module}.{name}")
