from __future__ import annotations

"""Canonical registry and loader for built-in external tool modules."""

import importlib
import logging
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

logger = logging.getLogger(__name__)

# These tools are only exposed in an isolated runtime. Keep them out of the
# default registry so host-side tool lists and permissions remain unchanged.
_ENCLAVE_ONLY_TOOL_MODULES = {
    "enclave_records": "core.integrations.enclave_records",
    "enclave_sql": "core.integrations.enclave_sql",
}


def discover_core_tools() -> dict[str, str]:
    """Scan ``core/integrations`` for generally available public tool modules."""
    tools_dir = Path(__file__).resolve().parents[2] / "integrations"
    return {
        path.stem: f"core.integrations.{path.stem}"
        for path in sorted(tools_dir.glob("*.py"))
        if not path.name.startswith("_") and path.stem not in _ENCLAVE_ONLY_TOOL_MODULES
    }


TOOL_MODULES = discover_core_tools()


def get_tool_modules(*, enclave_enabled: bool | None = None) -> dict[str, str]:
    """Return tools available in the current runtime.

    ``enclave_records`` is intentionally absent from :data:`TOOL_MODULES` so
    it does not appear on the host. It is added only when enclave mode is
    enabled; an explicit argument is available to callers that already know
    the mode and to keep the selection easy to test.
    """
    modules = dict(TOOL_MODULES)
    if enclave_enabled is None:
        try:
            from core.config import load_config

            enclave_enabled = load_config().enclave.enabled
        except Exception:
            logger.debug("Could not load enclave mode for tool discovery", exc_info=True)
            enclave_enabled = False

    if enclave_enabled:
        modules.update(_ENCLAVE_ONLY_TOOL_MODULES)
    return modules


def load_tool_module(
    tool_name: str,
    registry: Mapping[str, str] | None = None,
) -> ModuleType:
    """Import a built-in tool module from its registry entry."""
    modules = get_tool_modules() if registry is None else registry
    return importlib.import_module(modules[tool_name])
