"""Mode Y (Antigravity CLI / agy) wiring tests.

Part A ships the executor and platform modules on a parallel branch.  These
tests pin the Part B wiring and use patches so they pass before that branch
lands.
"""

from __future__ import annotations

import json

from core.agent.executor_factory import ENGINE_ADAPTERS
from core.agent.priming import PrimingMixin
from core.config.model_catalog import _build_static_model_catalog, model_credential_available
from core.config.models import AnimaWorksConfig
from core.prompt.builder import _MCP_MODES as BUILDER_MCP_MODES
from core.prompt.builder import _host_tool_line
from core.tooling.policy.surface import _MCP_MODES as SURFACE_MCP_MODES


def test_y_engine_adapter_paths_are_pinned() -> None:
    adapter = ENGINE_ADAPTERS["y"]
    assert adapter.executor_path == "core.execution.engines.agy.executor:AgyCLIExecutor"
    assert adapter.availability_path == "core.execution.engines.agy.executor:is_agy_cli_available"


def test_y_is_an_mcp_mode() -> None:
    assert "Y" in SURFACE_MCP_MODES
    assert "y" in BUILDER_MCP_MODES


def test_y_has_its_own_host_tool_line() -> None:
    line = _host_tool_line("y")
    assert "run_command" in line
    assert "call_mcp_tool" in line
    assert line == _host_tool_line("Y")


def test_y_uses_the_mcp_schema_overhead_rate() -> None:
    priming = PrimingMixin()
    priming._tool_registry = ["tool"] * 100  # type: ignore[attr-defined]
    assert priming._estimate_tool_overhead("y") == priming._estimate_tool_overhead("x")


def test_y_catalog_availability_follows_agy_cli(monkeypatch) -> None:
    config = AnimaWorksConfig()

    monkeypatch.setattr("core.config.model_catalog.is_agy_cli_available", lambda: False)
    assert model_credential_available("agy/gemini-4-argon", "Y", config) is False
    ids = {entry["id"] for entry in _build_static_model_catalog(config)}
    assert "agy/gemini-4-argon" not in ids

    monkeypatch.setattr("core.config.model_catalog.is_agy_cli_available", lambda: True)
    assert model_credential_available("agy/gemini-4-argon", "Y", config) is True
    ids = {entry["id"] for entry in _build_static_model_catalog(config)}
    assert "agy/gemini-4-argon" in ids
    assert "agy/gemini-3.8-flash-medium" in ids


def test_template_models_json_routes_agy_wildcard_to_y() -> None:
    from core.paths import TEMPLATES_DIR

    models_path = TEMPLATES_DIR / "_shared" / "config_defaults" / "models.json"
    models = json.loads(models_path.read_text(encoding="utf-8"))
    assert models["agy/*"] == {"mode": "Y", "context_window": 1000000}
