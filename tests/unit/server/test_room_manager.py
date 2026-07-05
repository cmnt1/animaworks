"""Unit tests for server/room_manager.py — Meeting room lifecycle and orchestration."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from server.room_manager import MeetingRoom, RoomManager

# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def room_manager(tmp_path: Path) -> RoomManager:
    """Create a RoomManager with a temporary data directory."""
    data_dir = tmp_path / "meetings"
    return RoomManager(data_dir)


@pytest.fixture
def sample_room(room_manager: RoomManager) -> MeetingRoom:
    """Create a sample meeting room with 3 participants."""
    return room_manager.create_room(
        participants=["sakura", "rin", "ritsu"],
        chair="sakura",
        created_by="taka",
        title="週次レビュー",
    )


# ── Room CRUD ─────────────────────────────────────────────


class TestCreateRoom:
    """Tests for RoomManager.create_room."""

    def test_create_room_basic(self, room_manager: RoomManager):
        room = room_manager.create_room(
            participants=["sakura", "rin"],
            chair="sakura",
            created_by="taka",
            title="テスト会議",
        )
        assert room.room_id
        assert len(room.room_id) == 12
        assert room.participants == ["sakura", "rin"]
        assert room.chair == "sakura"
        assert room.created_by == "taka"
        assert room.title == "テスト会議"
        assert room.closed is False
        assert room.conversation == []

    def test_create_room_with_project_metadata(self, room_manager: RoomManager):
        room = room_manager.create_room(
            participants=["sakura", "kanna"],
            chair="sakura",
            created_by="taka",
            title="AFF-012 ブログ立ち上げ機械",
            project_department="アフィリエイト",
            project_task_code="AFF-012",
            project_note_path=r"E:\OneDriveBiz\Obsidian\_notes\Projects\ブログ立ち上げ機械.md",
            project_task_title="ブログ立ち上げ機械",
        )

        assert room.project_department == "アフィリエイト"
        assert room.project_task_code == "AFF-012"
        assert room.project_task_title == "ブログ立ち上げ機械"

    def test_create_room_max_participants(self, room_manager: RoomManager):
        participants = ["a", "b", "c", "d", "e"]
        room = room_manager.create_room(
            participants=participants,
            chair="a",
            created_by="taka",
        )
        assert len(room.participants) == 5

    def test_create_room_max_participants_exceeds(self, room_manager: RoomManager):
        participants = ["a", "b", "c", "d", "e", "f"]
        with pytest.raises(ValueError) as exc_info:
            room_manager.create_room(
                participants=participants,
                chair="a",
                created_by="taka",
            )
        assert "5" in str(exc_info.value) or "participants" in str(exc_info.value).lower()

    def test_create_room_chair_must_be_participant(self, room_manager: RoomManager):
        with pytest.raises(ValueError):
            room_manager.create_room(
                participants=["sakura", "rin"],
                chair="ritsu",
                created_by="taka",
            )

    def test_create_room_empty_participants(self, room_manager: RoomManager):
        with pytest.raises(ValueError):
            room_manager.create_room(
                participants=[],
                chair="sakura",
                created_by="taka",
            )


class TestGetRoom:
    """Tests for RoomManager.get_room."""

    def test_get_room_exists(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room = room_manager.get_room(sample_room.room_id)
        assert room is not None
        assert room.room_id == sample_room.room_id
        assert room.chair == "sakura"

    def test_get_room_not_found(self, room_manager: RoomManager):
        room = room_manager.get_room("nonexistent123")
        assert room is None


class TestListRooms:
    """Tests for RoomManager.list_rooms."""

    def test_list_rooms_excludes_closed(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_id = sample_room.room_id
        room_manager.close_room(room_id)
        rooms = room_manager.list_rooms(include_closed=False)
        assert len(rooms) == 0

    def test_list_rooms_includes_closed(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_id = sample_room.room_id
        room_manager.close_room(room_id)
        rooms = room_manager.list_rooms(include_closed=True)
        assert len(rooms) == 1
        assert rooms[0].room_id == room_id
        assert rooms[0].closed is True


class TestArchiveRoom:
    """Tests for RoomManager.set_room_archived and archive filtering."""

    def test_archive_excludes_from_default_list(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.set_room_archived(sample_room.room_id, True)
        assert len(room_manager.list_rooms(include_closed=True)) == 0

    def test_archive_included_when_requested(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.set_room_archived(sample_room.room_id, True)
        rooms = room_manager.list_rooms(include_closed=True, include_archived=True)
        assert len(rooms) == 1
        assert rooms[0].archived is True

    def test_archive_persists(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.set_room_archived(sample_room.room_id, True)
        manager2 = RoomManager(room_manager._data_dir)
        loaded = manager2.load_room(sample_room.room_id)
        assert loaded is not None
        assert loaded.archived is True

    def test_unarchive(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.set_room_archived(sample_room.room_id, True)
        room_manager.set_room_archived(sample_room.room_id, False)
        assert len(room_manager.list_rooms(include_closed=True)) == 1

    def test_archive_room_not_found(self, room_manager: RoomManager):
        with pytest.raises(ValueError):
            room_manager.set_room_archived("ffffffffffff", True)


class TestDeleteRoom:
    """Tests for RoomManager.delete_room."""

    def test_delete_removes_from_memory_and_disk(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_id = sample_room.room_id
        room_manager.delete_room(room_id)
        assert room_manager.get_room(room_id) is None
        assert not (room_manager._data_dir / f"{room_id}.json").exists()

    def test_delete_missing_room_is_noop(self, room_manager: RoomManager):
        room_manager.delete_room("ffffffffffff")

    def test_delete_invalid_room_id_raises(self, room_manager: RoomManager):
        with pytest.raises(ValueError):
            room_manager.delete_room("../etc/passwd")


class TestUpdateRoomTitle:
    """Tests for RoomManager.update_room_title."""

    def test_update_room_title_persists(self, room_manager: RoomManager, sample_room: MeetingRoom):
        updated = room_manager.update_room_title(sample_room.room_id, "AFF-012 review")

        assert updated.title == "AFF-012 review"

        manager2 = RoomManager(room_manager._data_dir)
        loaded = manager2.load_room(sample_room.room_id)
        assert loaded is not None
        assert loaded.title == "AFF-012 review"

    def test_update_room_title_trims(self, room_manager: RoomManager, sample_room: MeetingRoom):
        updated = room_manager.update_room_title(sample_room.room_id, "  renamed  ")

        assert updated.title == "renamed"


class TestAddParticipant:
    """Tests for RoomManager.add_participant."""

    def test_add_participant(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.add_participant(sample_room.room_id, "mio")
        room = room_manager.get_room(sample_room.room_id)
        assert room is not None
        assert "mio" in room.participants
        assert len(room.participants) == 4

    def test_add_participant_room_full(self, room_manager: RoomManager):
        room = room_manager.create_room(
            participants=["a", "b", "c", "d", "e"],
            chair="a",
            created_by="taka",
        )
        with pytest.raises(ValueError) as exc_info:
            room_manager.add_participant(room.room_id, "f")
        assert "5" in str(exc_info.value) or "participants" in str(exc_info.value).lower()

    def test_add_participant_room_closed(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.close_room(sample_room.room_id)
        with pytest.raises(ValueError):
            room_manager.add_participant(sample_room.room_id, "mio")


class TestRemoveParticipant:
    """Tests for RoomManager.remove_participant."""

    def test_remove_participant(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.remove_participant(sample_room.room_id, "ritsu")
        room = room_manager.get_room(sample_room.room_id)
        assert room is not None
        assert "ritsu" not in room.participants
        assert room.chair == "sakura"

    def test_remove_participant_chair_reassign(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.remove_participant(sample_room.room_id, "sakura")
        room = room_manager.get_room(sample_room.room_id)
        assert room is not None
        assert room.chair == "rin"
        assert "sakura" not in room.participants


class TestCloseRoom:
    """Tests for RoomManager.close_room."""

    def test_close_room(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.close_room(sample_room.room_id)
        room = room_manager.get_room(sample_room.room_id)
        assert room is not None
        assert room.closed is True
        assert room.closed_at is not None


# ── @mention extraction ───────────────────────────────────


class TestExtractMentions:
    """Tests for RoomManager.extract_mentions."""

    def test_extract_mentions_basic(self, room_manager: RoomManager):
        result = room_manager.extract_mentions(
            "@rin what do you think?",
            participants=["sakura", "rin", "ritsu"],
        )
        assert result == ["rin"]

    def test_extract_mentions_multiple(self, room_manager: RoomManager):
        result = room_manager.extract_mentions(
            "@rin and @ritsu please",
            participants=["sakura", "rin", "ritsu"],
        )
        assert result == ["rin", "ritsu"]

    def test_extract_mentions_case_insensitive(self, room_manager: RoomManager):
        result = room_manager.extract_mentions(
            "@RIN",
            participants=["sakura", "rin", "ritsu"],
        )
        assert result == ["rin"]

    def test_extract_mentions_no_match(self, room_manager: RoomManager):
        result = room_manager.extract_mentions(
            "hello everyone",
            participants=["sakura", "rin", "ritsu"],
        )
        assert result == []

    def test_extract_mentions_non_participant(self, room_manager: RoomManager):
        result = room_manager.extract_mentions(
            "@unknown_name",
            participants=["sakura", "rin", "ritsu"],
        )
        assert result == []

    def test_extract_mentions_preserves_order(self, room_manager: RoomManager):
        result = room_manager.extract_mentions(
            "@ritsu then @rin and @sakura",
            participants=["sakura", "rin", "ritsu"],
        )
        assert result == ["ritsu", "rin", "sakura"]


# ── Conversation ─────────────────────────────────────────


class TestConversation:
    """Tests for conversation history methods."""

    def test_append_message(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.append_message(
            sample_room.room_id,
            speaker="sakura",
            role="chair",
            text="会議を始めます",
        )
        room = room_manager.get_room(sample_room.room_id)
        assert room is not None
        assert len(room.conversation) == 1
        assert room.conversation[0]["speaker"] == "sakura"
        assert room.conversation[0]["role"] == "chair"
        assert room.conversation[0]["text"] == "会議を始めます"
        assert "ts" in room.conversation[0]

    def test_get_conversation_context_format(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.append_message(
            sample_room.room_id,
            speaker="taka",
            role="human",
            text="よろしく",
        )
        room_manager.append_message(
            sample_room.room_id,
            speaker="sakura",
            role="chair",
            text="承知しました",
        )
        room_manager.append_message(
            sample_room.room_id,
            speaker="rin",
            role="participant",
            text="技術面からの意見",
        )
        ctx = room_manager.get_conversation_context(sample_room.room_id)
        assert "[human(taka)] よろしく" in ctx
        assert "[sakura(議長)] 承知しました" in ctx
        assert "[rin] 技術面からの意見" in ctx

    def test_get_conversation_context_truncation(self, room_manager: RoomManager, sample_room: MeetingRoom):
        for i in range(60):
            room_manager.append_message(
                sample_room.room_id,
                speaker="sakura",
                role="chair",
                text=f"msg{i}",
            )
        ctx = room_manager.get_conversation_context(sample_room.room_id, max_messages=10)
        lines = [line for line in ctx.split("\n") if line.strip()]
        assert len(lines) == 10
        assert "msg50" in ctx
        assert "msg0" not in ctx


# ── Chair prompt ─────────────────────────────────────────


class TestBuildChairPrompt:
    """Tests for RoomManager.build_chair_prompt."""

    def test_build_chair_prompt_contains_participants(self, room_manager: RoomManager, sample_room: MeetingRoom):
        prompt = room_manager.build_chair_prompt(sample_room)
        assert "rin" in prompt
        assert "ritsu" in prompt
        assert "sakura" not in prompt or "議長" in prompt

    def test_build_chair_prompt_contains_rules(self, room_manager: RoomManager, sample_room: MeetingRoom):
        prompt = room_manager.build_chair_prompt(sample_room)
        assert "会議進行ルール" in prompt
        assert "議長" in prompt
        assert "@メンバー名" in prompt or "参加者" in prompt


# ── Persistence ───────────────────────────────────────────


class TestPersistence:
    """Tests for room persistence."""

    def test_save_and_load_room(self, room_manager: RoomManager, sample_room: MeetingRoom, tmp_path: Path):
        room_id = sample_room.room_id
        room_manager.append_message(room_id, "sakura", "chair", "テスト発言")
        room_manager.save_room(room_id)
        data_dir = tmp_path / "meetings"
        manager2 = RoomManager(data_dir)
        manager2._rooms.clear()
        loaded = manager2.load_room(room_id)
        assert loaded is not None
        assert loaded.room_id == room_id
        assert loaded.chair == "sakura"
        assert len(loaded.conversation) == 1
        assert loaded.conversation[0]["text"] == "テスト発言"

    def test_save_and_load_room_preserves_project_metadata(self, room_manager: RoomManager, tmp_path: Path):
        room = room_manager.create_room(
            participants=["sakura", "kanna"],
            chair="sakura",
            created_by="taka",
            title="AFF-012 ブログ立ち上げ機械",
            project_department="アフィリエイト",
            project_task_code="AFF-012",
            project_note_path=r"E:\OneDriveBiz\Obsidian\_notes\Projects\ブログ立ち上げ機械.md",
            project_task_title="ブログ立ち上げ機械",
        )

        manager2 = RoomManager(tmp_path / "meetings")
        loaded = manager2.load_room(room.room_id)

        assert loaded is not None
        assert loaded.project_department == "アフィリエイト"
        assert loaded.project_task_code == "AFF-012"
        assert loaded.project_task_title == "ブログ立ち上げ機械"

    def test_load_all_rooms(self, room_manager: RoomManager, tmp_path: Path):
        room1 = room_manager.create_room(
            participants=["a", "b", "c"],
            chair="a",
            created_by="taka",
        )
        room2 = room_manager.create_room(
            participants=["x", "y"],
            chair="x",
            created_by="taka",
        )
        data_dir = tmp_path / "meetings"
        manager2 = RoomManager(data_dir)
        manager2._rooms.clear()
        manager2.load_all_rooms()
        assert len(manager2._rooms) == 2
        assert room1.room_id in manager2._rooms
        assert room2.room_id in manager2._rooms

    def test_load_room_not_found(self, room_manager: RoomManager, tmp_path: Path):
        data_dir = tmp_path / "meetings"
        data_dir.mkdir(parents=True, exist_ok=True)
        manager = RoomManager(data_dir)
        loaded = manager.load_room("aabbccddeeff")
        assert loaded is None


# ── Minutes ───────────────────────────────────────────────


class TestGenerateMinutes:
    """Tests for RoomManager.generate_minutes."""

    @pytest.mark.asyncio
    async def test_generate_minutes(self, room_manager: RoomManager, sample_room: MeetingRoom, tmp_path: Path):
        room_manager.append_message(
            sample_room.room_id,
            speaker="sakura",
            role="chair",
            text="結論です",
        )
        common_knowledge_dir = tmp_path / "common_knowledge"
        path = await room_manager.generate_minutes(sample_room.room_id, common_knowledge_dir)
        assert path is not None
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "会議録" in content
        assert "週次レビュー" in content
        assert "参加者" in content
        assert "sakura" in content
        assert "結論です" in content

    @pytest.mark.asyncio
    async def test_generate_minutes_creates_directory(
        self, room_manager: RoomManager, sample_room: MeetingRoom, tmp_path: Path
    ):
        common_knowledge_dir = tmp_path / "shared" / "common_knowledge"
        assert not common_knowledge_dir.exists()
        path = await room_manager.generate_minutes(sample_room.room_id, common_knowledge_dir)
        assert path is not None
        meetings_dir = common_knowledge_dir / "meetings"
        assert meetings_dir.exists()
        assert meetings_dir.is_dir()

    @pytest.mark.asyncio
    async def test_generate_minutes_room_not_found(self, room_manager: RoomManager, tmp_path: Path):
        common_knowledge_dir = tmp_path / "common_knowledge"
        path = await room_manager.generate_minutes("aabbccddeeff", common_knowledge_dir)
        assert path is None


# ── Action items ──────────────────────────────────────────


class TestSetActionItems:
    """Tests for RoomManager.set_action_items."""

    def test_set_assigns_ids_and_default_status(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room = room_manager.set_action_items(
            sample_room.room_id,
            [{"assignee": "rin", "text": "資料を作る"}],
        )
        assert len(room.action_items) == 1
        item = room.action_items[0]
        assert item["assignee"] == "rin"
        assert item["text"] == "資料を作る"
        assert item["status"] == "draft"
        assert item["id"]

    def test_set_rejects_non_participant(self, room_manager: RoomManager, sample_room: MeetingRoom):
        with pytest.raises(ValueError):
            room_manager.set_action_items(
                sample_room.room_id,
                [{"assignee": "stranger", "text": "やること"}],
            )

    def test_set_filters_empty_text(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room = room_manager.set_action_items(
            sample_room.room_id,
            [{"assignee": "rin", "text": "  "}, {"assignee": "ritsu", "text": "実装"}],
        )
        assert len(room.action_items) == 1
        assert room.action_items[0]["assignee"] == "ritsu"

    def test_set_persists(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.set_action_items(sample_room.room_id, [{"assignee": "rin", "text": "T1"}])
        manager2 = RoomManager(room_manager._data_dir)
        loaded = manager2.load_room(sample_room.room_id)
        assert loaded is not None
        assert loaded.action_items[0]["text"] == "T1"

    def test_set_preserves_sent_status(self, room_manager: RoomManager, sample_room: MeetingRoom):
        room_manager.set_action_items(sample_room.room_id, [{"assignee": "rin", "text": "T1"}])
        room = room_manager.get_room(sample_room.room_id)
        room.action_items[0]["status"] = "sent"
        room_manager.save_room(sample_room.room_id)
        # Re-save same item plus a new one
        room = room_manager.set_action_items(
            sample_room.room_id,
            [{"assignee": "rin", "text": "T1"}, {"assignee": "ritsu", "text": "T2"}],
        )
        statuses = {(i["assignee"], i["text"]): i["status"] for i in room.action_items}
        assert statuses[("rin", "T1")] == "sent"
        assert statuses[("ritsu", "T2")] == "draft"

    def test_set_room_not_found(self, room_manager: RoomManager):
        with pytest.raises(ValueError):
            room_manager.set_action_items("ffffffffffff", [])


class TestDispatchActionItems:
    """Tests for RoomManager.dispatch_action_items."""

    def test_dispatch_writes_inbox_and_marks_sent(
        self, room_manager: RoomManager, sample_room: MeetingRoom, tmp_path: Path
    ):
        shared_dir = tmp_path / "shared"
        room_manager.set_action_items(
            sample_room.room_id,
            [{"assignee": "rin", "text": "資料作成"}, {"assignee": "ritsu", "text": "実装"}],
        )
        delivered = room_manager.dispatch_action_items(sample_room.room_id, shared_dir)
        assert delivered == 2
        assert list((shared_dir / "inbox" / "rin").glob("*.json"))
        assert list((shared_dir / "inbox" / "ritsu").glob("*.json"))
        # Wake files are required for the supervisor to trigger process_inbox.
        wake_dir = shared_dir.parent / "run" / "inbox_wake"
        assert (wake_dir / "rin").is_file()
        assert (wake_dir / "ritsu").is_file()
        room = room_manager.get_room(sample_room.room_id)
        assert all(i["status"] == "sent" for i in room.action_items)

    def test_dispatch_skips_already_sent(self, room_manager: RoomManager, sample_room: MeetingRoom, tmp_path: Path):
        shared_dir = tmp_path / "shared"
        room_manager.set_action_items(sample_room.room_id, [{"assignee": "rin", "text": "T1"}])
        assert room_manager.dispatch_action_items(sample_room.room_id, shared_dir) == 1
        # Second dispatch delivers nothing new
        assert room_manager.dispatch_action_items(sample_room.room_id, shared_dir) == 0

    def test_dispatch_content_includes_task(self, room_manager: RoomManager, sample_room: MeetingRoom, tmp_path: Path):
        import json

        shared_dir = tmp_path / "shared"
        room_manager.set_action_items(sample_room.room_id, [{"assignee": "rin", "text": "ユニーク作業XYZ"}])
        room_manager.dispatch_action_items(sample_room.room_id, shared_dir)
        files = list((shared_dir / "inbox" / "rin").glob("*.json"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert "ユニーク作業XYZ" in data["content"]
        assert data["from_person"] == "sakura"

    def test_dispatch_room_not_found(self, room_manager: RoomManager, tmp_path: Path):
        with pytest.raises(ValueError):
            room_manager.dispatch_action_items("ffffffffffff", tmp_path / "shared")


class TestExtractActionItems:
    """Tests for RoomManager.extract_action_items (LLM mocked)."""

    @pytest.mark.asyncio
    async def test_extract_returns_empty_without_conversation(
        self, room_manager: RoomManager, sample_room: MeetingRoom
    ):
        assert await room_manager.extract_action_items(sample_room.room_id) == []

    @pytest.mark.asyncio
    async def test_extract_parses_and_filters(self, room_manager: RoomManager, sample_room: MeetingRoom, monkeypatch):
        room_manager.append_message(sample_room.room_id, speaker="sakura", role="chair", text="決めよう")

        async def fake_llm(*args, **kwargs):
            return (
                '[{"assignee": "rin", "task": "資料作成"}, '
                '{"assignee": "stranger", "task": "無効"}, '
                '{"assignee": "ritsu", "task": ""}]'
            )

        monkeypatch.setattr("core.memory._llm_utils.one_shot_completion", fake_llm)
        items = await room_manager.extract_action_items(sample_room.room_id)
        assert items == [{"assignee": "rin", "text": "資料作成"}]

    @pytest.mark.asyncio
    async def test_extract_handles_code_fence(self, room_manager: RoomManager, sample_room: MeetingRoom, monkeypatch):
        room_manager.append_message(sample_room.room_id, speaker="sakura", role="chair", text="決めよう")

        async def fake_llm(*args, **kwargs):
            return '```json\n[{"assignee": "ritsu", "task": "実装する"}]\n```'

        monkeypatch.setattr("core.memory._llm_utils.one_shot_completion", fake_llm)
        items = await room_manager.extract_action_items(sample_room.room_id)
        assert items == [{"assignee": "ritsu", "text": "実装する"}]

    @pytest.mark.asyncio
    async def test_extract_returns_empty_on_llm_failure(
        self, room_manager: RoomManager, sample_room: MeetingRoom, monkeypatch
    ):
        room_manager.append_message(sample_room.room_id, speaker="sakura", role="chair", text="決めよう")

        async def fake_llm(*args, **kwargs):
            return None

        monkeypatch.setattr("core.memory._llm_utils.one_shot_completion", fake_llm)
        assert await room_manager.extract_action_items(sample_room.room_id) == []


class TestActionItemsSerialization:
    """Round-trip of action_items through to_dict/from_dict."""

    def test_round_trip(self, sample_room: MeetingRoom):
        sample_room.action_items = [{"id": "abc", "assignee": "rin", "text": "T", "status": "sent"}]
        restored = MeetingRoom.from_dict(sample_room.to_dict())
        assert restored.action_items == sample_room.action_items

    def test_legacy_room_defaults_to_empty(self):
        legacy = {
            "room_id": "aabbccddeeff",
            "participants": ["sakura"],
            "chair": "sakura",
            "created_by": "taka",
            "created_at": "2026-06-28T10:00:00",
            "conversation": [],
        }
        room = MeetingRoom.from_dict(legacy)
        assert room.action_items == []
