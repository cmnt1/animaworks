# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Meeting room API routes with SSE streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from core.config import load_config
from core.exceptions import AnimaNotFoundError
from core.exceptions import IPCConnectionError as IPCConnError
from core.execution.base import strip_thinking_tags
from core.paths import get_common_knowledge_dir, get_shared_dir
from server.project_tasks import grouped_project_tasks
from server.room_manager import MeetingRoom, RoomManager
from server.routes.chat_chunk_handler import _chunk_to_event, _format_sse
from server.routes.chat_emotion import extract_emotion

logger = logging.getLogger(__name__)
# Meeting turns may now use read-only tools to verify before answering, so a
# speaker's whole stream needs a larger wall-clock budget than the old
# reference-only turns. Keep the child-side continuation deadline
# (_agent_cycle._MEETING_CONT_DEADLINE_S) comfortably under MIN.
MEETING_MIN_STREAM_TIMEOUT = 180.0
MEETING_MAX_STREAM_TIMEOUT = 300.0
MEETING_CONTEXT_MAX_MESSAGES = 8
MEETING_CONTEXT_MAX_CHARS = 6000
MEETING_CONTEXT_ENTRY_MAX_CHARS = 900
MEETING_TASK_CONTEXT_MAX_CHARS = 4000


async def _with_wall_timeout(stream: AsyncIterator[Any], timeout: float) -> AsyncIterator[Any]:
    async with asyncio.timeout(timeout):
        async for item in stream:
            yield item


# ── Active round registry ────────────────────────────────────
#
# A meeting round (chair → participants) can take many minutes.  It runs as a
# background task so a client reload or network blip does not abort the
# remaining speakers.  Connected clients subscribe to the round's event feed;
# a reloaded client re-attaches via GET /rooms/{room_id}/chat/attach and polls
# state from the room payload's "active_round" field.

ROUND_STATUS_INTERVAL_S = 5.0

_SSE_EVENT_RE = re.compile(r"^event: (?P<event>[^\n]+)\ndata: (?P<data>.*)\n\n$", re.DOTALL)


def _parse_sse_event(frame: str) -> tuple[str, dict[str, Any]]:
    """Recover (event, payload) from a frame produced by _format_sse."""
    m = _SSE_EVENT_RE.match(frame)
    if not m:
        return "", {}
    try:
        payload = json.loads(m.group("data"))
    except json.JSONDecodeError:
        payload = {}
    return m.group("event"), payload if isinstance(payload, dict) else {}


class _ActiveRound:
    """State + subscriber fan-out for one in-flight meeting round."""

    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self.task: asyncio.Task[None] | None = None
        self.listeners: set[asyncio.Queue[str | None]] = set()
        self.speakers: list[str] = []
        self.completed: list[str] = []
        self.current_speaker: str = ""
        self.started_at: float = time.monotonic()
        self.speaker_started_at: float | None = None
        self.done = False

    def subscribe(self) -> asyncio.Queue[str | None]:
        q: asyncio.Queue[str | None] = asyncio.Queue()
        self.listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str | None]) -> None:
        self.listeners.discard(q)

    def publish(self, frame: str | None) -> None:
        for q in list(self.listeners):
            q.put_nowait(frame)

    def note_event(self, event: str, payload: dict[str, Any]) -> None:
        """Track round progress from the SSE event flow."""
        if event == "speaker_queue":
            self.speakers = [str(s) for s in (payload.get("speakers") or [])]
        elif event == "speaker_start":
            speaker = str(payload.get("speaker") or "")
            self.current_speaker = speaker
            self.speaker_started_at = time.monotonic()
            if speaker and speaker not in self.speakers:
                self.speakers.append(speaker)  # redirect targets join mid-round
        elif event == "speaker_end":
            speaker = str(payload.get("speaker") or "")
            if speaker and speaker not in self.completed:
                self.completed.append(speaker)
            self.current_speaker = ""
            self.speaker_started_at = None

    def status_payload(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "active": not self.done,
            "current_speaker": self.current_speaker,
            "speakers": list(self.speakers),
            "completed": list(self.completed),
            "remaining": [s for s in self.speakers if s != self.current_speaker and s not in self.completed],
            "round_elapsed_s": round(now - self.started_at, 1),
            "speaker_elapsed_s": (
                round(now - self.speaker_started_at, 1) if self.speaker_started_at is not None else None
            ),
        }


