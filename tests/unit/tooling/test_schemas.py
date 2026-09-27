"""Tests for core.tooling.schemas — canonical tool schema definitions and converters."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock, patch

import core.integrations
from core.tooling.schemas import (
    MEMORY_TOOLS,
    load_external_schemas,
    to_litellm_format,
)

# ── Canonical schema structure ─────────────────────────────────


class TestMemoryTools:
    def test_memory_tools_is_list(self):
        assert isinstance(MEMORY_TOOLS, list)
        assert len(MEMORY_TOOLS) == 5

    def test_search_memory_schema(self):
        schema = next(t for t in MEMORY_TOOLS if t["name"] == "search_memory")
        assert "description" in schema
        assert schema["parameters"]["type"] == "object"
        assert "query" in schema["parameters"]["properties"]
        assert "query" in schema["parameters"]["required"]

    def test_search_memory_scope_includes_common_knowledge(self):
        schema = next(t for t in MEMORY_TOOLS if t["name"] == "search_memory")
        scope_enum = schema["parameters"]["properties"]["scope"]["enum"]
        assert "common_knowledge" in scope_enum
        assert "skills" in scope_enum
        assert "activity_log" in scope_enum
        # Also verify other expected values are still present
        assert "knowledge" in scope_enum
        assert "episodes" in scope_enum
        assert "procedures" in scope_enum
        assert "all" in scope_enum

    def test_read_memory_file_schema(self):
        schema = next(t for t in MEMORY_TOOLS if t["name"] == "read_memory_file")
        assert "path" in schema["parameters"]["properties"]
        assert "path" in schema["parameters"]["required"]

    def test_write_memory_file_schema(self):
        schema = next(t for t in MEMORY_TOOLS if t["name"] == "write_memory_file")
        props = schema["parameters"]["properties"]
        assert "path" in props
        assert "content" in props
        assert "mode" in props
        assert set(schema["parameters"]["required"]) == {"path", "content"}

    def test_send_message_schema(self):
        schema = next(t for t in MEMORY_TOOLS if t["name"] == "send_message")
        props = schema["parameters"]["properties"]
        assert "to" in props
        assert "content" in props
        assert set(schema["parameters"]["required"]) == {"to", "content", "intent"}


class TestSendMessageSchema:
    def test_intent_property_exists(self):
        send_msg = next(t for t in MEMORY_TOOLS if t["name"] == "send_message")
        assert "intent" in send_msg["parameters"]["properties"]

    def test_intent_required(self):
        send_msg = next(t for t in MEMORY_TOOLS if t["name"] == "send_message")
        assert "intent" in send_msg["parameters"]["required"]

    def test_intent_type_is_string(self):
        send_msg = next(t for t in MEMORY_TOOLS if t["name"] == "send_message")
        assert send_msg["parameters"]["properties"]["intent"]["type"] == "string"


# ── Format converters ─────────────────────────────────────────


class TestToLitellmFormat:
    def test_converts_single_tool(self):
        tools = [{"name": "bar", "description": "desc2", "parameters": {"type": "object"}}]
        result = to_litellm_format(tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "bar"
        assert result[0]["function"]["description"] == "desc2"
        assert result[0]["function"]["parameters"] == {"type": "object"}

    def test_converts_multiple_tools(self):
        result = to_litellm_format(MEMORY_TOOLS)
        assert len(result) == len(MEMORY_TOOLS)
        for item in result:
            assert item["type"] == "function"
            assert "name" in item["function"]

    def test_empty_list(self):
        assert to_litellm_format([]) == []


# ── load_external_schemas ─────────────────────────────────────


class TestLoadExternalSchemas:
    def test_empty_registry(self):
        assert load_external_schemas([]) == []

    def test_unknown_tool_name(self):
        result = load_external_schemas(["nonexistent_tool_xyz"])
        assert result == []

    def test_loads_schemas_from_module(self):
        mock_mod = MagicMock()
        mock_mod.get_tool_schemas.return_value = [
            {
                "name": "web_search",
                "description": "Search the web",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ]

        with (
            patch.dict(core.integrations.TOOL_MODULES, {"web_search": "core.integrations.web_search"}, clear=True),
            patch("importlib.import_module", return_value=mock_mod),
        ):
            result = load_external_schemas(["web_search"])

        assert len(result) == 1
        assert result[0]["name"] == "web_search"
        assert result[0]["parameters"] == {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }

    def test_handles_module_without_get_tool_schemas(self):
        mock_mod = MagicMock(spec=[])  # No get_tool_schemas attribute

        with (
            patch.dict(core.integrations.TOOL_MODULES, {"web_search": "core.integrations.web_search"}, clear=True),
            patch("importlib.import_module", return_value=mock_mod),
        ):
            result = load_external_schemas(["web_search"])

        assert result == []

    def test_handles_import_error(self):
        with (
            patch.dict(core.integrations.TOOL_MODULES, {"web_search": "core.integrations.web_search"}, clear=True),
            patch("importlib.import_module", side_effect=ImportError("no module")),
        ):
            result = load_external_schemas(["web_search"])

        assert result == []

    def test_skips_tool_not_in_registry(self):
        with patch.dict(core.integrations.TOOL_MODULES, {"web_search": "core.integrations.web_search"}, clear=True):
            result = load_external_schemas(["slack"])

        assert result == []

    def test_uses_parameters_key_as_fallback(self):
        mock_mod = MagicMock()
        mock_mod.get_tool_schemas.return_value = [
            {
                "name": "test_tool",
                "description": "Test",
                "parameters": {"type": "object", "properties": {}},
            }
        ]

        with (
            patch.dict(core.integrations.TOOL_MODULES, {"test": "core.integrations.test"}, clear=True),
            patch("importlib.import_module", return_value=mock_mod),
        ):
            result = load_external_schemas(["test"])

        assert len(result) == 1
        assert result[0]["parameters"] == {"type": "object", "properties": {}}
