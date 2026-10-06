from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Twilio Media Streams WebSocket endpoint using the shared VoiceSession."""

import asyncio
import base64
import binascii
import json
import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config.models import load_config
from core.phone.session import phone_sessions
from core.phone.stream_tokens import phone_stream_tokens
from core.phone.stream_transport import TwilioMediaStreamTransport
from core.phone.twilio_client import get_twilio_credentials, validate_signature
from core.voice.audio_codec import mulaw_to_pcm16, upsample_8k_to_16k
from core.voice.session_factory import build_voice_session
from core.voice.transport import VoiceTransport
from core.voice.turn_detector import TurnDetector, drive_session
from server.routes.voice import _get_stt

logger = logging.getLogger(__name__)


def _public_stream_url(public_base_url: str, raw_query: str = "") -> str:
    """Create the externally visible WSS URL used to validate a handshake."""
    parsed = urlsplit(public_base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("phone.public_base_url must be an absolute HTTP(S) URL")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = f"{parsed.path.rstrip('/')}/api/webhooks/twilio/stream"
    return urlunsplit((scheme, parsed.netloc, path, raw_query, ""))


def _valid_optional_signature(websocket: WebSocket, phone_config: Any) -> bool:
    """Validate Twilio's optional signature without ever logging credential data."""
    signature = websocket.headers.get("X-Twilio-Signature", "")
    if not signature:
        return True
    _, auth_token = get_twilio_credentials(phone_config)
    if not auth_token:
        return False
    query = websocket.scope.get("query_string", b"").decode("ascii", errors="replace")
    try:
        url = _public_stream_url(phone_config.public_base_url, query)
    except ValueError:
        return False
    return validate_signature(auth_token, url, {}, signature)


def _valid_media_format(start: dict[str, Any]) -> bool:
    """Accept the documented mono 8 kHz μ-law format (omitted fields default to it)."""
    media_format = start.get("mediaFormat")
    if not isinstance(media_format, dict):
        return True
    encoding = str(media_format.get("encoding", "audio/x-mulaw")).casefold()
    try:
        sample_rate = int(media_format.get("sampleRate", 8_000))
        channels = int(media_format.get("channels", 1))
    except (TypeError, ValueError):
        return False
    return encoding == "audio/x-mulaw" and sample_rate == 8_000 and channels == 1


