from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.config import BackgroundReviewConfig
from core.memory.maintenance import background_review as review
from core.memory.manager import MemoryManager
from core.memory.priming.channel_a import channel_a_sender_profile
from core.time_utils import now_local


class _FakeMemory:
    def __init__(self, knowledge_dir: Path) -> None:
        self.knowledge_dir = knowledge_dir
        self.indexed: list[Path] = []
        self.peers: dict[str, str] = {}

    def list_knowledge_files(self) -> list[str]:
        return [path.stem for path in self.knowledge_dir.glob("*.md")]

    def read_peer_profile(self, name: str, *, max_chars: int | None = None) -> str:
        content = self.peers.get(name, "")
        return content[:max_chars] if max_chars is not None else content

    def read_knowledge_content(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def read_knowledge_metadata(self, path: Path) -> dict:
        return {}

    def write_knowledge_with_meta(self, path: Path, content: str, metadata: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def index_knowledge_file(self, path: Path, *, origin: str = "") -> None:
        self.indexed.append(path)

    def write_peer_profile(self, name: str, content: str, *, max_chars: int = 1500) -> Path:
        self.peers[name] = content[:max_chars]
        return Path(name)


def _settings(**overrides: object) -> SimpleNamespace:
    values = {
        "enabled": True,
        "chat_every_user_turns": 10,
        "min_interval_minutes": 0,
        "max_per_day": 24,
        "max_input_bytes": 60 * 1024,
        "max_writes": 3,
        "peer_profile_max_chars": 1500,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_background_review_prompt_templates_render_in_all_locales() -> None:
    from core.paths import load_prompt

    for locale in ("ja", "en", "ko"):
        prompt = load_prompt(
            "memory/background_review",
            locale=locale,
            anima_name="agent",
            trigger="task_end",
            activity="recent activity",
            knowledge_files="note.md",
            peer_profiles="Alice: profile",
        )
        assert "recent activity" in prompt
        assert '"operations"' in prompt


def test_background_review_config_defaults_and_per_anima_switch() -> None:
    settings = BackgroundReviewConfig()
    assert settings.enabled is True
    assert settings.chat_every_user_turns == 10
    assert settings.min_interval_minutes == 10
    assert settings.max_per_day == 24
    assert settings.max_input_bytes == 60 * 1024
    assert settings.max_writes == 3
    assert settings.peer_profile_max_chars == 1500


def test_apply_operations_filters_and_caps_writes(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "agent"
    knowledge_dir = anima_dir / "knowledge"
    knowledge_dir.mkdir(parents=True)
    note = knowledge_dir / "handoff.md"
    note.write_text("Existing note", encoding="utf-8")
    memory = _FakeMemory(knowledge_dir)
    operations = [
        {"op": "knowledge_upsert", "path": "handoff.md", "content": "Keep the confirmed checklist."},
        {"op": "knowledge_upsert", "path": "../outside.md", "content": "blocked"},
        {"op": "peer_update", "peer": "alice", "content": "A" * 2000},
        {"op": "peer_update", "peer": "unrelated", "content": "blocked"},
        {"op": "skill_update", "path": "skills/x.md", "content": "blocked"},
    ]

    written = review._apply_operations(memory, anima_dir, operations, ["Alice"], _settings(max_writes=2))

    assert written == 2
    content = note.read_text(encoding="utf-8")
    assert "Existing note" in content
    assert "Keep the confirmed checklist." in content
    assert "## " in content
    assert memory.indexed == [note]
    assert len(memory.peers["Alice"]) == 1500
    assert not (tmp_path / "outside.md").exists()


def test_build_prompt_obeys_byte_cap_and_keeps_newest_activity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        review,
        "load_prompt",
        lambda _name, **kwargs: "{anima_name}|{trigger}|{activity}|{knowledge_files}|{peer_profiles}".format(**kwargs),
    )
    entries = [
        SimpleNamespace(
            ts="2026-09-28T10:00:00+09:00",
            type="message_received",
            from_person="alice",
            to_person="agent",
            channel="chat",
            tool="",
            summary="old marker",
            content="OLD_MARKER " + "x" * 1000,
        ),
        SimpleNamespace(
            ts="2026-09-28T10:05:00+09:00",
            type="message_received",
            from_person="alice",
            to_person="agent",
            channel="chat",
            tool="",
            summary="new marker",
            content="NEW_MARKER " + "新" * 1000,
        ),
    ]
    memory = _FakeMemory(tmp_path / "knowledge")
    memory.knowledge_dir.mkdir()
    prompt = review._build_prompt(tmp_path / "agent", "auto_compact", entries, memory, _settings(max_input_bytes=260))

    assert len(prompt.encode("utf-8")) <= 260
    assert "NEW_MARKER" in prompt
    assert "OLD_MARKER" not in prompt


@pytest.mark.asyncio
async def test_existing_episode_model_fallback_is_used_and_all_failures_are_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.anima.lifecycle import _complete_episode_prompt

    attempts: list[str] = []

    async def completion(_prompt: str, *, model: str, credential: str, max_tokens: int) -> str | None:
        attempts.append(model)
        if model == "primary":
            raise RuntimeError("primary unavailable")
        return '{"operations": []}' if model == "fallback" else None

    monkeypatch.setattr("core.memory._llm_utils.one_shot_completion", completion)
    configs = [SimpleNamespace(model="primary", credential=""), SimpleNamespace(model="fallback", credential="")]

    raw, reason = await _complete_episode_prompt("prompt", configs)
    assert raw == '{"operations": []}'
    assert reason == ""
    assert attempts == ["primary", "fallback"]

    attempts.clear()

    async def fail_all(_prompt: str, *, model: str, credential: str, max_tokens: int) -> str | None:
        attempts.append(model)
        raise RuntimeError("unavailable")

    monkeypatch.setattr("core.memory._llm_utils.one_shot_completion", fail_all)
    raw, reason = await _complete_episode_prompt("prompt", configs)
    assert raw is None
    assert reason
    assert attempts == ["primary", "fallback"]


@pytest.mark.asyncio
async def test_queue_contains_review_failures_without_blocking_caller(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def fail_review(*_args, **_kwargs) -> bool:
        raise RuntimeError("mocked failure")

    monkeypatch.setattr(review, "_review_config", lambda _path: _settings(min_interval_minutes=10))
    monkeypatch.setattr(review, "perform_background_review", fail_review)
    anima_dir = tmp_path / "agent"
    review.request_background_review(anima_dir, "task_end")
    runtime = review._RUNTIMES[anima_dir.resolve()]
    assert runtime.task is not None
    await asyncio.sleep(0)
    task = runtime.task
    assert task is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    state = review._load_state(review._state_path(anima_dir))
    assert state["pending_triggers"] == ["task_end"]
    assert "last_attempt_at" in state


def test_review_delay_enforces_interval_and_daily_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    current = now_local()
    monkeypatch.setattr(review, "now_local", lambda: current)
    monkeypatch.setattr(review, "today_local", lambda: current.date())
    settings = _settings(min_interval_minutes=10, max_per_day=1)

    interval_state = {
        "daily_date": current.date().isoformat(),
        "daily_count": 0,
        "last_attempt_at": (current - timedelta(minutes=5)).isoformat(),
    }
    assert review._review_delay(interval_state, settings) == pytest.approx(300, abs=1)

    capped_state = {"daily_date": current.date().isoformat(), "daily_count": 1}
    assert review._review_delay(capped_state, settings) > 60 * 60


@pytest.mark.asyncio
async def test_auto_compact_task_end_and_chat_turn_triggers_are_queued(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    state_by_path: dict[Path, dict] = {}

    async def fake_review(_anima_dir: Path, trigger: str, *, since, settings) -> bool:
        calls.append(trigger)
        return True

    monkeypatch.setattr(review, "_review_config", lambda _path: _settings())
    monkeypatch.setattr(review, "_state_path", lambda path: path / "state" / "background_review.json")
    monkeypatch.setattr(review, "_load_state", lambda path: state_by_path.get(path.parent.parent, {}).copy())
    monkeypatch.setattr(
        review, "_save_state", lambda path, state: state_by_path.__setitem__(path.parent.parent, state.copy())
    )
    monkeypatch.setattr(review, "perform_background_review", fake_review)
    anima_dir = tmp_path / "agent"

    for trigger in ("auto_compact", "task_end"):
        review.request_background_review(anima_dir, trigger)
        runtime = review._RUNTIMES[anima_dir.resolve()]
        assert runtime.task is not None
        await runtime.task
        await asyncio.sleep(0)

    for _ in range(10):
        review.request_background_review(anima_dir, "", user_turn=True)
    runtime = review._RUNTIMES[anima_dir.resolve()]
    assert runtime.task is not None
    await runtime.task

    assert calls == ["auto_compact", "task_end", "chat_user_turns"]
    assert state_by_path[anima_dir]["chat_user_turns"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("sender", ["alice", "agent_b"])
async def test_channel_a_appends_peer_profile_for_human_and_anima_senders(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sender: str,
) -> None:
    anima_dir = tmp_path / "animas" / "observer"
    shared_dir = tmp_path / "shared"
    peer_dir = anima_dir / "peers"
    peer_dir.mkdir(parents=True)
    (peer_dir / f"{sender}.md").write_text("Peer-specific observations", encoding="utf-8")
    if sender == "alice":
        user_dir = shared_dir / "users" / sender
        user_dir.mkdir(parents=True)
        (user_dir / "index.md").write_text("Shared profile", encoding="utf-8")
    monkeypatch.setattr("core.paths.get_shared_dir", lambda: shared_dir)

    result = await channel_a_sender_profile(anima_dir, sender)

    assert "Peer-specific observations" in result
    if sender == "alice":
        assert "Shared profile" in result


def test_memory_manager_atomically_writes_safe_peer_profiles(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "observer"
    anima_dir.mkdir(parents=True)
    memory = MemoryManager.__new__(MemoryManager)
    memory.anima_dir = anima_dir

    path = memory.write_peer_profile("Alice Smith", "Works best with a concise brief.", max_chars=40)

    assert path == anima_dir / "peers" / "alice_smith.md"
    assert memory.read_peer_profile("alice smith").strip() == "Works best with a concise brief."
    with pytest.raises(ValueError):
        memory.write_peer_profile("../outside", "Must not escape")
    assert not (tmp_path / "outside.md").exists()


def test_peer_name_normalization_rejects_traversal() -> None:
    assert review.normalize_peer_name("Alice Smith") == "alice_smith"
    assert review.normalize_peer_name("../outside") == ""


def test_deferred_requests_are_recorded_and_consumed(tmp_path, monkeypatch):
    """Disposable runners persist requests; the resident worker picks them up."""
    from core.memory.maintenance import background_review as br

    monkeypatch.setattr(br, "_DEFERRED_REQUESTS", True)
    br.request_background_review(tmp_path, "task_end")
    br.request_background_review(tmp_path, "", user_turn=True)
    assert br.has_pending_background_review(tmp_path)
    assert not br._RUNTIMES.get(tmp_path.resolve())

    runtime = br._ReviewRuntime()
    br._consume_deferred_requests(tmp_path, runtime)
    assert runtime.pending_triggers == ["task_end"]
    assert runtime.user_turn_delta == 1
    assert not br._requests_path(tmp_path).exists()
    assert not br.has_pending_background_review(tmp_path)


def test_related_people_splits_batched_senders() -> None:
    from types import SimpleNamespace

    from core.memory.maintenance.background_review import _related_people

    entries = [
        SimpleNamespace(from_person="sumire, sakura", to_person="rin"),
        SimpleNamespace(from_person="taka", to_person=""),
    ]
    assert _related_people(entries, "rin") == ["taka", "sumire", "sakura"]