_ACTIVE_ROUNDS: dict[str, _ActiveRound] = {}


async def _run_meeting_round(
    round_: _ActiveRound,
    room_id: str,
    message: str,
    from_person: str,
    room_manager: RoomManager,
    supervisor: Any,
) -> None:
    """Drive one meeting round to completion, independent of any client."""

    async def _ticker() -> None:
        while not round_.done:
            await asyncio.sleep(ROUND_STATUS_INTERVAL_S)
            if round_.done:
                return
            round_.publish(_format_sse("round_status", round_.status_payload()))

    ticker = asyncio.create_task(_ticker())
    try:
        async for frame in _meeting_stream(room_id, message, from_person, room_manager, supervisor):
            event, payload = _parse_sse_event(frame)
            round_.note_event(event, payload)
            round_.publish(frame)
    except Exception:
        logger.exception("Meeting round failed for room %s", room_id)
        round_.publish(
            _format_sse(
                "error",
                {"code": "ROUND_FAILED", "message": "Meeting round failed unexpectedly"},
            )
        )
        round_.publish(_format_sse("done", {"summary": "Meeting round aborted"}))
    finally:
        round_.done = True
        ticker.cancel()
        round_.publish(None)  # sentinel: close all listener feeds
        if _ACTIVE_ROUNDS.get(room_id) is round_:
            _ACTIVE_ROUNDS.pop(room_id, None)


def _start_meeting_round(
    room_id: str,
    message: str,
    from_person: str,
    room_manager: RoomManager,
    supervisor: Any,
) -> _ActiveRound:
    """Register and launch a background round. Raises 409 if one is running."""
    existing = _ACTIVE_ROUNDS.get(room_id)
    if existing is not None and not existing.done:
        raise HTTPException(status_code=409, detail="A meeting round is already in progress for this room")
    round_ = _ActiveRound(room_id)
    _ACTIVE_ROUNDS[room_id] = round_
    round_.task = asyncio.create_task(
        _run_meeting_round(round_, room_id, message, from_person, room_manager, supervisor)
    )
    return round_


async def _round_event_feed(
    round_: _ActiveRound,
    *,
    snapshot: bool,
    queue: asyncio.Queue[str | None] | None = None,
) -> AsyncIterator[str]:
    """Yield SSE frames from an active round until it completes.

    Disconnecting a feed only unsubscribes this listener; the round task
    keeps running and its messages keep landing in the room history.

    Pass a pre-subscribed *queue* to guarantee no events are missed between
    starting the round and consuming the response (subscription must happen
    synchronously before the round task first runs).
    """
    fresh_subscription = queue is None
    q = round_.subscribe() if queue is None else queue
    try:
        if snapshot:
            yield _format_sse("round_status", round_.status_payload())
        if fresh_subscription and round_.done:
            # Subscribed after completion: the sentinel was already published,
            # so the queue would never terminate — finish immediately instead.
            yield _format_sse("done", {"summary": "Meeting round complete"})
            return
        while True:
            frame = await q.get()
            if frame is None:
                return
            yield frame
    finally:
        round_.unsubscribe(q)


# ── Pydantic Models ──────────────────────────────────────────


class CreateRoomRequest(BaseModel):
    """Request body for creating a meeting room."""

    participants: list[str]
    chair: str
    title: str = ""
    project_department: str = ""
    project_task_code: str = ""
    project_note_path: str = ""
    project_task_title: str = ""

    @field_validator("participants")
    @classmethod
    def validate_participants(cls, v: list[str]) -> list[str]:
        if len(v) > 5:
            raise ValueError("Maximum 5 participants")
        if len(v) < 1:
            raise ValueError("At least 1 participant required")
        return v


class MeetingChatRequest(BaseModel):
    """Request body for meeting chat stream."""

    message: str
    from_person: str = "human"


