# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Meeting room lifecycle, orchestration, and minutes generation."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from core.i18n import t

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────

MAX_PARTICIPANTS = 5
DEFAULT_MAX_CONTEXT_MESSAGES = 50
SUMMARY_THRESHOLD = 5
_ROOM_ID_RE = re.compile(r"^[a-f0-9]{12}$")

# ── Data Model ──────────────────────────────────────────────


@dataclass
class MeetingRoom:
    """A meeting room with participants, chair, and shared conversation."""

    room_id: str
    participants: list[str]  # Anima names
    chair: str  # Chair Anima name
    created_by: str  # Human user name
    created_at: datetime
    conversation: list[dict]  # Shared conversation history
    # Each entry: {"speaker": "sakura", "role": "chair"|"participant"|"human", "text": "...", "ts": "ISO8601"}
    closed: bool = False
    archived: bool = False
    title: str = ""
    closed_at: datetime | None = None
    project_department: str = ""
    project_task_code: str = ""
    project_note_path: str = ""
    project_task_title: str = ""
    action_items: list[dict] = field(default_factory=list)
    # Each entry: {"id": str, "assignee": str, "text": str, "status": "draft"|"sent"}

    def to_dict(self) -> dict:
        """Serialize for JSON persistence."""
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        if self.closed_at is not None:
            d["closed_at"] = self.closed_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> MeetingRoom:
        """Deserialize from JSON."""
        created_at = datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"]
        closed_at = None
        if d.get("closed_at"):
            closed_at = datetime.fromisoformat(d["closed_at"]) if isinstance(d["closed_at"], str) else d["closed_at"]
        return cls(
            room_id=d["room_id"],
            participants=d["participants"],
            chair=d["chair"],
            created_by=d["created_by"],
            created_at=created_at,
            conversation=d.get("conversation", []),
            closed=d.get("closed", False),
            archived=d.get("archived", False),
            title=d.get("title", ""),
            closed_at=closed_at,
            project_department=d.get("project_department", ""),
            project_task_code=d.get("project_task_code", ""),
            project_note_path=d.get("project_note_path", ""),
            project_task_title=d.get("project_task_title", ""),
            action_items=d.get("action_items", []),
        )


# ── RoomManager ─────────────────────────────────────────────


