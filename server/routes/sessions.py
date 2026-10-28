from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import asyncio
import json
import logging
import math
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.activity.logger import ActivityLogger
from core.memory.conversation.memory import ConversationMemory
from core.memory.conversation.shortterm import ShortTermMemory
from core.memory.manager import MemoryManager
from core.skills.activation import validate_thread_id

logger = logging.getLogger("animaworks.routes.sessions")


class NotificationReplyRequest(BaseModel):
    notification_id: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=4000)


def _thread_file_conversation_view(anima_dir, thread_id: str) -> dict | None:
    """Build a conversation view from the thread's conversation file.

    Threads persist their turns in ``state/conversations/{thread_id}.json``
    while the activity log only holds entries within its retention window
    (and older threads predate thread_id tagging entirely). When the
    activity-based view is missing turns, this file is the durable source.
    Returns None when the file is absent or unreadable.
    """
    conv_file = anima_dir / "state" / "conversations" / f"{thread_id}.json"
    if not conv_file.is_file():
        return None
    try:
        data = json.loads(conv_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError):
        return None

    turns = data.get("turns", [])
    if not isinstance(turns, list):
        return None

    messages = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        role = turn.get("role", "")
        if role not in ("human", "assistant"):
            continue
        tool_calls = []
        for rec in turn.get("tool_records", []) or []:
            if not isinstance(rec, dict):
                continue
            tool_calls.append(
                {
                    "tool_use_id": rec.get("tool_id", ""),
                    "tool_name": rec.get("tool_name", ""),
                    "input": rec.get("input_summary", ""),
                    "result": rec.get("result_summary", ""),
                    "is_error": bool(rec.get("is_error", False)),
                }
            )
        messages.append(
            {
                "ts": turn.get("timestamp", ""),
                "role": role,
                "content": turn.get("content", ""),
                "from_person": "",
                "to_person": "",
                "source_key": "chat",
                "tool_calls": tool_calls,
            }
        )

    if not messages:
        return None

    sessions = ActivityLogger._group_into_sessions(messages, 10)
    return {"sessions": sessions, "has_more": False, "next_before": None}


def _count_view_messages(view: dict) -> int:
    return sum(len(s.get("messages", [])) for s in view.get("sessions", []))


