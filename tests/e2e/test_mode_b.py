# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for Mode B (assisted) execution.

Mode B is a 1-shot LLM call where the framework handles memory I/O.
Post-call: episode recording and knowledge extraction.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from core.time_utils import now_jst, today_local
from tests.helpers.mocks import make_litellm_response, patch_litellm


@contextmanager
def _capture_system_prompt(main_resp, captured_system):
    """Patch litellm.acompletion and record the first system message sent."""
    with patch_litellm(main_resp) as mock_acompletion:

        async def wrapped(messages=None, **kwargs):
            for msg in messages or []:
                if msg.get("role") == "system":
                    captured_system.append(msg.get("content"))
                    break
            return main_resp

        mock_acompletion.side_effect = wrapped
        yield


class TestModeBMock:
    """Mode B tests using mocked LLM calls."""

    async def test_basic_oneshot_response(self, make_agent_core):
        """Basic 1-shot response returns correct CycleResult."""
        agent = make_agent_core(
            name="b-basic",
            model="ollama/gemma3:27b",
            execution_mode="assisted",
        )

        main_resp = make_litellm_response(content="Assisted response from LLM.")
        extract_resp = make_litellm_response(content="なし")

        with patch_litellm(main_resp, extract_resp):
            result = await agent.run_cycle("Hello, tell me something.")

        assert result.action == "responded"
        assert result.summary == "Assisted response from LLM."

    async def test_episode_recorded_after_response(self, make_agent_core):
        """Episode file is written after a Mode B response via MemoryManager.

        The current Mode B executor (text-loop) does not auto-record episodes;
        the caller is responsible for post-processing.  This test verifies that
        MemoryManager.append_episode() works correctly after a Mode B cycle.
        """
        agent = make_agent_core(
            name="b-episode",
            model="ollama/gemma3:27b",
            execution_mode="assisted",
        )

        main_resp = make_litellm_response(content="I think about things.")

        with patch_litellm(main_resp):
            result = await agent.run_cycle("What do you think?")

        assert result.action == "responded"

        # Simulate post-call episode recording (formerly done by old AssistedExecutor)
        episode = f"- [assisted] prompt: What do you think? → reply: {result.summary[:200]}"
        agent.memory.append_episode(episode)

        # Check episode file was written
        today = today_local().isoformat()
        episode_path = agent.anima_dir / "episodes" / f"{today}.md"
        assert episode_path.exists()
        content = episode_path.read_text(encoding="utf-8")
        assert "[assisted]" in content
        assert "What do you think?" in content

    async def test_knowledge_extracted_after_response(self, make_agent_core):
        """Knowledge file is created via MemoryManager after Mode B response.

        The current Mode B executor (text-loop) does not auto-extract knowledge;
        the caller is responsible for post-processing.  This test verifies that
        MemoryManager.write_knowledge() works correctly after a Mode B cycle.
        """
        agent = make_agent_core(
            name="b-knowledge",
            model="ollama/gemma3:27b",
            execution_mode="assisted",
        )

        main_resp = make_litellm_response(
            content="The capital of France is Paris."
        )

        with patch_litellm(main_resp):
            result = await agent.run_cycle("What is the capital of France?")

        assert result.action == "responded"

        # Simulate post-call knowledge extraction (formerly done by old AssistedExecutor)
        knowledge_text = "France's capital is Paris — useful geographic fact."
        topic = now_jst().strftime("learned_%Y%m%d_%H%M%S")
        agent.memory.write_knowledge(topic, knowledge_text)

        # Check knowledge file was created
        knowledge_files = list(
            agent.anima_dir.glob("knowledge/learned_*.md")
        )
        assert len(knowledge_files) >= 1
        content = knowledge_files[0].read_text(encoding="utf-8")
        assert "Paris" in content

    async def test_knowledge_extraction_skipped_when_nashi(self, make_agent_core):
        """No knowledge file when LLM returns 'なし'."""
        agent = make_agent_core(
            name="b-no-knowledge",
            model="ollama/gemma3:27b",
            execution_mode="assisted",
        )

        main_resp = make_litellm_response(content="Hello!")
        extract_resp = make_litellm_response(content="なし")

        # Snapshot existing knowledge files
        existing = set(agent.anima_dir.glob("knowledge/*.md"))

        with patch_litellm(main_resp, extract_resp):
            await agent.run_cycle("Hi there")

        new_files = set(agent.anima_dir.glob("knowledge/*.md")) - existing
        assert len(new_files) == 0


class TestModeBLive:
    """Mode B tests using real API calls."""

    @pytest.mark.live
    @pytest.mark.timeout(60)
    async def test_live_basic_response(self, make_agent_core):
        """Live Mode B: real LLM call produces a response and records an episode."""
        pytest.importorskip("litellm")
        agent = make_agent_core(
            name="b-live",
            model="claude-sonnet-4-6",
            execution_mode="assisted",
        )

        result = await agent.run_cycle(
            "Reply with exactly: ANIMAWORKS_B_TEST_OK"
        )

        assert result.summary
        assert result.action == "responded"
        # Episode should be recorded
        today = today_local().isoformat()
        episode_path = agent.anima_dir / "episodes" / f"{today}.md"
        assert episode_path.exists()


class TestModeBOllamaLive:
    """Mode B tests using Ollama on remote GPU server."""

    @pytest.mark.live
    @pytest.mark.ollama
    @pytest.mark.timeout(120)
    async def test_live_ollama_basic_response(self, make_agent_core):
        """Live Mode B: Ollama model produces an assisted response."""
        pytest.importorskip("litellm")
        import os

        agent = make_agent_core(
            name="b-ollama-live",
            model="ollama/glm-flash-q8:32k",
            credential="ollama",
            execution_mode="assisted",
            api_base_url=os.environ.get("OLLAMA_API_BASE", ""),
        )

        result = await agent.run_cycle(
            "Reply with exactly: ANIMAWORKS_OLLAMA_TEST_OK"
        )

        assert result.summary
        assert result.action == "responded"


