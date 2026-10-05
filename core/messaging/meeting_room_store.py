from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from core.platform.atomic_io import atomic_write_json
from core.platform.locks import locked_path
from core.time_utils import now_iso

logger = logging.getLogger("animaworks.meeting_room_store")

_ROOM_ID_RE = re.compile(r"^[a-f0-9]{12}$")


def _validate_room_id(room_id: str) -> None:
    if not _ROOM_ID_RE.match(room_id):
        raise ValueError(f"Invalid room_id: {room_id!r}")


@contextmanager
def _locked_room(path: Path) -> Iterator[None]:
    lock_path = path.with_suffix(path.suffix + ".lock")
    with locked_path(lock_path, thread_lock=True, best_effort=True):
        yield


def _room_path(meetings_dir: Path, room_id: str) -> Path:
    _validate_room_id(room_id)
    return Path(meetings_dir) / f"{room_id}.json"


def _load_room_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Meeting room not found: {path.stem}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid meeting room file: {path}")
    conversation = data.setdefault("conversation", [])
    if not isinstance(conversation, list):
        data["conversation"] = []
    return data


def _write_room_data(path: Path, data: dict[str, Any]) -> None:
    atomic_write_json(path, data, trailing_newline=False)


def append_room_message(
    meetings_dir: Path,
    room_id: str,
    speaker: str,
    role: str,
    text: str,
    *,
    meta: dict[str, Any] | None = None,
    dedup_key: str = "",
) -> dict[str, Any]:
    """Append a room conversation entry with an interprocess file lock."""
    path = _room_path(meetings_dir, room_id)
    with _locked_room(path):
        data = _load_room_data(path)
        conversation = data.setdefault("conversation", [])
        if dedup_key:
            for existing in conversation:
                existing_meta = existing.get("meta", {}) if isinstance(existing, dict) else {}
                if isinstance(existing_meta, dict) and existing_meta.get("dedup_key") == dedup_key:
                    return existing
        entry: dict[str, Any] = {
            "speaker": speaker,
            "role": role,
            "text": text,
            "ts": now_iso(),
        }
        if meta or dedup_key:
            entry_meta = dict(meta or {})
            if dedup_key:
                entry_meta["dedup_key"] = dedup_key
            entry["meta"] = entry_meta
        conversation.append(entry)
        _write_room_data(path, data)
        return entry


def append_meeting_redirect(
    meetings_dir: Path,
    room_id: str,
    *,
    from_name: str,
    to_name: str,
    content: str,
    intent: str = "",
    redirect_id: str = "",
) -> dict[str, Any]:
    """Durably append a meeting-local redirect entry to the room store."""
    path = _room_path(meetings_dir, room_id)
    dedup_key = f"meeting_redirect:{redirect_id}" if redirect_id else ""
    with _locked_room(path):
        data = _load_room_data(path)
        conversation = data.setdefault("conversation", [])
        if dedup_key:
            for existing in conversation:
                existing_meta = existing.get("meta", {}) if isinstance(existing, dict) else {}
                if isinstance(existing_meta, dict) and existing_meta.get("dedup_key") == dedup_key:
                    return existing
        participants = {str(name) for name in data.get("participants", [])}
        if to_name not in participants:
            raise ValueError(f"Meeting redirect target is not a participant: {to_name}")
        chair = str(data.get("chair") or "")
        role = "chair" if from_name == chair else "participant"
        entry: dict[str, Any] = {
            "speaker": from_name,
            "role": role,
            "text": f"@{to_name} {content}",
            "ts": now_iso(),
            "meta": {
                "type": "meeting_redirect",
                "to": to_name,
                "intent": intent,
                "redirect_id": redirect_id,
                "dedup_key": dedup_key,
            },
        }
        conversation.append(entry)
        _write_room_data(path, data)
        return entry
