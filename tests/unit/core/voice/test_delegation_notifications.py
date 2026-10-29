from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config.schemas import VoiceConfig
from core.voice.front_conversation import FrontConversation
from core.voice.session import VoiceSession
from core.voice.tts_base import TTSConfig


class _ResultSupervisor:
    def __init__(self, gate: asyncio.Event | None = None) -> None:
        self.gate = gate

    async def send_request_stream(self, **_kwargs):
        if self.gate is not None:
            await self.gate.wait()
        yield SimpleNamespace(
            done=True,
            chunk=None,
            result={"cycle_result": {"summary": "作業が完了しました"}},
        )


def _conversation(supervisor=None) -> FrontConversation:
    return FrontConversation(
        anima_name="aoi",
        supervisor=supervisor or _ResultSupervisor(),
        front_model=None,
        front_api_base=None,
        channel="phone",
    )


def _fake_notifier(monkeypatch: pytest.MonkeyPatch):
    from core.notification import notifier as notifier_module

    notifier = SimpleNamespace(notify=AsyncMock(return_value=["slack: sent"]))
    monkeypatch.setattr(notifier_module.HumanNotifier, "from_config", lambda _config: notifier)
    return notifier


@pytest.mark.asyncio
async def test_phone_close_waits_for_delegation_then_notifies_once(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = asyncio.Event()
    conversation = _conversation(_ResultSupervisor(gate))
    conversation._ensure_delegation_state()
    conversation._delegation_requests[1] = "ログを調べて"
    job = asyncio.create_task(conversation._run_ask_anima_job(1, "ログを調べて"))
    conversation._delegation_jobs[1] = job
    notifier = _fake_notifier(monkeypatch)
    config = SimpleNamespace(enabled=True)

    notification = asyncio.create_task(conversation.notify_unreported_delegations(config, wait_timeout=1))
    await asyncio.sleep(0)
    gate.set()
    await notification

    notifier.notify.assert_awaited_once()
    subject, body = notifier.notify.await_args.args[:2]
    assert subject == "電話で頼まれた件の結果（aoi）"
    assert "作業が完了しました" in body
    assert notifier.notify.await_args.kwargs["anima_name"] == "aoi"


@pytest.mark.asyncio
async def test_phone_notification_reports_jobs_still_running_after_wait_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    never = asyncio.Event()
    conversation = _conversation(_ResultSupervisor(never))
    conversation._ensure_delegation_state()
    conversation._delegation_requests[4] = "バックアップを確認"
    job = asyncio.create_task(conversation._run_ask_anima_job(4, "バックアップを確認"))
    conversation._delegation_jobs[4] = job
    notifier = _fake_notifier(monkeypatch)

    await conversation.notify_unreported_delegations(SimpleNamespace(enabled=True), wait_timeout=0)

    notifier.notify.assert_awaited_once()
    body = notifier.notify.await_args.args[1]
    assert "still running" not in body
    assert "バックアップを確認" in body
    job.cancel()
    await asyncio.gather(job, return_exceptions=True)


@pytest.mark.asyncio
async def test_web_disconnect_notification_uses_voice_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    conversation = FrontConversation(
        anima_name="aoi",
        supervisor=_ResultSupervisor(),
        front_model=None,
        front_api_base=None,
        channel="web",
    )
    conversation._unreported_delegation_results[2] = "完了した結果"
    notifier = _fake_notifier(monkeypatch)

    await conversation.notify_unreported_delegations(
        SimpleNamespace(enabled=True),
        channel="web",
        wait_timeout=0,
    )

    assert notifier.notify.await_args.args[0] == "音声で頼まれた件の結果（aoi）"


@pytest.mark.asyncio
async def test_reported_delegation_is_not_sent_again(monkeypatch: pytest.MonkeyPatch) -> None:
    conversation = _conversation()
    conversation._ensure_delegation_state()
    await conversation._run_ask_anima_job(1, "依頼")
    result = conversation.drain_delegation_results()
    assert "作業が完了しました" in result
    conversation.mark_delegation_results_reported(conversation.last_drained_delegation_ids)
    notifier = _fake_notifier(monkeypatch)

    await conversation.notify_unreported_delegations(SimpleNamespace(enabled=True), wait_timeout=0)

    notifier.notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_voice_session_close_waits_for_unreported_phone_job(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = asyncio.Event()
    notifier = _fake_notifier(monkeypatch)
    session = VoiceSession(
        anima_name="aoi",
        transport=MagicMock(),
        stt=MagicMock(),
        tts=MagicMock(),
        tts_config=TTSConfig(provider="voicevox"),
        supervisor=_ResultSupervisor(gate),
        voice_config=VoiceConfig(proactive_enabled=True),
        channel="phone",
        human_notification_config=SimpleNamespace(enabled=True),
        delegation_report_wait_sec=1,
    )
    conversation = session._front_conversation
    conversation._ensure_delegation_state()
    conversation._delegation_requests[1] = "依頼の続き"
    job = asyncio.create_task(conversation._run_ask_anima_job(1, "依頼の続き"))
    conversation._delegation_jobs[1] = job

    await session.close()
    assert session._delegation_report_task is not None
    await asyncio.sleep(0)
    gate.set()
    await session._delegation_report_task

    notifier.notify.assert_awaited_once()
    assert "作業が完了しました" in notifier.notify.await_args.args[1]
    assert session._proactive_enabled is False


def test_web_notification_on_disconnect_is_opt_in() -> None:
    def make_session(voice_config: VoiceConfig) -> VoiceSession:
        return VoiceSession(
            anima_name="aoi",
            transport=MagicMock(),
            stt=MagicMock(),
            tts=MagicMock(),
            tts_config=TTSConfig(provider="voicevox"),
            supervisor=MagicMock(),
            voice_config=voice_config,
            channel="web",
        )

    assert make_session(VoiceConfig())._report_delegations_on_close is False
    assert make_session(VoiceConfig(notify_delegations_on_web_disconnect=True))._report_delegations_on_close is True