def register_phone_stream_route(router: APIRouter) -> None:
    """Register the protected Media Streams WebSocket on the Twilio router."""

    @router.websocket("/stream")
    async def phone_media_stream(websocket: WebSocket) -> None:
        # The HTTP auth middleware does not handle WebSocket scopes. This route
        # is intentionally public to Twilio, but every stream must consume the
        # short-lived CallSid-bound token issued only after successful PIN auth.
        try:
            app_config = load_config()
            phone_config = app_config.phone
        except Exception:
            logger.warning("Phone Media Streams configuration could not be loaded")
            await websocket.close(code=1011, reason="Phone service unavailable")
            return
        if not phone_config.enabled:
            await websocket.close(code=1008, reason="Phone service disabled")
            return
        if not _valid_optional_signature(websocket, phone_config):
            await websocket.close(code=1008, reason="Invalid Twilio signature")
            return

        await websocket.accept()
        detector: TurnDetector | None = None
        transport: TwilioMediaStreamTransport | None = None
        session: Any | None = None
        greeting_task: asyncio.Task[Any] | None = None
        session_tasks: set[asyncio.Task[Any]] = set()
        started = False

        def _track_task(task: asyncio.Task[Any]) -> None:
            session_tasks.add(task)

            def _finished(done: asyncio.Task[Any]) -> None:
                session_tasks.discard(done)
                if done.cancelled():
                    return
                try:
                    done.result()
                except Exception:
                    logger.warning("Phone voice session task failed", exc_info=True)

            task.add_done_callback(_finished)

        try:
            while True:
                message_text = await websocket.receive_text()
                try:
                    message = json.loads(message_text)
                except json.JSONDecodeError:
                    await websocket.close(code=1003, reason="Invalid Media Streams message")
                    return
                if not isinstance(message, dict):
                    await websocket.close(code=1003, reason="Invalid Media Streams message")
                    return

                event = message.get("event")
                if event in {"connected", "dtmf"}:
                    continue
                if event == "start":
                    if started:
                        await websocket.close(code=1008, reason="Duplicate stream start")
                        return
                    start = message.get("start")
                    if not isinstance(start, dict) or not _valid_media_format(start):
                        await websocket.close(code=1003, reason="Unsupported media format")
                        return
                    stream_sid = str(start.get("streamSid") or "")
                    call_sid = str(start.get("callSid") or "")
                    parameters = start.get("customParameters")
                    token = parameters.get("token", "") if isinstance(parameters, dict) else ""
                    if not stream_sid or not call_sid or not isinstance(token, str):
                        await websocket.close(code=1008, reason="Missing stream credentials")
                        return
                    if not phone_stream_tokens.consume(token, call_sid):
                        await websocket.close(code=1008, reason="Invalid or expired stream token")
                        return
                    phone_session = phone_sessions.get(call_sid)
                    if phone_session is None or not phone_session.authenticated:
                        await websocket.close(code=1008, reason="Call is not authenticated")
                        return

                    supervisor = getattr(websocket.app.state, "supervisor", None)
                    if supervisor is None:
                        await websocket.close(code=1011, reason="Voice service unavailable")
                        return
                    from core.paths import get_animas_dir

                    animas_dir = getattr(websocket.app.state, "animas_dir", None) or get_animas_dir()
                    detector = TurnDetector()
                    transport = TwilioMediaStreamTransport(websocket, detector, stream_sid)
                    voice_transport: VoiceTransport = transport
                    session = build_voice_session(
                        anima_name=phone_session.anima,
                        transport=voice_transport,
                        stt=_get_stt(app_config.voice),
                        supervisor=supervisor,
                        animas_dir=animas_dir,
                        voice_config=app_config.voice,
                        channel="phone",
                        from_person=phone_config.from_person,
                        thread_id=phone_config.thread_id,
                        proactive_enabled=False,
                        human_notification_config=app_config.human_notification,
                        report_delegations_on_close=True,
                    )
                    from core.i18n import t

                    greeting_task = asyncio.create_task(
                        session.speak_text(t("phone.greeting", locale=app_config.locale)),
                        name=f"phone-greeting-{call_sid}",
                    )
                    _track_task(greeting_task)
                    started = True
                    continue

                if event == "stop":
                    break
                if event == "mark" and transport is not None:
                    mark = message.get("mark")
                    name = mark.get("name", "") if isinstance(mark, dict) else ""
                    transport.handle_mark(str(name))
                    continue
                if event != "media":
                    continue
                if not started or detector is None or session is None:
                    await websocket.close(code=1008, reason="Stream has not been authenticated")
                    return

                media = message.get("media")
                payload = media.get("payload") if isinstance(media, dict) else None
                if not isinstance(payload, str):
                    continue
                try:
                    mulaw = base64.b64decode(payload, validate=True)
                except (binascii.Error, ValueError):
                    logger.debug("Ignoring malformed Twilio Media Streams audio frame")
                    continue
                pcm16_16k = upsample_8k_to_16k(mulaw_to_pcm16(mulaw))

                def _schedule_speech_end(
                    current_session: Any = session,
                    current_call_sid: str = call_sid,
                ) -> None:
                    task = asyncio.create_task(
                        current_session.handle_speech_end(from_person=phone_config.from_person),
                        name=f"phone-speech-end-{current_call_sid}",
                    )
                    _track_task(task)

                await drive_session(
                    detector.feed(pcm16_16k),
                    session,
                    from_person=phone_config.from_person,
                    on_speech_end=_schedule_speech_end,
                )

        except WebSocketDisconnect:
            logger.info("Twilio Media Streams disconnected")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Twilio Media Streams handler failed")
            try:
                await websocket.close(code=1011, reason="Voice service error")
            except Exception:
                logger.debug("Best-effort operation failed", exc_info=True)
        finally:
            pending = [task for task in session_tasks if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    logger.debug("Phone VoiceSession cleanup failed", exc_info=True)
            if transport is not None:
                try:
                    await transport.close()
                except Exception:
                    logger.debug("Phone Media Streams transport cleanup failed", exc_info=True)


__all__ = ["register_phone_stream_route"]