class RoomManager:
    """Manages meeting room lifecycle and orchestration."""

    def __init__(self, data_dir: Path) -> None:
        """Initialize the room manager.

        Args:
            data_dir: Base directory for room persistence, e.g. ~/.animaworks/shared/meetings/
        """
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._rooms: dict[str, MeetingRoom] = {}
        self._lock = asyncio.Lock()

    # ── Room CRUD ───────────────────────────────────────────

    def create_room(
        self,
        participants: list[str],
        chair: str,
        created_by: str,
        title: str = "",
        project_department: str = "",
        project_task_code: str = "",
        project_note_path: str = "",
        project_task_title: str = "",
    ) -> MeetingRoom:
        """Create a new meeting room.

        Args:
            participants: List of Anima names.
            chair: Chair Anima name (must be in participants).
            created_by: Human user name who created the room.
            title: Optional meeting title.
            project_department: Projects DB category/department.
            project_task_code: Projects DB task code.
            project_note_path: Source Obsidian note path.
            project_task_title: Projects DB task title.

        Returns:
            The created MeetingRoom.

        Raises:
            ValueError: If participants exceed MAX_PARTICIPANTS or chair not in participants.
        """
        if len(participants) > MAX_PARTICIPANTS:
            raise ValueError(t("room_manager.max_participants_exceeded", max_n=MAX_PARTICIPANTS))
        if chair not in participants:
            raise ValueError(t("room_manager.chair_not_in_participants"))
        room_id = uuid.uuid4().hex[:12]
        now = datetime.now()
        room = MeetingRoom(
            room_id=room_id,
            participants=list(participants),
            chair=chair,
            created_by=created_by,
            created_at=now,
            conversation=[],
            closed=False,
            title=title,
            project_department=project_department,
            project_task_code=project_task_code,
            project_note_path=project_note_path,
            project_task_title=project_task_title,
        )
        self._rooms[room_id] = room
        self.save_room(room_id)
        logger.info("Created meeting room %s (chair=%s, participants=%s)", room_id, chair, participants)
        return room

    @staticmethod
    def _validate_room_id(room_id: str) -> None:
        """Validate room_id to prevent path traversal."""
        if not _ROOM_ID_RE.match(room_id):
            raise ValueError(f"Invalid room_id: {room_id!r}")

    def get_room(self, room_id: str) -> MeetingRoom | None:
        """Get a room by ID."""
        return self._rooms.get(room_id)

    def update_room_title(self, room_id: str, title: str) -> MeetingRoom:
        """Update a room title and persist it."""
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(t("room_manager.room_not_found", room_id=room_id))
        room.title = title.strip()
        self.save_room(room_id)
        logger.info("Updated meeting room %s title", room_id)
        return room

    def list_rooms(self, include_closed: bool = False, include_archived: bool = False) -> list[MeetingRoom]:
        """List rooms, optionally including closed and/or archived ones."""
        rooms = list(self._rooms.values())
        if not include_archived:
            rooms = [r for r in rooms if not r.archived]
        if not include_closed:
            rooms = [r for r in rooms if not r.closed]
        return rooms

    def set_room_archived(self, room_id: str, archived: bool) -> MeetingRoom:
        """Archive or unarchive a room and persist it."""
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(t("room_manager.room_not_found", room_id=room_id))
        room.archived = archived
        self.save_room(room_id)
        logger.info("Set room %s archived=%s", room_id, archived)
        return room

    def delete_room(self, room_id: str) -> None:
        """Delete a room from memory and disk."""
        self._validate_room_id(room_id)
        self._rooms.pop(room_id, None)
        path = self._data_dir / f"{room_id}.json"
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to delete room file %s", path, exc_info=True)
        logger.info("Deleted room %s", room_id)

    def add_participant(self, room_id: str, name: str) -> None:
        """Add a participant to the room.

        Args:
            room_id: Room ID.
            name: Anima name to add.

        Raises:
            ValueError: If room not found, room closed, or room full (max 5).
        """
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(t("room_manager.room_not_found", room_id=room_id))
        if room.closed:
            raise ValueError(t("room_manager.room_closed"))
        if len(room.participants) >= MAX_PARTICIPANTS:
            raise ValueError(t("room_manager.max_participants_exceeded", max_n=MAX_PARTICIPANTS))
        if name in room.participants:
            return
        room.participants.append(name)
        self.save_room(room_id)
        logger.info("Added participant %s to room %s", name, room_id)

    def remove_participant(self, room_id: str, name: str) -> None:
        """Remove a participant from the room.

        If the chair is removed, reassign chair to the first remaining participant.

        Args:
            room_id: Room ID.
            name: Anima name to remove.

        Raises:
            ValueError: If room not found or room closed.
        """
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(t("room_manager.room_not_found", room_id=room_id))
        if room.closed:
            raise ValueError(t("room_manager.room_closed"))
        if name not in room.participants:
            return
        room.participants.remove(name)
        if room.chair == name and room.participants:
            room.chair = room.participants[0]
            logger.info("Reassigned chair to %s in room %s", room.chair, room_id)
        elif room.chair == name and not room.participants:
            room.chair = ""
        self.save_room(room_id)
        logger.info("Removed participant %s from room %s", name, room_id)

    def close_room(self, room_id: str) -> None:
        """Close a room."""
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(t("room_manager.room_not_found", room_id=room_id))
        room.closed = True
        room.closed_at = datetime.now()
        self.save_room(room_id)
        logger.info("Closed room %s", room_id)

    # ── @mention extraction ────────────────────────────────

    def extract_mentions(self, text: str, participants: list[str]) -> list[str]:
        """Extract @mentions that match participant names.

        Case-insensitive: @Rin matches participant 'rin'.
        Returns list of mentioned participant names in order of first appearance,
        using original case from participants list.

        Args:
            text: Message text to scan.
            participants: List of participant names.

        Returns:
            List of mentioned participant names (in order of appearance).
        """
        seen: set[str] = set()
        result: list[str] = []
        # Build case-insensitive map: lower(name) -> name
        name_map = {p.lower(): p for p in participants}
        # Find @mentions (word after @)
        for m in re.finditer(r"@(\w+)", text, re.IGNORECASE):
            key = m.group(1).lower()
            if key in name_map and key not in seen:
                seen.add(key)
                result.append(name_map[key])
        return result

    # ── Conversation history ────────────────────────────────

    def append_message(
        self,
        room_id: str,
        speaker: str,
        role: str,
        text: str,
        *,
        meta: dict | None = None,
    ) -> None:
        """Append a message to the room's conversation history.

        Args:
            room_id: Room ID.
            speaker: Speaker name (Anima or human).
            role: One of 'chair', 'participant', 'human'.
            text: Message text.
            meta: Optional machine-readable metadata for non-standard entries.
        """
        from core.meeting_room_store import append_room_message

        if self.get_room(room_id) is None:
            raise ValueError(t("room_manager.room_not_found", room_id=room_id))
        append_room_message(
            self._data_dir,
            room_id,
            speaker,
            role,
            text,
            meta=meta,
        )
        self.load_room(room_id)

    def append_meeting_redirect(
        self,
        room_id: str,
        *,
        from_name: str,
        to_name: str,
        content: str,
        intent: str = "",
        redirect_id: str = "",
    ) -> None:
        """Append a meeting-local redirect to the room's conversation history."""
        from core.meeting_room_store import append_meeting_redirect

        if self.get_room(room_id) is None:
            raise ValueError(t("room_manager.room_not_found", room_id=room_id))
        append_meeting_redirect(
            self._data_dir,
            room_id,
            from_name=from_name,
            to_name=to_name,
            content=content,
            intent=intent,
            redirect_id=redirect_id,
        )
        self.load_room(room_id)

    @staticmethod
    def _format_entries(messages: list[dict]) -> str:
        """Format conversation entries into display strings."""
        lines: list[str] = []
        for entry in messages:
            speaker = entry.get("speaker", "")
            role = entry.get("role", "")
            text = entry.get("text", "")
            if role == "chair":
                lines.append(f"[{speaker}(議長)] {text}")
            elif role == "human":
                lines.append(f"[human({speaker})] {text}")
            else:
                lines.append(f"[{speaker}] {text}")
        return "\n".join(lines)

    def get_conversation_context(self, room_id: str, max_messages: int = DEFAULT_MAX_CONTEXT_MESSAGES) -> str:
        """Build conversation context string for sending to an Anima.

        If messages exceed max_messages, truncate older ones.
        """
        room = self.get_room(room_id)
        if room is None:
            return ""
        messages = room.conversation
        if len(messages) > max_messages:
            messages = messages[-max_messages:]
        return self._format_entries(messages)

    async def get_summarized_context(self, room_id: str) -> str:
        """Build conversation context with summarization for entries > SUMMARY_THRESHOLD.

        When conversation has more than SUMMARY_THRESHOLD entries, older entries
        are summarized via LLM and the result is formatted as:
        "[要約] <summary>\\n\\n<recent N entries verbatim>"

        Falls back to get_conversation_context() on any failure.
        """
        room = self.get_room(room_id)
        if room is None:
            return ""
        messages = room.conversation
        if len(messages) <= SUMMARY_THRESHOLD:
            return self.get_conversation_context(room_id)

        older = messages[:-SUMMARY_THRESHOLD]
        recent = messages[-SUMMARY_THRESHOLD:]

        cached_idx = getattr(room, "_summary_up_to", 0)
        cached_text = getattr(room, "_summary_text", "")
        if cached_idx == len(older) and cached_text:
            summary = cached_text
        else:
            try:
                summary = await self._call_summary_llm(older)
                room._summary_up_to = len(older)  # type: ignore[attr-defined]
                room._summary_text = summary  # type: ignore[attr-defined]
            except Exception:
                logger.warning("Meeting context summarization failed; falling back to full context", exc_info=True)
                return self.get_conversation_context(room_id)

        recent_text = self._format_entries(recent)
        return f"[要約] {summary}\n\n{recent_text}"

    async def _call_summary_llm(self, entries: list[dict]) -> str:
        """Summarize conversation entries using the consolidation LLM."""
        from core.memory._llm_utils import one_shot_completion

        formatted = self._format_entries(entries)
        system = (
            "You are a meeting conversation summarizer. "
            "Summarize the following meeting discussion concisely in the same language as the input. "
            "Preserve key decisions, action items, and important opinions. "
            "Keep the summary under 500 characters."
        )
        result = await one_shot_completion(
            formatted,
            system_prompt=system,
            max_tokens=500,
        )
        if not result:
            raise RuntimeError("LLM returned empty summary")
        return result

    # ── Chair prompt ────────────────────────────────────────

    def build_chair_prompt(self, room: MeetingRoom) -> str:
        """Build the meeting chair system prompt injection.

        Returns a string to be injected into the chair Anima's system prompt at runtime.
        """
        participants_excluding_chair = [p for p in room.participants if p != room.chair]
        member_lines = [f"- {p} (participant)" for p in participants_excluding_chair]
        members_section = "\n".join(member_lines) if member_lines else "- (なし)"
        return f"""## 会議進行ルール

あなたはこの会議の議長です。

### 参加メンバー
{members_section}

### ルール
- @メンバー名 で参加者に意見を求めることができます
- なんでも自分で回答しようとせず、専門性に応じて参加者にも意見を求めてください
- 今までの発言者の意見を踏まえて、他の参加者に自然に意見を求めてください
- 議論が収束したら、結論をまとめてください
- 1つの論点につき全員に聞く必要はありません。適切な人に聞いてください
"""

    # ── Persistence ────────────────────────────────────────

    def save_room(self, room_id: str) -> None:
        """Save room state to JSON file at data_dir/{room_id}.json."""
        self._validate_room_id(room_id)
        room = self.get_room(room_id)
        if room is None:
            return
        path = self._data_dir / f"{room_id}.json"
        data = room.to_dict()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_room(self, room_id: str) -> MeetingRoom | None:
        """Load room from disk."""
        self._validate_room_id(room_id)
        path = self._data_dir / f"{room_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            room = MeetingRoom.from_dict(data)
            self._rooms[room_id] = room
            return room
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load room %s: %s", room_id, e)
            return None

    def load_all_rooms(self) -> None:
        """Load all rooms from disk on startup."""
        self._rooms.clear()
        if not self._data_dir.exists():
            return
        for path in self._data_dir.glob("*.json"):
            room_id = path.stem
            self.load_room(room_id)
        logger.info("Loaded %d meeting rooms from %s", len(self._rooms), self._data_dir)

    # ── Minutes ────────────────────────────────────────────

    async def generate_minutes(self, room_id: str, common_knowledge_dir: Path) -> Path | None:
        """Generate meeting minutes and save to common_knowledge_dir/meetings/{date}_{title}.md.

        Args:
            room_id: Room ID.
            common_knowledge_dir: Base directory for common knowledge (e.g. shared/common_knowledge).

        Returns:
            Path to saved minutes file, or None if room not found.
        """
        room = self.get_room(room_id)
        if room is None:
            return None

        meetings_dir = common_knowledge_dir / "meetings"
        meetings_dir.mkdir(parents=True, exist_ok=True)

        date_str = room.created_at.strftime("%Y-%m-%d")
        title_safe = _sanitize_filename(room.title or "無題の会議")
        closed_str = room.closed_at.strftime("%Y-%m-%d %H:%M") if room.closed_at else "進行中"
        created_str = room.created_at.strftime("%Y-%m-%d %H:%M")

        # Build participants line: chair(議長), others
        parts = []
        for p in room.participants:
            if p == room.chair:
                parts.append(f"{p}(議長)")
            else:
                parts.append(p)
        participants_str = ", ".join(parts)

        # Build discussion content from conversation
        discussion_lines: list[str] = []
        for entry in room.conversation:
            speaker = entry.get("speaker", "")
            role = entry.get("role", "")
            text = entry.get("text", "")
            ts = entry.get("ts", "")
            if role == "chair":
                discussion_lines.append(f"**{speaker} (議長)**: {text}")
            elif role == "human":
                discussion_lines.append(f"**{speaker} (人間)**: {text}")
            else:
                discussion_lines.append(f"**{speaker}**: {text}")
            if ts:
                discussion_lines.append(f"  *{ts}*")
            discussion_lines.append("")
        discussion_content = "\n".join(discussion_lines).strip() or "(発言なし)"

        # Extract conclusion from last chair message, or use placeholder
        conclusion = "議事録を確認してください"
        for entry in reversed(room.conversation):
            if entry.get("role") == "chair":
                text = entry.get("text", "").strip()
                if text:
                    conclusion = text
                break

        content = f"""# 会議録: {room.title or "無題の会議"}

**日時**: {created_str} 〜 {closed_str}
**参加者**: {participants_str}
**議題**: {room.title or "(なし)"}

## 議論内容

{discussion_content}

## 結論・決定事項

{conclusion}
"""

        filename = f"{date_str}_{title_safe}.md"
        out_path = meetings_dir / filename
        out_path.write_text(content, encoding="utf-8")
        logger.info("Generated meeting minutes: %s", out_path)
        return out_path

    # ── Action items ────────────────────────────────────────

    async def extract_action_items(self, room_id: str) -> list[dict]:
        """Draft action items from the meeting transcript via LLM.

        Returns a list of {"assignee", "text"} draft entries (not persisted).
        Assignees are constrained to room participants. Returns [] on failure.
        """
        from core.memory._llm_utils import one_shot_completion

        room = self.get_room(room_id)
        if room is None:
            raise ValueError(t("room_manager.room_not_found", room_id=room_id))
        if not room.conversation:
            return []

        formatted = self._format_entries(room.conversation)
        participants = ", ".join(room.participants)
        system = (
            "You extract concrete action items from a meeting transcript. "
            "Output ONLY a JSON array. Each element is an object with two string "
            'fields: "assignee" (who will do it) and "task" (what to do, imperative). '
            f"The assignee MUST be exactly one of these participant names: {participants}. "
            "Write the task in the same language as the transcript. "
            "If there are no clear action items, output []."
        )
        result = await one_shot_completion(
            formatted,
            system_prompt=system,
            max_tokens=800,
        )
        if not result:
            return []

        valid_names = {p.lower(): p for p in room.participants}
        items: list[dict] = []
        for entry in _parse_json_array(result):
            assignee = str(entry.get("assignee", "")).strip()
            text = str(entry.get("task", "")).strip()
            if not text:
                continue
            canonical = valid_names.get(assignee.lower())
            if canonical is None:
                continue
            items.append({"assignee": canonical, "text": text})
        return items

    def set_action_items(self, room_id: str, items: list[dict]) -> MeetingRoom:
        """Persist the confirmed action item list (replaces existing).

        Each input item needs {"assignee", "text"}; assignees must be participants.
        Preserves "sent" status for items whose (assignee, text) already exist.
        """
        room = self.get_room(room_id)
        if room is None:
            raise ValueError(t("room_manager.room_not_found", room_id=room_id))

        sent_keys = {(i.get("assignee"), i.get("text")) for i in room.action_items if i.get("status") == "sent"}
        valid = set(room.participants)
        new_items: list[dict] = []
        for entry in items:
            assignee = str(entry.get("assignee", "")).strip()
            text = str(entry.get("text", "")).strip()
            if not text:
                continue
            if assignee not in valid:
                raise ValueError(t("room_manager.action_item_invalid_assignee", name=assignee))
            status = "sent" if (assignee, text) in sent_keys else "draft"
            new_items.append(
                {
                    "id": uuid.uuid4().hex[:12],
                    "assignee": assignee,
                    "text": text,
                    "status": status,
                }
            )
        room.action_items = new_items
        self.save_room(room_id)
        logger.info("Set %d action items for room %s", len(new_items), room_id)
        return room

    def dispatch_action_items(self, room_id: str, shared_dir: Path) -> int:
        """Deliver unsent action items to each assignee's inbox (sender = chair).

        Returns the number of items delivered.
        """
        from core.messenger import Messenger

        room = self.get_room(room_id)
        if room is None:
            raise ValueError(t("room_manager.room_not_found", room_id=room_id))
        if not room.chair:
            raise ValueError(t("room_manager.chair_not_in_participants"))

        sender = Messenger(Path(shared_dir), room.chair)
        meeting_label = room.title or t("room_manager.untitled_meeting")
        delivered = 0
        woken: set[str] = set()
        for item in room.action_items:
            if item.get("status") == "sent":
                continue
            assignee = item.get("assignee", "")
            text = item.get("text", "")
            if not assignee or not text:
                continue
            content = t(
                "room_manager.action_item_message",
                meeting=meeting_label,
                task=text,
            )
            msg = sender.send(
                to=assignee,
                content=content,
                intent="meeting_action_item",
                meta={"room_id": room_id, "meeting_title": meeting_label},
            )
            if getattr(msg, "type", "") == "error":
                logger.warning("Action item delivery to %s blocked: %s", assignee, msg.content)
                continue
            item["status"] = "sent"
            delivered += 1
            woken.add(assignee)
        # Writing to the inbox alone does not make an anima act; the supervisor's
        # inbox-wake dispatcher only triggers process_inbox when a wake file
        # exists at run/inbox_wake/{anima}.
        self._wake_animas(Path(shared_dir), woken)
        self.save_room(room_id)
        logger.info("Dispatched %d action items for room %s", delivered, room_id)
        return delivered

    @staticmethod
    def _wake_animas(shared_dir: Path, names: set[str]) -> None:
        """Drop wake files so the supervisor triggers each anima's process_inbox."""
        if not names:
            return
        wake_dir = shared_dir.parent / "run" / "inbox_wake"
        try:
            wake_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning("Failed to create inbox wake dir %s", wake_dir, exc_info=True)
            return
        for name in names:
            try:
                (wake_dir / name).write_text(name, encoding="utf-8")
            except OSError:
                logger.warning("Failed to write inbox wake file for %s", name, exc_info=True)


# ── Helpers ────────────────────────────────────────────────


def _parse_json_array(raw: str) -> list[dict]:
    """Best-effort parse of an LLM response into a list of dicts."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [x for x in parsed if isinstance(x, dict)]


def _sanitize_filename(s: str) -> str:
    """Sanitize string for use in filename."""
    s = s.strip() or "untitled"
    s = re.sub(r'[<>:"/\\|?*]', "_", s)
    s = re.sub(r"\s+", "_", s)
    return s[:80] if len(s) > 80 else s