def create_sessions_router() -> APIRouter:
    router = APIRouter()

    @router.get("/animas/{name}/sessions")
    async def list_sessions(name: str, request: Request):
        """List all available sessions: active conversation, archives, episodes."""
        animas_dir = request.app.state.animas_dir
        anima_dir = animas_dir / name
        if not anima_dir.exists():
            raise HTTPException(status_code=404, detail=f"Anima not found: {name}")

        from core.config.models import load_model_config

        model_config = load_model_config(anima_dir)

        # Active conversation
        conv = ConversationMemory(anima_dir, model_config)
        conv_state = conv.load()
        active_conv = None
        if conv_state.turns or conv_state.compressed_summary:
            active_conv = {
                "exists": True,
                "turn_count": len(conv_state.turns),
                "total_turn_count": conv_state.total_turn_count,
                "last_timestamp": (conv_state.turns[-1].timestamp if conv_state.turns else ""),
                "first_timestamp": (conv_state.turns[0].timestamp if conv_state.turns else ""),
                "has_summary": bool(conv_state.compressed_summary),
            }

        # Thread conversations
        threads = []
        conv_dir = anima_dir / "state" / "conversations"
        if conv_dir.is_dir():
            for conv_file in sorted(conv_dir.glob("*.json"), reverse=True):
                try:
                    data = json.loads(conv_file.read_text(encoding="utf-8"))
                    turns = data.get("turns", [])
                    threads.append(
                        {
                            "thread_id": conv_file.stem,
                            "turn_count": len(turns),
                            "total_turn_count": len(turns) + data.get("compressed_turn_count", 0),
                            "last_timestamp": turns[-1].get("timestamp", "") if turns else "",
                            "has_summary": bool(data.get("compressed_summary", "")),
                        }
                    )
                except (json.JSONDecodeError, TypeError):
                    pass

        # Archived sessions — metadata only (no full content read)
        stm = ShortTermMemory(anima_dir, read_only=True)
        archived = []
        archive_dir = stm._archive_dir
        if archive_dir.exists():
            for json_file in sorted(archive_dir.glob("*.json"), reverse=True):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    ts_str = json_file.stem
                    archived.append(
                        {
                            "id": ts_str,
                            "timestamp": data.get("timestamp", ts_str),
                            "trigger": data.get("trigger", ""),
                            "turn_count": data.get("turn_count", 0),
                            "context_usage_ratio": data.get(
                                "context_usage_ratio",
                                0,
                            ),
                            "original_prompt_preview": data.get(
                                "original_prompt",
                                "",
                            )[:200],
                            "has_markdown": (archive_dir / f"{ts_str}.md").exists(),
                        }
                    )
                except (json.JSONDecodeError, TypeError):
                    pass

        # Episodes — partial read (first 200 chars only, no full file load)
        memory = MemoryManager(anima_dir, read_only=True)
        episodes = []
        for stem in memory.list_episode_files():
            ep_path = memory.episodes_dir / f"{stem}.md"
            preview = ""
            if ep_path.exists():
                with ep_path.open(encoding="utf-8") as f:
                    preview = f.read(200)
            episodes.append({"date": stem, "preview": preview})

        # Transcripts — count lines without loading full content
        transcripts = []
        transcript_dir = anima_dir / "transcripts"
        if transcript_dir.exists():
            for tf in sorted(transcript_dir.glob("*.jsonl"), reverse=True):
                line_count = sum(1 for line in tf.read_text(encoding="utf-8").splitlines() if line.strip())
                transcripts.append({"date": tf.stem, "message_count": line_count})

        return {
            "anima": name,
            "active_conversation": active_conv,
            "threads": threads,
            "archived_sessions": archived,
            "episodes": episodes,
            "transcripts": transcripts,
        }

    # ── Conversation history (activity_log-based) ──────────

    @router.get("/animas/{name}/conversation/history")
    async def get_conversation_history(
        name: str,
        limit: int = 50,
        before: str | None = None,
        thread_id: str = "default",
        strict_thread: bool = False,
        request: Request = None,
    ):
        """Get conversation history from activity log.

        Returns sessions with messages, tool calls nested into assistant
        messages, and cursor-based pagination.
        """
        animas_dir = request.app.state.animas_dir
        anima_dir = animas_dir / name
        if not anima_dir.exists():
            raise HTTPException(status_code=404, detail=f"Anima not found: {name}")

        limit = max(1, min(limit, 200))
        activity = ActivityLogger(anima_dir)
        # Log scanning is sync file I/O + JSON parsing; keep it off the
        # event loop (UI polls this endpoint every few seconds).
        view = await asyncio.to_thread(
            activity.get_conversation_view,
            before=before,
            limit=limit,
            thread_id=thread_id,
            strict_thread=strict_thread,
        )

        # Named threads: the activity log may miss turns (retention window,
        # pre-thread_id-tagging history, or a response whose activity entry
        # was lost). Fall back to the thread's own conversation file when it
        # holds more messages than the activity-based view.
        if thread_id not in ("default", "inbox") and before is None:
            try:
                safe_thread_id = validate_thread_id(thread_id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid thread_id: {thread_id}") from None
            file_view = _thread_file_conversation_view(anima_dir, safe_thread_id)
            if file_view and _count_view_messages(file_view) > _count_view_messages(view):
                call_messages = [
                    message
                    for session in view.get("sessions", [])
                    for message in session.get("messages", [])
                    if message.get("type") == "voice_call"
                ]
                if call_messages:
                    file_messages = [
                        message for session in file_view.get("sessions", []) for message in session.get("messages", [])
                    ]
                    present_calls = {(message.get("ts", ""), message.get("type", "")) for message in file_messages}
                    file_messages.extend(
                        message
                        for message in call_messages
                        if (message.get("ts", ""), message.get("type", "")) not in present_calls
                    )
                    file_messages.sort(key=lambda message: message.get("ts", ""))
                    file_view = {
                        "sessions": ActivityLogger._group_into_sessions(file_messages, 10),
                        "has_more": False,
                        "next_before": None,
                    }
                return file_view
        return view

    @router.post("/animas/{name}/notifications/reply")
    async def reply_to_notification(
        name: str,
        body: NotificationReplyRequest,
        request: Request,
    ):
        """Route a reply to a human_notify entry back to its originating Anima."""
        if not name or name.startswith(".") or "/" in name:
            raise HTTPException(status_code=400, detail="Invalid Anima name")
        animas_dir = request.app.state.animas_dir
        anima_dir = animas_dir / name
        if not anima_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"Anima not found: {name}")

        activity = ActivityLogger(anima_dir)
        view = await asyncio.to_thread(activity.get_conversation_view, limit=200, thread_id="default")
        notification = next(
            (
                message
                for session in view.get("sessions", [])
                for message in session.get("messages", [])
                if message.get("type") == "human_notify"
                and body.notification_id in {str(message.get("notification_id") or ""), str(message.get("ts") or "")}
            ),
            None,
        )
        if notification is None:
            raise HTTPException(status_code=404, detail="Notification not found")
        if notification.get("replied"):
            raise HTTPException(status_code=409, detail="Notification already has a reply")

        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Reply text is required")
        actor = getattr(getattr(request.state, "user", None), "username", "") or "human"
        callback_id = str(notification.get("callback_id") or "")

        from core.notification.reply_routing import (
            _notification_context,
            _resolve_callback_text_reply,
            deliver_notification_reply,
        )

        if await _resolve_callback_text_reply(callback_id, text, actor):
            return {"status": "resolved", "notification_id": body.notification_id, "replied": True}

        notification_text = "\n".join(
            part for part in (str(notification.get("subject") or ""), str(notification.get("content") or "")) if part
        )
        from core.paths import get_shared_dir

        routed = await deliver_notification_reply(
            name,
            text,
            get_shared_dir(),
            actor=actor,
            source="web",
            source_message_id=body.notification_id,
            external_user_id=actor,
            external_channel_id="web",
            external_thread_ts=body.notification_id,
            thread_context=_notification_context(name, notification_text),
            notification_id=body.notification_id,
            callback_id=callback_id,
        )
        if not routed:
            raise HTTPException(status_code=400, detail="Reply could not be delivered")
        return {"status": "ok", "notification_id": body.notification_id, "replied": True}

    @router.post("/animas/{name}/conversation/calls")
    async def record_voice_call(name: str, request: Request, payload: dict[str, Any]):
        """Persist a completed voice call in the Anima's conversation history."""
        if not name or name.startswith(".") or "/" in name or ".." in name:
            raise HTTPException(status_code=400, detail="Invalid Anima name")
        anima_dir = request.app.state.animas_dir / name
        if not anima_dir.exists():
            raise HTTPException(status_code=404, detail=f"Anima not found: {name}")

        try:
            thread_id = validate_thread_id(payload.get("thread_id", "default"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

        duration = payload.get("duration_seconds", 0)
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise HTTPException(status_code=400, detail="duration_seconds must be a number")
        try:
            numeric_duration = float(duration)
        except (OverflowError, ValueError):
            raise HTTPException(status_code=400, detail="duration_seconds must be finite") from None
        if not math.isfinite(numeric_duration):
            raise HTTPException(status_code=400, detail="duration_seconds must be finite")
        duration_seconds = max(0, min(int(numeric_duration), 86_400))

        started_at = payload.get("started_at", "")
        if not isinstance(started_at, str) or len(started_at) > 64:
            raise HTTPException(status_code=400, detail="started_at must be an ISO timestamp")
        try:
            datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="started_at must be an ISO timestamp") from None

        summary = payload.get("summary", "")
        if not isinstance(summary, str):
            raise HTTPException(status_code=400, detail="summary must be a string")
        summary = summary[:60]

        raw_transcript = payload.get("transcript", [])
        if not isinstance(raw_transcript, list) or len(raw_transcript) > 500:
            raise HTTPException(status_code=400, detail="transcript must contain at most 500 lines")
        transcript: list[dict[str, str]] = []
        total_transcript_chars = 0
        for line in raw_transcript:
            if not isinstance(line, dict) or line.get("speaker") not in {"user", "assistant"}:
                raise HTTPException(status_code=400, detail="transcript lines need a valid speaker")
            text = line.get("text", "")
            if not isinstance(text, str):
                raise HTTPException(status_code=400, detail="transcript line text must be a string")
            total_transcript_chars += len(text)
            if total_transcript_chars > 100_000:
                raise HTTPException(status_code=400, detail="transcript is too long")
            transcript.append({"speaker": line["speaker"], "text": text})

        activity = ActivityLogger(anima_dir)
        entry = await asyncio.to_thread(
            activity.log,
            "voice_call",
            content=summary,
            summary=summary,
            channel="chat",
            origin="human",
            meta={
                "thread_id": thread_id,
                "started_at": started_at,
                "duration_seconds": duration_seconds,
                "transcript": transcript,
            },
        )
        return {"ok": True, "ts": entry.ts}

    @router.get("/animas/{name}/sessions/{session_id}")
    async def get_session_detail(
        name: str,
        session_id: str,
        request: Request,
    ):
        """Get archived session detail."""
        animas_dir = request.app.state.animas_dir
        anima_dir = animas_dir / name
        if not anima_dir.exists():
            raise HTTPException(status_code=404, detail=f"Anima not found: {name}")

        stm = ShortTermMemory(anima_dir, read_only=True)
        archive_dir = stm._archive_dir
        json_path = archive_dir / f"{session_id}.json"
        md_path = archive_dir / f"{session_id}.md"

        if not json_path.exists():
            raise HTTPException(status_code=404, detail="Session not found")

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=500, detail="Session data corrupted") from None

        markdown = ""
        if md_path.exists():
            markdown = md_path.read_text(encoding="utf-8")

        return {
            "anima": name,
            "session_id": session_id,
            "data": data,
            "markdown": markdown,
        }

    @router.get("/animas/{name}/transcripts/{date}")
    async def get_transcript(name: str, date: str, request: Request):
        """Get full conversation transcript for a specific date."""
        animas_dir = request.app.state.animas_dir
        anima_dir = animas_dir / name
        if not anima_dir.exists():
            raise HTTPException(status_code=404, detail=f"Anima not found: {name}")

        from core.config.models import load_model_config

        model_config = load_model_config(anima_dir)

        conv = ConversationMemory(anima_dir, model_config)
        messages = conv.load_transcript(date)
        return {
            "anima": name,
            "date": date,
            "has_summary": False,
            "compressed_summary": "",
            "compressed_turn_count": 0,
            "turns": messages,
        }

    return router
