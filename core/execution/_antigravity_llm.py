from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""LiteLLM custom provider that routes ``antigravity/*`` models through the
Google AI Pro / Antigravity OAuth flow.

The Antigravity CLI (``agy``) authenticates to Google with an OAuth token
that the Cloud Code Private API (``cloudcode-pa.googleapis.com``) accepts
for Gemini model inference.  This module exposes that same path to
AnimaWorks's Mode-A (LiteLLM) executor so Anima runs consume Google AI Pro
quota (same pool as the dashboard's Gemini bar) instead of an AI Studio
API key (separate billing).

Wire-up: imported once by ``core/execution/__init__.py``; registers
``"antigravity"`` into ``litellm.custom_provider_map`` so that models
named ``"antigravity/<model_id>"`` route here.

Request envelope (cloudcode-pa)::

    POST /v1internal:streamGenerateContent?alt=sse
    Authorization: Bearer <antigravity_access_token>
    {
        "model": "<model_id>",       # e.g. "gemini-2.5-flash-lite"
        "project": "<project_id>",
        "request": {
            "contents": [...],            # Gemini-style Content[]
            "systemInstruction": {...},
            "tools": [{"functionDeclarations": [...]}],
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
            "generationConfig": {...}
        }
    }

Streaming response (SSE)::

    data: {"response": {"candidates": [...], "usageMetadata": {...}}, ...}
    data: {"response": {...}}
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
from litellm.llms.custom_llm import CustomLLM, CustomLLMError
from litellm.types.utils import GenericStreamingChunk
from litellm.utils import Choices, Message, ModelResponse, Usage

logger = logging.getLogger("animaworks.execution.antigravity_llm")

_ENDPOINT_STREAM = (
    "https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
)
_ENDPOINT_NONSTREAM = (
    "https://cloudcode-pa.googleapis.com/v1internal:generateContent"
)

_DEFAULT_TIMEOUT_SEC = 600.0


# ── Auth helper ─────────────────────────────────────────────────────────────


def _get_access_token() -> tuple[str, str]:
    """Resolve a valid Antigravity access_token + project_id.

    Raises ``CustomLLMError`` on failure so LiteLLM surfaces it cleanly.
    """
    from core.config.antigravity_oauth import get_valid_access_token

    result = get_valid_access_token()
    if result is None:
        raise CustomLLMError(
            status_code=401,
            message=(
                "Antigravity CLI credential not available. "
                "Run `agy login` and ensure ANTIGRAVITY_OAUTH_CLIENT_ID / "
                "ANTIGRAVITY_OAUTH_CLIENT_SECRET are set "
                "(abconfig/secrets_local.py via Cnct_Env.py)."
            ),
        )
    return result


# ── Format conversion: LiteLLM messages → Gemini contents ───────────────────


def _strip_provider_prefix(model: str) -> str:
    """``antigravity/gemini-2.5-flash-lite`` → ``gemini-2.5-flash-lite``."""
    if model.startswith("antigravity/"):
        return model[len("antigravity/") :]
    return model


def _convert_messages_to_gemini(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Convert LiteLLM messages into Gemini Content[] + optional systemInstruction.

    LiteLLM shape::
        [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "...", "tool_calls": [...]},
            {"role": "tool", "tool_call_id": "...", "content": "..."},
        ]

    Gemini shape::
        [
            {"role": "user", "parts": [{"text": "..."}]},
            {"role": "model", "parts": [{"text": "..."}, {"functionCall": {...}}]},
            {"role": "user", "parts": [{"functionResponse": {"name": "...", "response": {...}}}]},
        ]
    """
    contents: list[dict[str, Any]] = []
    system_instruction: dict[str, Any] | None = None
    # Map tool_call_id -> tool_name so we can populate functionResponse.name later.
    tool_call_id_to_name: dict[str, str] = {}

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role == "system":
            text = _text_of(content)
            if not text:
                continue
            if system_instruction is None:
                system_instruction = {"role": "system", "parts": [{"text": text}]}
            else:
                # Multiple system messages → concatenate as additional text parts.
                system_instruction["parts"].append({"text": text})
            continue

        if role == "user":
            text = _text_of(content)
            parts: list[dict[str, Any]] = []
            if text:
                parts.append({"text": text})
            # Multi-modal images would go here (skip for now).
            if parts:
                contents.append({"role": "user", "parts": parts})
            continue

        if role == "assistant":
            parts = []
            text = _text_of(content)
            if text:
                parts.append({"text": text})
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                tool_call_id = tc.get("id", "")
                if tool_call_id and name:
                    tool_call_id_to_name[tool_call_id] = name
                raw_args = fn.get("arguments", "")
                try:
                    args_obj = (
                        json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    )
                except json.JSONDecodeError:
                    args_obj = {"_raw": raw_args}
                parts.append({"functionCall": {"name": name, "args": args_obj or {}}})
            if parts:
                contents.append({"role": "model", "parts": parts})
            continue

        if role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            tool_name = tool_call_id_to_name.get(tool_call_id) or msg.get("name", "")
            text = _text_of(content)
            # Gemini expects functionResponse.response as a struct; wrap raw text.
            try:
                response_obj = json.loads(text) if text.strip().startswith(("{", "[")) else {"content": text}
            except json.JSONDecodeError:
                response_obj = {"content": text}
            contents.append(
                {
                    "role": "user",  # Gemini treats tool responses as user-role parts
                    "parts": [
                        {
                            "functionResponse": {
                                "name": tool_name or "tool",
                                "response": response_obj if isinstance(response_obj, dict) else {"result": response_obj},
                            }
                        }
                    ],
                }
            )
            continue

    return contents, system_instruction


def _text_of(content: Any) -> str:
    """Extract a plain-text representation of LiteLLM ``content`` field."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # LiteLLM multi-modal content: [{"type": "text", "text": "..."}, ...]
        out: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                out.append(str(part.get("text", "")))
        return "".join(out)
    return str(content)


def _convert_tools_to_gemini(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Convert OpenAI-style tools list to Gemini's functionDeclarations envelope."""
    if not tools:
        return None
    declarations: list[dict[str, Any]] = []
    for tool in tools:
        fn = tool.get("function") or {}
        name = fn.get("name")
        if not name:
            continue
        decl = {"name": name}
        if "description" in fn:
            decl["description"] = fn["description"]
        if "parameters" in fn:
            decl["parameters"] = _sanitize_schema(fn["parameters"])
        declarations.append(decl)
    if not declarations:
        return None
    return [{"functionDeclarations": declarations}]


def _sanitize_schema(schema: Any) -> Any:
    """Strip JSON Schema fields Gemini doesn't accept (best-effort)."""
    if isinstance(schema, dict):
        cleaned: dict[str, Any] = {}
        for key, value in schema.items():
            # Gemini rejects $schema, additionalProperties at some levels, etc.
            if key in ("$schema", "additionalProperties", "$ref", "$defs"):
                continue
            cleaned[key] = _sanitize_schema(value)
        return cleaned
    if isinstance(schema, list):
        return [_sanitize_schema(v) for v in schema]
    return schema


# ── Response conversion: Gemini → LiteLLM ModelResponse ─────────────────────


def _convert_candidate_to_message(
    candidate: dict[str, Any],
) -> tuple[Message, str | None]:
    """Return (Message, finish_reason)."""
    parts = (candidate.get("content") or {}).get("parts") or []
    text_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if "text" in part and part["text"]:
            text_chunks.append(str(part["text"]))
        if "functionCall" in part:
            fc = part["functionCall"] or {}
            name = fc.get("name", "")
            args = fc.get("args", {})
            tool_calls.append(
                {
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                }
            )
    text = "".join(text_chunks)
    msg_kwargs: dict[str, Any] = {"role": "assistant", "content": text or None}
    if tool_calls:
        msg_kwargs["tool_calls"] = tool_calls
    message = Message(**msg_kwargs)
    finish_reason = _map_finish_reason(candidate.get("finishReason"))
    return message, finish_reason


def _map_finish_reason(reason: str | None) -> str | None:
    """Map Gemini finish reasons to OpenAI-style values."""
    if reason is None:
        return None
    mapping = {
        "STOP": "stop",
        "MAX_TOKENS": "length",
        "SAFETY": "content_filter",
        "RECITATION": "content_filter",
        "OTHER": "stop",
    }
    return mapping.get(str(reason).upper(), "stop")


def _usage_from_metadata(meta: dict[str, Any] | None) -> Usage:
    if not meta:
        return Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    prompt = int(meta.get("promptTokenCount") or 0)
    completion = int(meta.get("candidatesTokenCount") or 0)
    total = int(meta.get("totalTokenCount") or (prompt + completion))
    return Usage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


# ── HTTP request builder ────────────────────────────────────────────────────


def _build_request_body(
    model: str,
    messages: list[dict[str, Any]],
    optional_params: dict[str, Any],
    project_id: str,
) -> dict[str, Any]:
    bare_model = _strip_provider_prefix(model)
    contents, system_instruction = _convert_messages_to_gemini(messages)
    tools = _convert_tools_to_gemini(optional_params.get("tools"))

    generation_config: dict[str, Any] = {}
    if "max_tokens" in optional_params and optional_params["max_tokens"]:
        generation_config["maxOutputTokens"] = int(optional_params["max_tokens"])
    if "temperature" in optional_params and optional_params["temperature"] is not None:
        generation_config["temperature"] = float(optional_params["temperature"])
    if "top_p" in optional_params and optional_params["top_p"] is not None:
        generation_config["topP"] = float(optional_params["top_p"])
    if "stop" in optional_params and optional_params["stop"]:
        stop = optional_params["stop"]
        generation_config["stopSequences"] = stop if isinstance(stop, list) else [stop]

    request: dict[str, Any] = {"contents": contents}
    if system_instruction is not None:
        request["systemInstruction"] = system_instruction
    if tools is not None:
        request["tools"] = tools
        # Match Antigravity CLI: AUTO mode lets the model decide whether to call.
        request["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
    if generation_config:
        request["generationConfig"] = generation_config

    return {
        "model": bare_model,
        "project": project_id,
        "request": request,
    }


# ── Custom LLM implementation ───────────────────────────────────────────────


class AntigravityLLM(CustomLLM):
    """LiteLLM custom provider for the Antigravity/Cloud Code path."""

    def completion(self, *args, **kwargs) -> ModelResponse:  # type: ignore[override]
        """Synchronous completion (rarely used; defers to async via event loop)."""
        return asyncio.run(self.acompletion(*args, **kwargs))  # type: ignore[arg-type]

    async def acompletion(  # type: ignore[override]
        self,
        model: str,
        messages: list,
        api_base: str,
        custom_prompt_dict: dict,
        model_response: ModelResponse,
        print_verbose: Any,
        encoding: Any,
        api_key: Any,
        logging_obj: Any,
        optional_params: dict,
        acompletion: Any = None,
        litellm_params: Any = None,
        logger_fn: Any = None,
        headers: dict | None = None,
        timeout: float | httpx.Timeout | None = None,
        client: Any = None,
    ) -> ModelResponse:
        access_token, project_id = _get_access_token()
        body = _build_request_body(model, messages, optional_params, project_id)
        req_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if headers:
            req_headers.update(headers)

        timeout_value = _resolve_timeout(timeout)
        async with httpx.AsyncClient(timeout=timeout_value) as http:
            resp = await http.post(_ENDPOINT_NONSTREAM, json=body, headers=req_headers)

        if resp.status_code >= 400:
            raise CustomLLMError(
                status_code=resp.status_code,
                message=f"Antigravity API HTTP {resp.status_code}: {resp.text[:300]}",
            )

        try:
            payload = resp.json()
        except ValueError as exc:
            raise CustomLLMError(
                status_code=502, message=f"Invalid JSON from cloudcode-pa: {exc}"
            ) from exc

        return _populate_model_response(model_response, model, payload)

    def streaming(  # type: ignore[override]
        self, *args, **kwargs
    ) -> Iterator[GenericStreamingChunk]:
        # AnimaWorks always invokes via async; a sync streaming path is
        # not currently needed.  Raising keeps surprises loud.
        raise CustomLLMError(
            status_code=500,
            message="Antigravity streaming requires async (use astreaming).",
        )

    async def astreaming(  # type: ignore[override]
        self,
        model: str,
        messages: list,
        api_base: str,
        custom_prompt_dict: dict,
        model_response: ModelResponse,
        print_verbose: Any,
        encoding: Any,
        api_key: Any,
        logging_obj: Any,
        optional_params: dict,
        acompletion: Any = None,
        litellm_params: Any = None,
        logger_fn: Any = None,
        headers: dict | None = None,
        timeout: float | httpx.Timeout | None = None,
        client: Any = None,
    ) -> AsyncIterator[GenericStreamingChunk]:
        access_token, project_id = _get_access_token()
        body = _build_request_body(model, messages, optional_params, project_id)
        req_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        if headers:
            req_headers.update(headers)

        timeout_value = _resolve_timeout(timeout)
        # Track aggregated state so we can emit a final chunk with usage.
        accumulated_text = ""
        last_finish_reason: str | None = None
        last_usage: Usage | None = None
        tool_call_seen = False

        async with (
            httpx.AsyncClient(timeout=timeout_value) as http,
            http.stream(
                "POST", _ENDPOINT_STREAM, json=body, headers=req_headers
            ) as resp,
        ):
            if resp.status_code >= 400:
                text = await resp.aread()
                raise CustomLLMError(
                    status_code=resp.status_code,
                    message=(
                        f"Antigravity streaming HTTP {resp.status_code}: "
                        f"{text.decode('utf-8', errors='replace')[:300]}"
                    ),
                )
            buffer = ""
            async for raw_line in resp.aiter_lines():
                line = raw_line.rstrip("\r")
                if line.startswith("data:"):
                    buffer += line[len("data:") :].lstrip()
                    continue
                if line == "" and buffer:
                    try:
                        event = json.loads(buffer)
                    except json.JSONDecodeError:
                        logger.debug("Skipping malformed SSE chunk: %s", buffer[:120])
                        buffer = ""
                        continue
                    buffer = ""
                    chunk, delta_text, finish, usage = _sse_event_to_chunk(event)
                    if delta_text:
                        accumulated_text += delta_text
                    if finish:
                        last_finish_reason = finish
                    if usage is not None:
                        last_usage = usage
                    if chunk.get("tool_use"):
                        tool_call_seen = True
                    if chunk["text"] or chunk["tool_use"] or chunk["is_finished"]:
                        yield chunk
            if buffer:
                try:
                    event = json.loads(buffer)
                except json.JSONDecodeError:
                    event = None
                if event is not None:
                    chunk, delta_text, finish, usage = _sse_event_to_chunk(event)
                    if delta_text:
                        accumulated_text += delta_text
                    if finish:
                        last_finish_reason = finish
                    if usage is not None:
                        last_usage = usage
                    if chunk["text"] or chunk["tool_use"] or chunk["is_finished"]:
                        yield chunk

        # Emit a synthetic final chunk so LiteLLM closes the stream with usage.
        if last_usage is None:
            last_usage = Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        yield {
            "finish_reason": last_finish_reason or ("tool_calls" if tool_call_seen else "stop"),
            "index": 0,
            "is_finished": True,
            "text": "",
            "tool_use": None,
            "usage": {
                "prompt_tokens": last_usage.prompt_tokens,
                "completion_tokens": last_usage.completion_tokens,
                "total_tokens": last_usage.total_tokens,
            },
        }


# ── SSE helpers ─────────────────────────────────────────────────────────────


def _sse_event_to_chunk(
    event: dict[str, Any],
) -> tuple[GenericStreamingChunk, str, str | None, Usage | None]:
    """Translate one parsed SSE event into a GenericStreamingChunk.

    Returns (chunk, accumulated_text_delta, finish_reason, usage).
    """
    response = event.get("response") or {}
    candidates = response.get("candidates") or []
    delta_text = ""
    tool_use_obj: dict[str, Any] | None = None
    finish_reason: str | None = None
    for cand in candidates:
        parts = (cand.get("content") or {}).get("parts") or []
        for part in parts:
            if not isinstance(part, dict):
                continue
            if "text" in part and part["text"]:
                delta_text += str(part["text"])
            if "functionCall" in part:
                fc = part["functionCall"] or {}
                name = fc.get("name", "")
                arguments = json.dumps(fc.get("args", {}), ensure_ascii=False)
                tool_use_obj = {
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "name": name,
                    "arguments": arguments,
                    "function": {
                        "name": name,
                        "arguments": arguments,
                    },
                    "index": 0,
                }
        if cand.get("finishReason"):
            finish_reason = _map_finish_reason(cand["finishReason"])

    usage_meta = response.get("usageMetadata")
    usage = _usage_from_metadata(usage_meta) if usage_meta else None

    chunk: GenericStreamingChunk = {
        "finish_reason": finish_reason,
        "index": 0,
        "is_finished": finish_reason is not None,
        "text": delta_text,
        "tool_use": tool_use_obj,
        "usage": (
            {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
            if usage is not None
            else None
        ),
    }
    return chunk, delta_text, finish_reason, usage


def _populate_model_response(
    model_response: ModelResponse, model: str, payload: dict[str, Any]
) -> ModelResponse:
    """Fill in a LiteLLM ModelResponse from cloudcode-pa non-streaming payload."""
    response = payload.get("response") or {}
    candidates = response.get("candidates") or []
    choices: list[Choices] = []
    for idx, cand in enumerate(candidates):
        message, finish_reason = _convert_candidate_to_message(cand)
        choices.append(
            Choices(
                finish_reason=finish_reason or "stop",
                index=idx,
                message=message,
            )
        )
    if not choices:
        # Provide a minimal empty choice so downstream code doesn't crash.
        choices = [
            Choices(
                finish_reason="stop",
                index=0,
                message=Message(role="assistant", content=""),
            )
        ]
    model_response.choices = choices  # type: ignore[assignment]
    model_response.model = _strip_provider_prefix(model)
    model_response.created = int(time.time())
    model_response.usage = _usage_from_metadata(response.get("usageMetadata"))  # type: ignore[attr-defined]
    return model_response


def _resolve_timeout(timeout: Any) -> httpx.Timeout:
    if isinstance(timeout, httpx.Timeout):
        return timeout
    if timeout is None:
        return httpx.Timeout(_DEFAULT_TIMEOUT_SEC)
    try:
        return httpx.Timeout(float(timeout))
    except (TypeError, ValueError):
        return httpx.Timeout(_DEFAULT_TIMEOUT_SEC)


# ── Provider registration ───────────────────────────────────────────────────


_REGISTERED = False


def register_antigravity_provider() -> None:
    """Idempotently register ``"antigravity"`` with LiteLLM.

    Called once from ``core/execution/__init__.py`` so any
    ``antigravity/<model_id>`` reference routes to :class:`AntigravityLLM`.
    """
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        import litellm

        handler = AntigravityLLM()
        existing = getattr(litellm, "custom_provider_map", None) or []
        # Skip if already registered (defensive against double-import).
        for entry in existing:
            if isinstance(entry, dict) and entry.get("provider") == "antigravity":
                _REGISTERED = True
                return
        existing.append({"provider": "antigravity", "custom_handler": handler})
        litellm.custom_provider_map = existing  # type: ignore[attr-defined]
        _REGISTERED = True
        logger.debug("Registered Antigravity LiteLLM provider")
    except Exception:
        logger.exception("Failed to register Antigravity LiteLLM provider")