class AddParticipantRequest(BaseModel):
    """Request body for adding a participant."""

    name: str


class SetChairRequest(BaseModel):
    """Request body for reassigning the meeting chair."""

    name: str


class UpdateRoomRequest(BaseModel):
    """Request body for updating meeting room metadata."""

    title: str = ""


class ArchiveRoomRequest(BaseModel):
    """Request body for archiving/unarchiving a meeting room."""

    archived: bool = True


class ActionItemInput(BaseModel):
    """A single action item from the confirmation UI."""

    assignee: str = ""
    text: str = ""


class ActionItemsRequest(BaseModel):
    """Request body for saving the confirmed action item list."""

    items: list[ActionItemInput] = []


# ── Helpers ─────────────────────────────────────────────────


def _ensure_project_thread_for_room(
    task_code: str,
    task_title: str,
    department: str,
    room_title: str,
    action_items: list[dict],
) -> None:
    """会議クローズ時にプロジェクト専用 Discord スレッドを確立し、キックオフを投稿する.

    以後、タスクコードに言及する board 投稿は BoardDiscordSync がこのスレッドへ
    ルーティングする (core/project_threads.py)。失敗しても close は妨げない。
    """
    try:
        from core.project_threads import ensure_project_thread, resolve_thread_for_code

        already = resolve_thread_for_code(task_code.strip())
        lines = [f"**[{task_code}] {task_title or room_title}** のミーティングがクローズされました。"]
        if action_items:
            lines.append("")
            lines.append("**アクションアイテム:**")
            for item in action_items:
                assignee = item.get("assignee", "?")
                text = (item.get("text") or "")[:200]
                lines.append(f"- {assignee}: {text}")
        lines.append("")
        lines.append(f"以後、{task_code} に関する報告・進捗はこのスレッドに集約されます。")
        kickoff = "\n".join(lines)

        result = ensure_project_thread(
            task_code,
            title=task_title or room_title,
            department=department,
            kickoff_text=kickoff,
        )
        if result and already:
            # 既存スレッド再利用時もクローズ通知は流す
            from core.discord_webhooks import get_webhook_manager

            channel_id, thread_id = result
            get_webhook_manager().send_as_anima(channel_id, "AnimaWorks 会議", kickoff, thread_id=thread_id)
    except Exception:
        logger.exception("Project thread setup failed for %s", task_code)


def _get_room_manager(request: Request) -> RoomManager:
    """Get RoomManager from app state. Raises 503 if not available."""
    room_manager = getattr(request.app.state, "room_manager", None)
    if room_manager is None:
        raise HTTPException(
            status_code=503,
            detail="Meeting room feature not available",
        )
    return room_manager


def _get_created_by(request: Request) -> str:
    """Get created_by from authenticated user or default to 'human'."""
    if hasattr(request.state, "user"):
        return request.state.user.username
    return "human"


def _room_payload(room: MeetingRoom, *, include_conversation: bool = False) -> dict[str, Any]:
    """Serialize a meeting room for API responses."""
    payload: dict[str, Any] = {
        "room_id": room.room_id,
        "participants": room.participants,
        "chair": room.chair,
        "title": room.title,
        "created_at": room.created_at.isoformat(),
        "closed": room.closed,
        "archived": room.archived,
        "closed_at": room.closed_at.isoformat() if room.closed_at else None,
        "project_department": room.project_department,
        "project_task_code": room.project_task_code,
        "project_note_path": room.project_note_path,
        "project_task_title": room.project_task_title,
        "action_items": room.action_items,
    }
    active = _ACTIVE_ROUNDS.get(room.room_id)
    payload["active_round"] = active.status_payload() if active is not None and not active.done else None
    if include_conversation:
        payload["conversation"] = room.conversation
    return payload


