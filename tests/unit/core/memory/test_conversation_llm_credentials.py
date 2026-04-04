from __future__ import annotations

"""Tests for ConversationMemory._call_llm() consolidation model usage.

Since _call_llm() always uses the consolidation model (via _llm_utils),
these tests verify that the consolidation model kwargs are correctly
applied and that anima-specific provider kwargs are NOT injected.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.schemas import ModelConfig


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "test_anima"
    d.mkdir()
    (d / "state").mkdir()
    return d


def _make_acompletion_mock() -> AsyncMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = "summary"
    return AsyncMock(return_value=resp)


class TestCallLlmConsolidationModel:
    """_call_llm always uses the consolidation model, not the anima's model."""

    @pytest.mark.asyncio
    async def test_uses_consolidation_model(self, anima_dir: Path) -> None:
        cfg = ModelConfig(model="bedrock/jp.anthropic.claude-sonnet-4-6")
        from core.memory.conversation import ConversationMemory

        conv = ConversationMemory(anima_dir, cfg)
        mock_ac = _make_acompletion_mock()

        consolidation_kwargs = {"model": "anthropic/claude-sonnet-4-6", "api_key": "test-key"}
        with (
            patch("core.memory._llm_utils.get_llm_kwargs_for_model", return_value=consolidation_kwargs),
            patch("litellm.acompletion", mock_ac),
        ):
            await conv._call_llm("sys", "user msg")

        mock_ac.assert_called_once()
        kw = mock_ac.call_args
        assert kw.kwargs["model"] == "anthropic/claude-sonnet-4-6"
        assert kw.kwargs["api_key"] == "test-key"

    @pytest.mark.asyncio
    async def test_no_anima_provider_kwargs_injected(self, anima_dir: Path) -> None:
        """Anima-specific provider kwargs (bedrock, azure, vertex) are not applied."""
        cfg = ModelConfig(
            model="bedrock/jp.anthropic.claude-sonnet-4-6",
            extra_keys={
                "aws_access_key_id": "AKIATEST",
                "aws_secret_access_key": "secret123",
                "aws_region_name": "ap-northeast-1",
            },
        )
        from core.memory.conversation import ConversationMemory

        conv = ConversationMemory(anima_dir, cfg)
        mock_ac = _make_acompletion_mock()

        consolidation_kwargs = {"model": "anthropic/claude-sonnet-4-6"}
        with (
            patch("core.memory._llm_utils.get_llm_kwargs_for_model", return_value=consolidation_kwargs),
            patch("litellm.acompletion", mock_ac),
        ):
            await conv._call_llm("sys", "user msg")

        kw = mock_ac.call_args
        for key in (
            "aws_access_key_id", "aws_secret_access_key", "aws_region_name",
            "api_version", "vertex_project", "vertex_location", "vertex_credentials",
        ):
            assert key not in kw.kwargs

    @pytest.mark.asyncio
    async def test_consolidation_model_without_api_key(self, anima_dir: Path) -> None:
        cfg = ModelConfig(model="claude-sonnet-4-6")
        from core.memory.conversation import ConversationMemory

        conv = ConversationMemory(anima_dir, cfg)
        mock_ac = _make_acompletion_mock()

        consolidation_kwargs = {"model": "anthropic/claude-sonnet-4-6"}
        with (
            patch("core.memory._llm_utils.get_llm_kwargs_for_model", return_value=consolidation_kwargs),
            patch("litellm.acompletion", mock_ac),
        ):
            await conv._call_llm("sys", "user msg")

        kw = mock_ac.call_args
        assert kw.kwargs["model"] == "anthropic/claude-sonnet-4-6"
        assert "api_key" not in kw.kwargs
