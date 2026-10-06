from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Signed Twilio webhooks for phone alerts and turn-based conversations."""

import asyncio
import hmac
import json
import logging
import re
import time
from html import escape
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from core.config.models import load_config
from core.config.schemas import AnimaWorksConfig, PhoneConfig
from core.config.vault import get_vault_manager
from core.phone.alert import acknowledge_alert, get_alert, notify_call_status
from core.phone.audio_store import phone_audio_store
from core.phone.session import PhoneSession, phone_sessions
from core.phone.speech import clean_for_speech, synthesize_speech
from core.phone.twilio_client import build_webhook_url, get_twilio_credentials, validate_signature

logger = logging.getLogger(__name__)

_MAX_PIN_FAILURES = 3
_MAX_SILENT_TURNS = 2
_POLL_WAIT_SEC = 10.0
_THINKING_NOTICE_INTERVAL_SEC = 20.0


def _get_phone_config() -> tuple[AnimaWorksConfig, PhoneConfig]:
    app_config = load_config()
    phone_config = app_config.phone
    if not phone_config.enabled:
        raise HTTPException(status_code=404, detail="Not found")
    return app_config, phone_config


def _form_params(body: bytes) -> dict[str, str | list[str]]:
    parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: values if len(values) > 1 else (values[0] if values else "") for key, values in parsed.items()}


def _form_value(params: dict[str, str | list[str]], key: str, default: str = "") -> str:
    value = params.get(key, default)
    if isinstance(value, list):
        return value[-1] if value else default
    return value


def _public_request_url(request: Request, phone_config: PhoneConfig) -> str:
    query = request.scope.get("query_string", b"").decode("ascii", errors="replace")
    return build_webhook_url(phone_config.public_base_url, request.url.path, raw_query=query or None)


async def _verified_request(
    request: Request,
) -> tuple[AnimaWorksConfig, PhoneConfig, dict[str, str | list[str]]]:
    app_config, phone_config = _get_phone_config()
    params = _form_params(await request.body())
    _, auth_token = get_twilio_credentials(phone_config)
    signature = request.headers.get("X-Twilio-Signature", "")
    if not validate_signature(
        auth_token or "",
        _public_request_url(request, phone_config),
        params,
        signature,
    ):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")
    return app_config, phone_config, params


def _xml_attr(name: str, value: object) -> str:
    return f' {name}="{escape(str(value), quote=True)}"'


def _tag(name: str, content: str = "", **attrs: object) -> str:
    attributes = "".join(_xml_attr(key, value) for key, value in attrs.items() if value is not None)
    return f"<{name}{attributes}>{content}</{name}>"


def _twiml(*parts: str) -> Response:
    return Response(f"<Response>{''.join(parts)}</Response>", media_type="application/xml")


def _hangup() -> str:
    return "<Hangup/>"


def _reject() -> str:
    return "<Reject/>"


def _hook_url(phone_config: PhoneConfig, endpoint: str, **params: str | int) -> str:
    return build_webhook_url(
        phone_config.public_base_url,
        f"/api/webhooks/twilio/{endpoint}",
        params=params or None,
    )


async def _play_text(
    request: Request,
    app_config: AnimaWorksConfig,
    phone_config: PhoneConfig,
    anima: str,
    text: str,
    *,
    cache_key: str | None = None,
) -> str:
    try:
        from core.paths import get_animas_dir

        animas_dir = getattr(request.app.state, "animas_dir", None) or get_animas_dir()
        audio = await synthesize_speech(
            anima,
            text,
            animas_dir=animas_dir,
            voice_config=app_config.voice,
            cache_key=cache_key,
        )
        token = phone_audio_store.put(audio)
        url = build_webhook_url(
            phone_config.public_base_url,
            f"/api/webhooks/twilio/audio/{token}.wav",
        )
        return _tag("Play", escape(url))
    except Exception:
        logger.warning("Phone speech synthesis failed for anima=%s", anima)
        spoken = clean_for_speech(text)
        language = "en-US" if app_config.locale == "en" else "ja-JP"
        return _tag("Say", escape(spoken), language=language)


async def _play_key(
    request: Request,
    app_config: AnimaWorksConfig,
    phone_config: PhoneConfig,
    key: str,
    **kwargs: object,
) -> str:
    from core.i18n import t

    text = t(key, locale=app_config.locale, **kwargs)
    return await _play_text(
        request,
        app_config,
        phone_config,
        phone_config.anima,
        text,
        cache_key=f"{app_config.locale}:{key}:{text}",
    )


def _pin_gather(phone_config: PhoneConfig, prompt: str) -> str:
    return _tag(
        "Gather",
        prompt,
        input="dtmf",
        numDigits="4",
        action=_hook_url(phone_config, "pin"),
        actionOnEmptyResult="true",
        method="POST",
        timeout="8",
    )


def _speech_gather(phone_config: PhoneConfig, prompt: str = "") -> str:
    return _tag(
        "Gather",
        prompt,
        input="speech",
        language="ja-JP",
        speechTimeout="auto",
        action=_hook_url(phone_config, "turn"),
        actionOnEmptyResult="true",
        method="POST",
    )


def _alert_gather(phone_config: PhoneConfig, alert_id: str, prompt: str) -> str:
    return _tag(
        "Gather",
        prompt,
        input="dtmf",
        numDigits="1",
        action=_hook_url(phone_config, "voice", alert=alert_id, phase="choice"),
        actionOnEmptyResult="true",
        method="POST",
        timeout="8",
    )


def _poll_redirect(phone_config: PhoneConfig) -> str:
    return _tag("Redirect", escape(_hook_url(phone_config, "poll")), method="POST")


def _poll_pause(phone_config: PhoneConfig, *, notice: str = "") -> Response:
    return _twiml(notice, '<Pause length="2"/>', _poll_redirect(phone_config))


def _pin_from_vault(phone_config: PhoneConfig) -> str | None:
    try:
        return get_vault_manager().get("shared", phone_config.pin_vault_key)
    except Exception:
        logger.warning("Phone PIN could not be read from the shared vault")
        return None


def _session_for_call(params: dict[str, str | list[str]]) -> PhoneSession | None:
    call_sid = _form_value(params, "CallSid")
    return phone_sessions.get(call_sid) if call_sid else None


def _terminal_call_status(status: str) -> bool:
    return status.lower().replace("_", "-") in {"completed", "busy", "failed", "no-answer", "canceled"}


def _result_text(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    response = result.get("response")
    if isinstance(response, str) and response.strip():
        return response
    cycle_result = result.get("cycle_result")
    if isinstance(cycle_result, dict):
        summary = cycle_result.get("summary")
        if isinstance(summary, str):
            return summary
    return ""


async def _run_turn(
    supervisor: Any,
    session: PhoneSession,
    speech: str,
    phone_config: PhoneConfig,
    locale: str,
) -> str:
    from core.i18n import t

    params = {
        "message": speech + t("phone.mode_suffix", locale=locale),
        "from_person": phone_config.from_person,
        "intent": "",
        "stream": True,
        "voice_mode": True,
        "thread_id": phone_config.thread_id,
        "images": [],
        "attachment_paths": [],
    }
    text_parts: list[str] = []
    result_data: dict[str, Any] = {}
    try:
        async for item in supervisor.send_request_stream(
            anima_name=session.anima,
            method="process_message",
            params=params,
            timeout=float(phone_config.turn_timeout_sec),
        ):
            if getattr(item, "done", False):
                value = getattr(item, "result", None)
                if isinstance(value, dict):
                    result_data = value
                continue
            chunk = getattr(item, "chunk", None)
            if not chunk:
                continue
            try:
                chunk_data = json.loads(chunk)
            except (json.JSONDecodeError, TypeError):
                chunk_data = {"type": "text_delta", "text": str(chunk)}
            if not isinstance(chunk_data, dict):
                continue
            if chunk_data.get("type") == "text_delta":
                delta = chunk_data.get("text", "")
                if delta:
                    text_parts.append(str(delta))
            elif chunk_data.get("type") == "cycle_done":
                value = chunk_data.get("cycle_result")
                if isinstance(value, dict) and not text_parts:
                    summary = value.get("summary")
                    if isinstance(summary, str) and summary:
                        text_parts.append(summary)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Phone conversation request failed for anima=%s", session.anima)
        return t("phone.turn_error", locale=locale)

    response = "".join(text_parts).strip() or _result_text(result_data).strip()
    return response or t("phone.turn_error", locale=locale)


def create_phone_router() -> APIRouter:
    """Create the Twilio phone webhook router."""
    router = APIRouter(prefix="/webhooks/twilio", tags=["phone"])

    @router.post("/voice")
    async def voice(request: Request) -> Response:
        """Handle inbound calls, alert playback, and alert DTMF responses."""
        app_config, phone_config, params = await _verified_request(request)
        call_sid = _form_value(params, "CallSid")
        if not call_sid:
            return _twiml(_hangup())

        alert_id = request.query_params.get("alert", "")
        phase = request.query_params.get("phase", "")
        if alert_id:
            alert = get_alert(alert_id)
            if alert is None or alert.anima != phone_config.anima or not alert.audio_token:
                return _twiml(_hangup())

            session = phone_sessions.get(call_sid)
            if session is None:
                session = phone_sessions.create(
                    call_sid,
                    phone_config.anima,
                    kind="alert",
                    alert_id=alert_id,
                )
            elif session.kind != "alert" or session.alert_id != alert_id:
                return _twiml(_hangup())

            if phase == "choice":
                digit = _form_value(params, "Digits")
                if digit == "1":
                    session.acknowledged = True
                    acknowledge_alert(alert_id)
                    return _twiml(await _play_key(request, app_config, phone_config, "phone.alert_ack"), _hangup())
                if digit == "2":
                    session.acknowledged = True
                    acknowledge_alert(alert_id)
                    pin_prompt = await _play_key(request, app_config, phone_config, "phone.pin_prompt")
                    return _twiml(_pin_gather(phone_config, pin_prompt))
                if not digit and not session.alert_repeat_done:
                    session.alert_repeat_done = True
                    audio_url = build_webhook_url(
                        phone_config.public_base_url,
                        f"/api/webhooks/twilio/audio/{alert.audio_token}.wav",
                    )
                    return _twiml(_tag("Play", escape(audio_url)), _hangup())
                invalid_prompt = await _play_key(request, app_config, phone_config, "phone.alert_invalid_choice")
                choice_prompt = await _play_key(
                    request,
                    app_config,
                    phone_config,
                    "phone.alert_choice",
                    anima=phone_config.anima,
                )
                return _twiml(invalid_prompt, _alert_gather(phone_config, alert_id, choice_prompt))

            audio_url = build_webhook_url(
                phone_config.public_base_url,
                f"/api/webhooks/twilio/audio/{alert.audio_token}.wav",
            )
            choice_prompt = await _play_key(
                request,
                app_config,
                phone_config,
                "phone.alert_choice",
                anima=phone_config.anima,
            )
            return _twiml(
                _tag("Play", escape(audio_url)),
                _alert_gather(phone_config, alert_id, choice_prompt),
                _tag("Play", escape(audio_url)),
                _hangup(),
            )

        direction = _form_value(params, "Direction").lower()
        if direction == "inbound":
            caller = _form_value(params, "From").strip()
            if caller not in phone_config.owner_numbers:
                return _twiml(_reject())
            phone_sessions.create(call_sid, phone_config.anima, kind="inbound")
            pin_prompt = await _play_key(request, app_config, phone_config, "phone.pin_prompt")
            return _twiml(_pin_gather(phone_config, pin_prompt))

        return _twiml(_hangup())

    @router.post("/pin")
    async def pin(request: Request) -> Response:
        """Validate the vault PIN and transition to the speech turn loop."""
        app_config, phone_config, params = await _verified_request(request)
        session = _session_for_call(params)
        if session is None:
            return _twiml(_hangup())

        supplied_pin = _form_value(params, "Digits")
        stored_pin = _pin_from_vault(phone_config)
        valid_pin = bool(
            stored_pin
            and re.fullmatch(r"[0-9]{4}", stored_pin)
            and re.fullmatch(r"[0-9]{4}", supplied_pin)
            and hmac.compare_digest(stored_pin, supplied_pin)
        )
        if not valid_pin:
            session.pin_failures += 1
            if session.pin_failures >= _MAX_PIN_FAILURES:
                locked = await _play_key(request, app_config, phone_config, "phone.pin_locked")
                return _twiml(locked, _hangup())
            invalid = await _play_key(request, app_config, phone_config, "phone.pin_invalid")
            prompt = await _play_key(request, app_config, phone_config, "phone.pin_prompt")
            return _twiml(invalid, _pin_gather(phone_config, prompt))

        session.authenticated = True
        session.pin_failures = 0
        session.silence_count = 0
        greeting = await _play_key(request, app_config, phone_config, "phone.greeting")
        return _twiml(greeting, _speech_gather(phone_config))

    @router.post("/turn")
    async def turn(request: Request) -> Response:
        """Receive one speech-recognized utterance and start its IPC task."""
        app_config, phone_config, params = await _verified_request(request)
        session = _session_for_call(params)
        if session is None or not session.authenticated:
            return _twiml(_hangup())

        speech = _form_value(params, "SpeechResult").strip()
        if not speech:
            session.silence_count += 1
            if session.silence_count >= _MAX_SILENT_TURNS:
                goodbye = await _play_key(request, app_config, phone_config, "phone.goodbye")
                return _twiml(goodbye, _hangup())
            retry = await _play_key(request, app_config, phone_config, "phone.silence_retry")
            return _twiml(retry, _speech_gather(phone_config))

        session.silence_count = 0
        existing_task = session.turn_task
        if existing_task is not None:
            if not existing_task.done():
                still_thinking = await _play_key(request, app_config, phone_config, "phone.still_thinking")
                return _twiml(still_thinking, _poll_redirect(phone_config))
            # Do not overwrite a completed but not-yet-played response.
            try:
                completed_text = existing_task.result()
            except asyncio.CancelledError:
                completed_text = _localized("phone.turn_error", app_config.locale)
            except Exception:
                completed_text = _localized("phone.turn_error", app_config.locale)
            session.turn_task = None
            clean_text, _ = _extract_emotion(completed_text)
            response_audio = await _play_text(
                request,
                app_config,
                phone_config,
                session.anima,
                clean_text,
            )
            return _twiml(response_audio, _speech_gather(phone_config))

        supervisor = getattr(request.app.state, "supervisor", None)
        if supervisor is None:
            error_audio = await _play_key(request, app_config, phone_config, "phone.turn_error")
            return _twiml(error_audio, _speech_gather(phone_config))

        session.turn_started_at = time.monotonic()
        session.last_thinking_at = 0.0
        session.timed_out = False
        session.turn_task = asyncio.create_task(
            _run_turn(supervisor, session, speech, phone_config, app_config.locale),
            name=f"phone-turn-{session.call_sid}",
        )
        wait_audio = await _play_key(request, app_config, phone_config, "phone.wait")
        return _twiml(wait_audio, _poll_redirect(phone_config))

    @router.post("/poll")
    async def poll(request: Request) -> Response:
        """Wait briefly for the current turn and play its result when ready."""
        app_config, phone_config, params = await _verified_request(request)
        session = _session_for_call(params)
        if session is None or not session.authenticated or session.turn_task is None:
            return _twiml(_hangup())

        task = session.turn_task
        elapsed = max(0.0, time.monotonic() - session.turn_started_at)
        timeout = float(phone_config.turn_timeout_sec)
        if not task.done() and elapsed < timeout:
            await asyncio.wait({task}, timeout=min(_POLL_WAIT_SEC, max(0.0, timeout - elapsed)))

        if task.done():
            try:
                response_text = task.result()
            except asyncio.CancelledError:
                return _twiml(_hangup())
            except Exception:
                response_text = ""
            session.turn_task = None
            session.turn_started_at = 0.0
            clean_text, _ = _extract_emotion(response_text)
            if not clean_text.strip():
                clean_text = _localized("phone.turn_error", app_config.locale)
            response_audio = await _play_text(
                request,
                app_config,
                phone_config,
                session.anima,
                clean_text,
            )
            return _twiml(response_audio, _speech_gather(phone_config))

        elapsed = max(0.0, time.monotonic() - session.turn_started_at)
        if elapsed >= timeout and not session.timed_out:
            session.timed_out = True
            timeout_audio = await _play_key(request, app_config, phone_config, "phone.turn_timeout")
            return _twiml(timeout_audio, _speech_gather(phone_config))

        notice = ""
        now = time.monotonic()
        if elapsed >= _THINKING_NOTICE_INTERVAL_SEC and (
            not session.last_thinking_at or now - session.last_thinking_at >= _THINKING_NOTICE_INTERVAL_SEC
        ):
            notice = await _play_key(request, app_config, phone_config, "phone.still_thinking")
            session.last_thinking_at = now
        return _poll_pause(phone_config, notice=notice)

    @router.post("/status")
    async def status(request: Request) -> Response:
        """Handle Twilio call status callbacks and release terminal sessions."""
        _app_config, phone_config, params = await _verified_request(request)
        call_sid = _form_value(params, "CallSid")
        call_status = _form_value(params, "CallStatus").lower().replace("_", "-")
        if call_sid and _terminal_call_status(call_status):
            session = phone_sessions.get(call_sid)
            alert_id = request.query_params.get("alert", "") or (session.alert_id if session else "")
            if alert_id:
                notify_call_status(alert_id, call_sid, call_status)
            # Keep an in-flight turn running after hang-up: the Anima may be
            # mid-way through work the caller asked for.
            phone_sessions.discard(call_sid)
        return Response(status_code=204)

    @router.get("/audio/{token}.wav")
    async def audio(token: str) -> Response:
        """Serve an unexpired synthesized WAV by its unguessable token."""
        _get_phone_config()
        audio_bytes = phone_audio_store.get(token)
        if audio_bytes is None:
            raise HTTPException(status_code=404, detail="Audio not found")
        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={"Cache-Control": "private, no-store"},
        )

    return router


def _extract_emotion(text: str) -> tuple[str, str]:
    from server.routes.chat_emotion import extract_emotion

    return extract_emotion(text)


def _localized(key: str, locale: str) -> str:
    from core.i18n import t

    return t(key, locale=locale)


__all__ = ["create_phone_router"]
