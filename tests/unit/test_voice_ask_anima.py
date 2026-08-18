# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the ``ask_anima`` async delegation (PR-3).

Covers:
  - front lane tool-call stream → tool_executor → follow-up completion → text
  - ``_ask_anima`` immediate ACK / task firing / result reflow into the queue
  - concurrent-cap (2) with rejection ACK on the 3rd
  - result prefixing into the next user turn (system prompt unchanged)
  - WS close does NOT cancel running delegation tasks
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config.schemas import VoiceConfig
from core.voice.front import ASK_ANIMA_TOOL, VoiceFrontLane
from core.voice.session import MAX_ASK_ANIMA_CONCURRENT, VoiceSession
from core.voice.tts_base import TTSConfig


def _make_session(supervisor: MagicMock, *, front_model: str | None = None) -> VoiceSession:
    stt = AsyncMock()
    stt.transcribe_buffer_async = AsyncMock(return_value={"raw_text": "テスト", "language": "ja"})
    tts = AsyncMock()
    tts.health_check = AsyncMock(return_value=True)

    async def _synthesize(text: str, config: object) -> AsyncMock:
        yield b""

    tts.synthesize = _synthesize
    ws = AsyncMock()
    voice_config = VoiceConfig(stt_refine_enabled=False)
    return VoiceSession(
        "test",
        ws,
        stt,
        tts,
        TTSConfig(provider="voicevox"),
        supervisor,
        voice_config,
        front_model=front_model or "openai/qwen3.6-35b-a3b",
        front_api_base="http://x:8000/v1",
    )


def _done_response(summary: str = "完了しました") -> SimpleNamespace:
    return SimpleNamespace(
        done=True,
        chunk=None,
        result={"cycle_result": {"summary": summary, "emotion": "neutral"}},
    )


def _immediate_supervisor(summary: str = "完了しました") -> MagicMock:
    async def _stream(**kwargs):  # type: ignore[no-untyped-def]
        yield _done_response(summary)

    supervisor = MagicMock()
    supervisor.send_request_stream = MagicMock(side_effect=_stream)
    return supervisor


def _blocked_supervisor() -> tuple[MagicMock, asyncio.Event, asyncio.Event]:
    started = asyncio.Event()
    release = asyncio.Event()

    async def _stream(**kwargs):  # type: ignore[no-untyped-def]
        started.set()
        await release.wait()
        yield _done_response("完了しました")

    supervisor = MagicMock()
    supervisor.send_request_stream = MagicMock(side_effect=_stream)
    return supervisor, started, release


# ── Front lane tool-call stream ──────────────────────────────────


class TestFrontLaneToolCall:
    @pytest.mark.asyncio
    async def test_tool_call_runs_executor_then_continues(self) -> None:
        lane = VoiceFrontLane(
            model="openai/qwen3.6-35b-a3b",
            api_base="http://x:8000/v1",
            system_prompt="SYSTEM",
        )

        async def _tool_response(**kwargs):  # type: ignore[no-untyped-def]
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="call_1",
                                    function=SimpleNamespace(
                                        name="ask_anima",
                                        arguments='{"request": "横浜の天気を調べて"}',
                                    ),
                                )
                            ],
                        ),
                        finish_reason="tool_calls",
                    )
                ]
            )

        async def _final_response(**kwargs):  # type: ignore[no-untyped-def]
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="やっておくね", tool_calls=None),
                        finish_reason="stop",
                    )
                ]
            )

        executor = MagicMock(return_value="受理しました (job 1)")
        with patch(
            "core.voice.front.litellm.acompletion",
            side_effect=[_tool_response(), _final_response()],
        ) as mock_ac:
            got = [
                d
                async for d in lane.stream(
                    "横浜の天気を調べて",
                    tools=[ASK_ANIMA_TOOL],
                    tool_executor=executor,
                )
            ]

        assert "".join(got) == "やっておくね"
        executor.assert_called_once_with("ask_anima", {"request": "横浜の天気を調べて"})
        # second (follow-up) completion carries the tool result message
        assert mock_ac.await_count == 2
        second_messages = mock_ac.await_args_list[1].kwargs["messages"]
        assert second_messages[-1]["role"] == "tool"
        assert second_messages[-1]["tool_call_id"] == "call_1"

    @pytest.mark.asyncio
    async def test_no_tool_call_skips_executor(self) -> None:
        lane = VoiceFrontLane(
            model="openai/qwen3.6-35b-a3b",
            api_base="http://x:8000/v1",
            system_prompt="SYSTEM",
        )

        async def _plain_response(**kwargs):  # type: ignore[no-untyped-def]
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="こんにちは", tool_calls=None),
                        finish_reason="stop",
                    )
                ]
            )

        executor = MagicMock()
        with patch(
            "core.voice.front.litellm.acompletion", side_effect=[_plain_response()]
        ):
            got = [d async for d in lane.stream("hi", tool_executor=executor)]
        assert "".join(got) == "こんにちは"
        executor.assert_not_called()