def _is_all_participants_request(message: str) -> bool:
    """Return True when the latest user message asks everyone to respond."""
    normalized = message.lower()
    markers = (
        "@all",
        "everyone",
        "everybody",
        "all participants",
        "each participant",
        "each of you",
        "\u305d\u308c\u305e\u308c",  # それぞれ
        "\u5168\u54e1",  # 全員
        "\u5404\u81ea",  # 各自
        "\u307f\u3093\u306a",  # みんな
        "\u4e00\u4eba\u305a\u3064",  # 一人ずつ
        "\u5404\u30e1\u30f3\u30d0\u30fc",  # 各メンバー
    )
    return any(marker in normalized for marker in markers)


def _truncate_text(text: str, max_chars: int) -> str:
    """Trim long meeting entries so one verbose turn cannot dominate the prompt."""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[truncated]"


def _build_compact_meeting_context(room: MeetingRoom) -> str:
    """Build bounded meeting context without invoking another LLM.

    Meeting turns must be low-latency. The normal summarizer can call an
    external SDK and, when that fails, falls back to very large history. Keep
    this path deterministic and capped.
    """
    entries = room.conversation[-MEETING_CONTEXT_MAX_MESSAGES:]
    formatted_entries: list[str] = []
    for entry in entries:
        speaker = str(entry.get("speaker") or "")
        role = str(entry.get("role") or "")
        text = _truncate_text(str(entry.get("text") or ""), MEETING_CONTEXT_ENTRY_MAX_CHARS)
        if not text:
            continue
        label = f"{speaker} ({role})" if role else speaker
        formatted_entries.append(f"[{label}] {text}")

    selected: list[str] = []
    total = 0
    truncated = False
    for line in reversed(formatted_entries):
        added = len(line) + (1 if selected else 0)
        if selected and total + added > MEETING_CONTEXT_MAX_CHARS:
            truncated = True
            break
        if not selected and added > MEETING_CONTEXT_MAX_CHARS:
            selected.append(_truncate_text(line, MEETING_CONTEXT_MAX_CHARS))
            truncated = len(line) > MEETING_CONTEXT_MAX_CHARS
            break
        selected.append(line)
        total += added

    selected.reverse()
    context = "\n".join(selected).strip()
    return f"[older meeting context truncated]\n{context}" if truncated else context


def _build_meeting_task_context(room: MeetingRoom) -> str:
    """Return bounded project/task context for the meeting prompt.

    This is deliberate preloaded meeting material, not an invitation for the
    Anima to browse files or search memory during its speaking turn.
    """
    lines: list[str] = []
    if room.project_department:
        lines.append(f"- Department: {room.project_department}")
    if room.project_task_code:
        title = f" {room.project_task_title}" if room.project_task_title else ""
        lines.append(f"- Task: {room.project_task_code}{title}")

    note_excerpt = ""
    if room.project_note_path:
        try:
            note_path = Path(room.project_note_path)
            if note_path.is_file():
                note_excerpt = _truncate_text(
                    note_path.read_text(encoding="utf-8", errors="replace"), MEETING_TASK_CONTEXT_MAX_CHARS
                )
        except OSError:
            logger.warning("Failed to read meeting project note: %s", room.project_note_path, exc_info=True)

    if note_excerpt:
        lines.append("\nProject note excerpt:\n" + note_excerpt)

    if not lines:
        return ""

    return "\n".join(
        [
            "Meeting task context (reference; you may also verify with read-only tools before answering):",
            *lines,
        ]
    )


