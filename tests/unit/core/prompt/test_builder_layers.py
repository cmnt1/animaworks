from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.memory.manager import MemoryManager
from core.prompt import builder


def _memory(anima_dir: Path, *, vision: str = "") -> MagicMock:
    for child in ("knowledge", "procedures", "skills"):
        (anima_dir / child).mkdir(parents=True, exist_ok=True)

    memory = MagicMock()
    memory.anima_dir = anima_dir
    memory.read_identity.return_value = "# Identity\nFixture anima"
    memory.read_injection.return_value = ""
    memory.read_permissions.return_value = ""
    memory.read_bootstrap.return_value = ""
    memory.read_company_vision.return_value = vision
    memory.read_specialty_prompt.return_value = ""
    memory.read_current_state.return_value = "status: idle"
    memory.read_resolutions.return_value = []
    memory.list_knowledge_files.return_value = []
    memory.list_procedure_files.return_value = []
    memory.list_shared_users.return_value = []
    return memory


def _build(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    trigger: str,
    *,
    anima_name: str = "fixture",
) -> str:
    anima_dir = data_dir / "animas" / anima_name
    memory = _memory(anima_dir)
    monkeypatch.setattr(builder, "get_data_dir", lambda: data_dir)
    monkeypatch.setattr(builder, "_discover_other_animas", lambda _path: [])
    return builder.build_system_prompt(
        memory,
        execution_mode="s",
        trigger=trigger,
        context_window=200_000,
    ).system_prompt


def test_trigger_specific_behavior_context(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chat = _build(data_dir, monkeypatch, "chat")
    heartbeat = _build(data_dir, monkeypatch, "heartbeat")
    task = _build(data_dir, monkeypatch, "task:fixture")

    assert "業務指示を受けた場合の振り分け" in chat
    assert "チャットでのタスク記録" in chat
    assert "Heartbeat でのタスク記録" not in chat

    assert "業務指示を受けた場合の振り分け" not in heartbeat
    assert "Heartbeat でのタスク記録" in heartbeat
    assert "チャットでのタスク記録" not in heartbeat

    assert "業務指示を受けた場合の振り分け" not in task
    assert "チャットでのタスク記録" not in task
    assert "Heartbeat でのタスク記録" not in task


def test_repo_rules_only_with_workspace(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builder, "_read_default_workspace", lambda _path: "")
    without_workspace = _build(data_dir, monkeypatch, "task:fixture")

    monkeypatch.setattr(builder, "_read_default_workspace", lambda _path: "WORKSPACE_MARKER")
    with_workspace = _build(data_dir, monkeypatch, "task:fixture")

    assert "リポジトリ作業ルール" not in without_workspace
    assert "WORKSPACE_MARKER" in with_workspace
    assert "リポジトリ作業ルール" in with_workspace


def test_environment_is_l1_and_points_to_reference(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prompt = _build(data_dir, monkeypatch, "chat")

    assert "├──" not in prompt
    assert 'read_memory_file(path="reference/anatomy/environment-layout.md")' in prompt


def test_cli_duplication_and_skill_creator_are_removed(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt = _build(data_dir, monkeypatch, "chat")

    assert "## CLI Tools" not in prompt
    assert prompt.count("skill-creator") <= 1


def test_communication_rules_are_injected_once(
    data_dir: Path,
    make_anima,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = make_anima("sakura")
    make_anima("rin", supervisor="sakura", speciality="development")
    memory = _memory(anima_dir)
    monkeypatch.setattr(builder, "get_data_dir", lambda: data_dir)

    prompt = builder.build_system_prompt(memory, execution_mode="s", trigger="chat").system_prompt

    assert prompt.count("**経路**:") == 1
    assert prompt.count('`ping_subordinate(name="<Anima名>")`') == 1


def test_read_identity_strips_frontmatter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    memory = MemoryManager.__new__(MemoryManager)
    memory.anima_dir = tmp_path
    raw = "---\nname: Fixture\nrole: engineer\n---\n\n# Identity\nFixture anima"
    monkeypatch.setattr(memory, "_read", lambda _path: raw)

    assert memory.read_identity() == "# Identity\nFixture anima"


@pytest.mark.parametrize("vision", ["# Vision\n要記入", "# Vision\nTODO", "# Vision\n(未記入)"])
def test_placeholder_vision_is_not_injected(vision: str) -> None:
    memory = MagicMock()
    memory.read_bootstrap.return_value = ""
    memory.read_company_vision.return_value = vision
    memory.read_specialty_prompt.return_value = ""

    sections = builder._build_group2(memory, "", False, False, {})

    assert "vision" not in {section.id for section in sections}


def test_substantive_vision_is_injected() -> None:
    vision = "# Vision\nBuild reliable systems that measurably improve how the organization works every day."
    memory = MagicMock()
    memory.read_bootstrap.return_value = ""
    memory.read_company_vision.return_value = vision
    memory.read_specialty_prompt.return_value = ""

    sections = builder._build_group2(memory, "", False, False, {})

    assert next(section.content for section in sections if section.id == "vision") == vision