# ── _ask_anima delegation ──────────────────────────────────────


class TestAskAnimaDelegation:
    @pytest.mark.asyncio
    async def test_immediate_ack_and_result_reflow(self) -> None:
        sess = _make_session(_immediate_supervisor())
        ack = sess._ask_anima("報告書を作成して")
        assert "受理しました" in ack
        assert "job 1" in ack
        # task fired and completes
        await asyncio.gather(*list(sess._delegation_jobs.values()))
        drained = sess._drain_delegation_results()
        assert "[ask_anima完了 job 1: 完了しました]" in drained

    @pytest.mark.asyncio
    async def test_concurrent_cap_rejects_third(self) -> None:
        supervisor, started, release = _blocked_supervisor()
        sess = _make_session(supervisor)
        ack1 = sess._ask_anima("a")
        ack2 = sess._ask_anima("b")
        assert "受理しました" in ack1
        assert "受理しました" in ack2
        ack3 = sess._ask_anima("c")
        assert f"実行中の依頼が{MAX_ASK_ANIMA_CONCURRENT}件ある" in ack3
        # the rejected one did NOT create a new job task
        assert len(sess._delegation_jobs) == 2
        release.set()
        await asyncio.gather(*list(sess._delegation_jobs.values()))

    @pytest.mark.asyncio
    async def test_result_prefixed_into_next_user_turn(self) -> None:
        sess = _make_session(_immediate_supervisor("完了したよ"))
        sess._ask_anima("メールを送って")
        await asyncio.gather(*list(sess._delegation_jobs.values()))
        # inject a pending result, then run a front turn and capture the text
        # actually passed to the lane.
        captured: dict[str, object] = {}

        async def _stream(user_text: str, **kwargs):  # type: ignore[no-untyped-def]
            captured["text"] = user_text
            captured["tools"] = kwargs.get("tools")
            yield "了解しました。 <!-- emotion: {\"emotion\": \"smile\"} -->"

        lane = AsyncMock()
        lane.check_health = AsyncMock(return_value=True)
        lane.reset_turn = MagicMock()
        lane.stream = _stream
        lane.system_prompt = "FIXED_SYSTEM"
        sess._front_lane = lane
        tts_ok = await sess._check_tts_health()
        await sess._run_front_turn(lane, "次の話題", "human", tts_ok)

        text = captured["text"]
        assert "[ask_anima完了 job 1:" in text
        assert "次の話題" in text
        # system prompt must be the lane's own fixed prompt (unchanged)
        assert lane.system_prompt == "FIXED_SYSTEM"

    @pytest.mark.asyncio
    async def test_close_does_not_cancel_delegation_tasks(self) -> None:
        supervisor, started, release = _blocked_supervisor()
        sess = _make_session(supervisor)
        ack = sess._ask_anima("時間のかかる処理")
        assert "受理しました" in ack
        await started.wait()
        task = list(sess._delegation_jobs.values())[0]
        assert not task.done()
        await sess.close()
        # close() must not have cancelled the running delegation task
        assert not task.done()
        release.set()
        await asyncio.wait_for(task, 5.0)
        assert task.done()