async def _build_message_for_anima(
    room_manager: RoomManager,
    room: MeetingRoom,
    target_name: str,
    human_message: str,
    *,
    is_chair: bool,
) -> str:
    """Build the message content sent to an Anima in the meeting context.

    Includes meeting context (conversation history) and role-specific prompt.
    """
    context = _build_compact_meeting_context(room)
    task_context = _build_meeting_task_context(room)
    target_directive = f"""Meeting response directive:
- You are {target_name}; answer as yourself, not as another participant.
- Latest human request: {human_message}
- If the latest request asks everyone/every participant to respond, give your own direct response now.
- Do not repeat, summarize, or endorse the previous participant's response unless you add a distinct point.
- Do not say you are waiting for the chair unless the human explicitly asked you to wait.
- If a fact can be checked, verify it FIRST with read-only tools (Read/Grep/Glob, the Obsidian vault, memory search) and answer from what you actually find this turn. Prefer fresh verification over reusing data fetched in an earlier turn. File writes/edits and external messaging are disabled for this turn.
- Always produce a visible final reply; never finish with only thinking/internal reasoning.
- Keep the response concise and actionable."""
    context = f"{target_directive}\n\n{context}" if context else target_directive
    task_section = f"\n\n## タスク前提\n\n{task_context}" if task_context else ""
    if is_chair:
        chair_prompt = room_manager.build_chair_prompt(room)
        return f"""{target_directive}

{chair_prompt}
{task_section}

## 会議の流れ

{context or "(まだ発言なし)"}

上記の会議の流れを踏まえて、議長として応答してください。"""
    else:
        return f"""あなたは会議に参加しています。以下の会議の流れを踏まえて意見を述べてください。
{task_section}

## 会議の流れ

{context or "(まだ発言なし)"}

上記の会議の流れに対して、あなたの意見を述べてください。"""


