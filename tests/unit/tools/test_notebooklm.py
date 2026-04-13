# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for core/tools/notebooklm.py — NotebookLM integration.

We mock the notebooklm package before importing core.tools.notebooklm
since it is an optional dependency.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Mock notebooklm modules before import ─────────────────

_NOTEBOOKLM_MODULES = [
    "notebooklm",
    "notebooklm.artifacts",
]


@pytest.fixture(autouse=True, scope="module")
def _mock_notebooklm_modules():
    """Inject mock notebooklm modules into sys.modules."""
    saved = {}
    mocks: dict[str, MagicMock] = {}
    for mod_name in _NOTEBOOKLM_MODULES:
        saved[mod_name] = sys.modules.get(mod_name)
        mock = MagicMock()
        sys.modules[mod_name] = mock
        mocks[mod_name] = mock

    # Wire up expected names on the top-level mock
    top = mocks["notebooklm"]
    top.NotebookLMClient = MagicMock()
    top.AuthError = type("AuthError", (Exception,), {})
    top.NotebookLMError = type("NotebookLMError", (Exception,), {})
    top.ArtifactType = MagicMock()

    art_mod = mocks["notebooklm.artifacts"]
    art_mod.ReportFormat = MagicMock()
    art_mod.ReportFormat.BRIEFING_DOC = "briefing_doc"
    art_mod.ReportFormat.STUDY_GUIDE = "study_guide"

    # Reload / import
    if "core.tools.notebooklm" in sys.modules:
        importlib.reload(sys.modules["core.tools.notebooklm"])
    else:
        import core.tools.notebooklm  # noqa: F401

    yield

    for mod_name in _NOTEBOOKLM_MODULES:
        if saved[mod_name] is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = saved[mod_name]
    sys.modules.pop("core.tools.notebooklm", None)


def _get_mod():
    import core.tools.notebooklm as mod

    return mod


# ── Schema tests ──────────────────────────────────────────


class TestSchemas:
    def test_get_tool_schemas_returns_list(self):
        mod = _get_mod()
        schemas = mod.get_tool_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) == 10

    def test_all_schemas_have_required_fields(self):
        mod = _get_mod()
        for schema in mod.get_tool_schemas():
            assert "name" in schema, f"Missing 'name' in schema: {schema}"
            assert "description" in schema
            assert "input_schema" in schema
            assert schema["name"].startswith("notebooklm_")

    def test_schema_names_are_unique(self):
        mod = _get_mod()
        names = [s["name"] for s in mod.get_tool_schemas()]
        assert len(names) == len(set(names))

    def test_required_params_present(self):
        mod = _get_mod()
        schemas = {s["name"]: s for s in mod.get_tool_schemas()}
        # create_notebook requires title
        assert "title" in schemas["notebooklm_create_notebook"]["input_schema"]["required"]
        # chat requires notebook_id and message
        chat_req = schemas["notebooklm_chat"]["input_schema"]["required"]
        assert "notebook_id" in chat_req
        assert "message" in chat_req


# ── Execution profile tests ───────────────────────────────


class TestExecutionProfile:
    def test_profile_exists(self):
        mod = _get_mod()
        assert hasattr(mod, "EXECUTION_PROFILE")

    def test_generate_artifact_is_background_eligible(self):
        mod = _get_mod()
        assert mod.EXECUTION_PROFILE["generate_artifact"]["background_eligible"] is True

    def test_chat_is_not_background_eligible(self):
        mod = _get_mod()
        assert mod.EXECUTION_PROFILE["chat"]["background_eligible"] is False


# ── Dispatch tests ────────────────────────────────────────


class TestDispatch:
    def test_unknown_tool_raises(self):
        mod = _get_mod()
        with pytest.raises(ValueError, match="Unknown tool"):
            mod.dispatch("notebooklm_nonexistent", {})

    def test_anima_dir_is_stripped(self):
        mod = _get_mod()
        with patch.object(mod, "_run_async", return_value=[]) as mock_run:
            mod.dispatch("notebooklm_list_notebooks", {"anima_dir": "/tmp/test", "_trigger": "chat"})
            mock_run.assert_called_once()

    def test_dispatch_list_notebooks(self):
        mod = _get_mod()
        expected = [{"id": "nb1", "title": "Test"}]
        with patch.object(mod, "_run_async", return_value=expected):
            result = mod.dispatch("notebooklm_list_notebooks", {})
            assert result == expected

    def test_dispatch_create_notebook(self):
        mod = _get_mod()
        expected = {"id": "nb1", "title": "New"}
        with patch.object(mod, "_run_async", return_value=expected):
            result = mod.dispatch("notebooklm_create_notebook", {"title": "New"})
            assert result == expected

    def test_dispatch_chat(self):
        mod = _get_mod()
        expected = {"answer": "42", "references": []}
        with patch.object(mod, "_run_async", return_value=expected):
            result = mod.dispatch(
                "notebooklm_chat",
                {"notebook_id": "nb1", "message": "What?"},
            )
            assert result == expected

    def test_dispatch_generate_artifact(self):
        mod = _get_mod()
        expected = {"success": True, "task_id": "t1", "artifact_type": "audio_overview"}
        with patch.object(mod, "_run_async", return_value=expected):
            result = mod.dispatch(
                "notebooklm_generate_artifact",
                {"notebook_id": "nb1", "artifact_type": "audio_overview"},
            )
            assert result == expected

    def test_dispatch_auth_error_returns_dict(self):
        mod = _get_mod()
        # Re-import AuthError from the mocked module
        from notebooklm import AuthError

        with patch.object(mod, "_run_async", side_effect=AuthError("expired")):
            result = mod.dispatch("notebooklm_list_notebooks", {})
            assert result["success"] is False
            assert "Authentication failed" in result["error"]

    def test_dispatch_notebooklm_error_returns_dict(self):
        mod = _get_mod()
        from notebooklm import NotebookLMError

        with patch.object(mod, "_run_async", side_effect=NotebookLMError("fail")):
            result = mod.dispatch("notebooklm_list_notebooks", {})
            assert result["success"] is False


# ── Storage path tests ────────────────────────────────────


class TestStoragePath:
    def test_missing_storage_file_raises(self):
        mod = _get_mod()
        with (
            patch.object(Path, "exists", return_value=False),
            pytest.raises(FileNotFoundError, match="notebooklm login"),
        ):
            mod._resolve_storage_path()

    def test_env_override(self):
        mod = _get_mod()
        with (
            patch.dict("os.environ", {"NOTEBOOKLM_STORAGE_PATH": "/custom/path.json"}),
            patch.object(Path, "exists", return_value=True),
        ):
            result = mod._resolve_storage_path()
            assert Path(result) == Path("/custom/path.json")


# ── CLI guide test ────────────────────────────────────────


class TestCliGuide:
    def test_get_cli_guide_returns_string(self):
        mod = _get_mod()
        guide = mod.get_cli_guide()
        assert isinstance(guide, str)
        assert "notebooklm" in guide
