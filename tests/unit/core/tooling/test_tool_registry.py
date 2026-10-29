from __future__ import annotations

from unittest.mock import patch

from core.tooling.policy import registry


def test_load_tool_module_uses_the_canonical_registry() -> None:
    with (
        patch.dict(registry.TOOL_MODULES, {"example": "example.tool"}, clear=True),
        patch("importlib.import_module", return_value=object()) as import_module,
    ):
        module = registry.load_tool_module("example")

    assert module is import_module.return_value
    import_module.assert_called_once_with("example.tool")


def test_discover_core_tools_omits_private_modules() -> None:
    discovered = registry.discover_core_tools()

    assert "_anima_icon_url" not in discovered
    assert discovered["web_search"] == "core.integrations.web_search"