async def _meeting_stream(
    room_id: str,
    message: str,
    from_person: str,
    room_manager: RoomManager,
    supervisor: Any,
) -> AsyncIterator[str]:
    """Async generator yielding SSE events for meeting chat round."""
    room = room_manager.get_room(room_id)
    if room is None:
        yield _format_sse("error", {"code": "ROOM_NOT_FOUND", "message": "Room not found"})
        return
    if room.closed:
        yield _format_sse("error", {"code": "ROOM_CLOSED", "message": "Room is closed"})
        return

    # Append human message to conversation
    room_manager.append_message(room_id, from_person, "human", message)

    # Determine targets: @mentions, everyone-request, or meeting round.
    mentions = room_manager.extract_mentions(message, room.participants)
    if mentions:
        targets = [t for t in mentions if t in room.participants]
    elif len(room.participants) > 1:
        # Chair speaks first to coordinate the round; remaining participants
        # follow. Chair-first keeps the redirect/@mention flow coherent
        # (the chair can pull a specific participant in via redirect).
        targets = [room.chair] if room.chair in room.participants else []
        targets += [t for t in room.participants if t != room.chair]
    else:
        targets = [room.chair] if room.chair in room.participants else []

    if not targets:
        yield _format_sse("done", {"summary": "No targets to respond"})
        return

    yield _format_sse("speaker_queue", {"speakers": targets})

    # Verify all targets exist in supervisor
    for t in targets:
        if t not in supervisor.processes:
            yield _format_sse(
                "error",
                {"code": "ANIMA_NOT_FOUND", "message": f"Anima not found: {t}"},
            )
            return

    try:
        _config = load_config()
        _timeout = float(_config.server.ipc_stream_timeout)
    except Exception:
        _timeout = MEETING_MIN_STREAM_TIMEOUT
    _timeout = min(max(_timeout, MEETING_MIN_STREAM_TIMEOUT), MEETING_MAX_STREAM_TIMEOUT)

    queue: list[str] = list(targets)
    processed_targets: set[str] = set()
    prev_speaker = from_person

    while queue:
        target_name = queue.pop(0)
        is_chair = target_name == room.chair

        # Build message for this target
        msg_content = await _build_message_for_anima(
            room_manager,
            room,
            target_name,
            message,
            is_chair=is_chair,
        )

        params: dict[str, Any] = {
            "message": msg_content,
            "from_person": prev_speaker,
            "stream": True,
            "source": "meeting",
            "thread_id": f"meeting-{room_id}",
            "meeting_room_id": room_id,
            "meeting_participants": room.participants,
        }

        # Yield speaker_start
        role = "chair" if is_chair else "participant"
        yield _format_sse("speaker_start", {"speaker": target_name, "role": role})

        full_response = ""
        text_delta_seen = False
        speaker_failed = False

        try:
            async for ipc_response in _with_wall_timeout(
                supervisor.send_request_stream(
                    anima_name=target_name,
                    method="process_message",
                    params=params,
                    timeout=_timeout,
                ),
                _timeout,
            ):
                if ipc_response.error:
                    err = ipc_response.error
                    speaker_failed = True
                    yield _format_sse(
                        "error",
                        {
                            "code": err.get("code", "STREAM_ERROR"),
                            "message": err.get("message", "Stream error"),
                            "speaker": target_name,
                        },
                    )
                    break

                if ipc_response.done:
                    result = ipc_response.result or {}
                    done_response = result.get("response", "")
                    cycle_result = result.get("cycle_result", {})
                    if cycle_result and not done_response:
                        done_response = cycle_result.get("summary", "")
                    if done_response and not text_delta_seen:
                        full_response = done_response
                    break

                if ipc_response.chunk:
                    try:
                        chunk_data = json.loads(ipc_response.chunk)
                        if chunk_data.get("type") == "keepalive":
                            continue
                        result = _chunk_to_event(chunk_data)
                        if result:
                            evt_name, evt_payload = result
                            # Don't yield "done" from cycle_done — we yield our own at the end
                            if evt_name == "done":
                                if not text_delta_seen:
                                    full_response = evt_payload.get("summary", full_response) or full_response
                                continue
                            if evt_name == "meeting_redirect":
                                redirect_from = str(evt_payload.get("from") or target_name)
                                redirect_to = str(evt_payload.get("to") or "")
                                redirect_content = str(evt_payload.get("content") or "")
                                redirect_id = str(evt_payload.get("redirect_id") or "")
                                if redirect_to in room.participants and redirect_content:
                                    try:
                                        room_manager.append_meeting_redirect(
                                            room_id,
                                            from_name=redirect_from,
                                            to_name=redirect_to,
                                            content=redirect_content,
                                            intent=str(evt_payload.get("intent") or ""),
                                            redirect_id=redirect_id,
                                        )
                                    except ValueError:
                                        logger.warning(
                                            "Meeting redirect persistence failed for room %s: %s -> %s",
                                            room_id,
                                            redirect_from,
                                            redirect_to,
                                            exc_info=True,
                                        )
                                    if (
                                        redirect_to != target_name
                                        and redirect_to in room.participants
                                        and redirect_to not in processed_targets
                                        and redirect_to not in queue
                                    ):
                                        queue.append(redirect_to)
                                evt_payload = dict(evt_payload)
                                evt_payload["speaker"] = redirect_from
                                yield _format_sse(evt_name, evt_payload)
                                continue
                            evt_payload = dict(evt_payload)
                            evt_payload["speaker"] = target_name
                            yield _format_sse(evt_name, evt_payload)
                            if evt_name == "text_delta":
                                text_delta_seen = True
                                full_response += evt_payload.get("text", "")
                    except json.JSONDecodeError:
                        text_delta_seen = True
                        yield _format_sse(
                            "text_delta",
                            {"text": ipc_response.chunk, "speaker": target_name},
                        )
                        full_response += ipc_response.chunk

                if ipc_response.result and not full_response:
                    full_response = ipc_response.result.get("response", "")

        except TimeoutError:
            speaker_failed = True
            logger.warning("Meeting stream timed out for %s after %.1fs", target_name, _timeout)
            yield _format_sse(
                "error",
                {
                    "code": "STREAM_TIMEOUT",
                    "message": f"Timed out waiting for {target_name} after {_timeout:.0f}s",
                    "speaker": target_name,
                },
            )
            full_response = ""
        except (AnimaNotFoundError, IPCConnError) as e:
            speaker_failed = True
            logger.warning("Meeting stream error for %s: %s", target_name, e)
            yield _format_sse(
                "error",
                {"code": "STREAM_ERROR", "message": str(e), "speaker": target_name},
            )
            full_response = ""

        # Clean response for storage
        clean_text, _ = extract_emotion(full_response)
        leaked, clean_text = strip_thinking_tags(clean_text)
        if leaked:
            clean_text = clean_text.strip()
        clean_text = clean_text.strip()

        if clean_text:
            # Append to conversation
            room_manager.append_message(
                room_id,
                target_name,
                "chair" if is_chair else "participant",
                clean_text,
            )
        elif not speaker_failed:
            speaker_failed = True
            yield _format_sse(
                "error",
                {
                    "code": "EMPTY_RESPONSE",
                    "message": f"No response from {target_name}",
                    "speaker": target_name,
                },
            )

        # Yield speaker_end
        yield _format_sse("speaker_end", {"speaker": target_name})

        processed_targets.add(target_name)
        prev_speaker = target_name

        # After chair responds: extract @mentions and add as next targets
        if is_chair and clean_text:
            new_mentions = room_manager.extract_mentions(clean_text, room.participants)
            for m in new_mentions:
                if m != target_name and m in room.participants and m not in processed_targets and m not in queue:
                    queue.append(m)
        elif is_chair and speaker_failed:
            for participant in room.participants:
                if participant != target_name and participant not in processed_targets and participant not in queue:
                    queue.append(participant)

    yield _format_sse("done", {"summary": "Meeting round complete"})


# ── Router ───────────────────────────────────────────────────


def create_room_router() -> APIRouter:
    """Create the meeting room API router."""
    router = APIRouter(prefix="/rooms", tags=["rooms"])

    @router.post("")
    async def create_room(body: CreateRoomRequest, request: Request):
        """Create a new meeting room."""
        room_manager = _get_room_manager(request)
        created_by = _get_created_by(request)
        try:
            room = room_manager.create_room(
                participants=body.participants,
                chair=body.chair,
                created_by=created_by,
                title=body.title,
                project_department=body.project_department,
                project_task_code=body.project_task_code,
                project_note_path=body.project_note_path,
                project_task_title=body.project_task_title,
            )
            return _room_payload(room)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

    @router.get("")
    async def list_rooms(request: Request, include_closed: bool = False, include_archived: bool = False):
        """List meeting rooms."""
        room_manager = _get_room_manager(request)
        rooms = room_manager.list_rooms(include_closed=include_closed, include_archived=include_archived)
        return [
            _room_payload(r)
            | {
                "message_count": len(r.conversation),
                "last_message_at": r.conversation[-1].get("ts") if r.conversation else r.created_at.isoformat(),
            }
            for r in rooms
        ]

    @router.get("/project-tasks")
    async def list_project_tasks(include_completed: bool = False):
        """List selectable Obsidian Projects DB tasks."""
        return grouped_project_tasks(include_completed=include_completed)

    @router.get("/{room_id}")
    async def get_room(room_id: str, request: Request):
        """Get room details including conversation."""
        room_manager = _get_room_manager(request)
        room = room_manager.get_room(room_id)
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found")
        return _room_payload(room, include_conversation=True)

    @router.patch("/{room_id}")
    async def update_room(room_id: str, body: UpdateRoomRequest, request: Request):
        """Update room metadata such as title."""
        room_manager = _get_room_manager(request)
        try:
            room = room_manager.update_room_title(room_id, body.title)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        return _room_payload(room, include_conversation=True)

    @router.post("/{room_id}/participants")
    async def add_participant(room_id: str, body: AddParticipantRequest, request: Request):
        """Add a participant to the room."""
        room_manager = _get_room_manager(request)
        try:
            room_manager.add_participant(room_id, body.name)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

    @router.delete("/{room_id}/participants/{name}")
    async def remove_participant(room_id: str, name: str, request: Request):
        """Remove a participant from the room."""
        room_manager = _get_room_manager(request)
        try:
            room_manager.remove_participant(room_id, name)
            return {"ok": True}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

    @router.put("/{room_id}/chair")
    async def set_chair(room_id: str, body: SetChairRequest, request: Request):
        """Reassign the meeting chair (takes effect from the next round)."""
        room_manager = _get_room_manager(request)
        try:
            room = room_manager.set_chair(room_id, body.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        return _room_payload(room)

    @router.post("/{room_id}/close")
    async def close_room(room_id: str, request: Request):
        """Close room and generate minutes."""
        room_manager = _get_room_manager(request)
        try:
            room_manager.close_room(room_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None

        # Project meeting: ensure a dedicated Discord thread exists and post
        # the kickoff summary (fire-and-forget; failures never block close).
        room = room_manager.get_room(room_id)
        if room is not None and room.project_task_code:
            asyncio.create_task(
                asyncio.to_thread(
                    _ensure_project_thread_for_room,
                    room.project_task_code,
                    room.project_task_title,
                    room.project_department,
                    room.title,
                    list(room.action_items or []),
                )
            )

        # Generate minutes
        try:
            common_knowledge_dir = get_common_knowledge_dir()
            minutes_path = await room_manager.generate_minutes(room_id, common_knowledge_dir)
            return {
                "ok": True,
                "minutes_path": str(minutes_path) if minutes_path else None,
            }
        except Exception as e:
            logger.warning("Failed to generate minutes for room %s: %s", room_id, e)
            return {"ok": True, "minutes_path": None}

    @router.post("/{room_id}/archive")
    async def archive_room(room_id: str, body: ArchiveRoomRequest, request: Request):
        """Archive or unarchive a meeting room."""
        room_manager = _get_room_manager(request)
        try:
            room = room_manager.set_room_archived(room_id, body.archived)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        return _room_payload(room)

    @router.delete("/{room_id}")
    async def delete_room(room_id: str, request: Request):
        """Delete a meeting room permanently."""
        room_manager = _get_room_manager(request)
        try:
            room_manager.delete_room(room_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        return {"ok": True}

    @router.post("/{room_id}/action-items/extract")
    async def extract_action_items(room_id: str, request: Request):
        """Draft action items from the transcript via LLM (not persisted)."""
        room_manager = _get_room_manager(request)
        try:
            items = await room_manager.extract_action_items(room_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from None
        return {"items": items}

    @router.put("/{room_id}/action-items")
    async def save_action_items(room_id: str, body: ActionItemsRequest, request: Request):
        """Persist the confirmed action item list."""
        room_manager = _get_room_manager(request)
        items = [{"assignee": i.assignee, "text": i.text} for i in body.items]
        try:
            room = room_manager.set_action_items(room_id, items)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        return _room_payload(room)

    @router.post("/{room_id}/action-items/dispatch")
    async def dispatch_action_items(room_id: str, request: Request):
        """Deliver unsent action items to each assignee's inbox."""
        room_manager = _get_room_manager(request)
        try:
            delivered = room_manager.dispatch_action_items(room_id, get_shared_dir())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
        return {"ok": True, "delivered": delivered}

    @router.post("/{room_id}/chat/stream")
    async def meeting_chat_stream(
        room_id: str,
        body: MeetingChatRequest,
        request: Request,
    ):
        """Start a meeting round and stream its SSE events.

        The round itself runs as a background task, so a client disconnect
        (page reload, network blip) does not abort the remaining speakers.
        Returns 409 while a round is already in progress for the room.
        """
        room_manager = _get_room_manager(request)
        supervisor = request.app.state.supervisor

        from_person = body.from_person
        if hasattr(request.state, "user"):
            from_person = request.state.user.username

        round_ = _start_meeting_round(
            room_id,
            body.message,
            from_person,
            room_manager,
            supervisor,
        )
        # Subscribe synchronously so no early events are lost before the
        # response body starts being consumed.
        listener = round_.subscribe()
        return StreamingResponse(
            _round_event_feed(round_, snapshot=False, queue=listener),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/{room_id}/chat/attach")
    async def meeting_chat_attach(room_id: str, request: Request):
        """Re-attach to an in-flight meeting round after a reload.

        Emits an immediate round_status snapshot, then live events until the
        round completes.  When no round is active, emits done immediately —
        the caller should render from the room conversation instead.
        """
        _get_room_manager(request)  # 503 guard when feature unavailable

        round_ = _ACTIVE_ROUNDS.get(room_id)
        if round_ is None or round_.done:

            async def _no_round() -> AsyncIterator[str]:
                yield _format_sse("round_status", {"active": False})
                yield _format_sse("done", {"summary": "No active round"})

            feed = _no_round()
        else:
            feed = _round_event_feed(round_, snapshot=True)

        return StreamingResponse(
            feed,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
