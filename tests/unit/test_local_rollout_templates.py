"""Keep local completion and business policies in the actual prompt source."""

from pathlib import Path

import pytest

from core import paths


@pytest.fixture()
def templates(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "templates"
    monkeypatch.setattr(paths, "TEMPLATES_DIR", directory)
    return directory / "ja"


def test_task_exec_keeps_closure_and_canonical_statuses(templates):
    prompt = paths.load_prompt("task_exec", locale="ja", task_id="policy-check")
    assert "TASK_CLOSURE:" in prompt
    assert "acceptance_checks" in prompt
    assert "remaining_blockers" in prompt
    assert 'update_task(task_id="policy-check", status="pending"' in prompt
    assert 'update_task(task_id="policy-check", status="done"' in prompt
    assert 'update_task(status="in_progress"' not in prompt
    assert 'update_task(status="blocked"' not in prompt
    assert "engine=claude" not in prompt


def test_heartbeat_keeps_observation_and_message_checks(templates):
    prompt = paths.load_prompt("heartbeat", locale="ja", checklist="test")
    assert "Current Pre-Observed Heartbeat Snapshot" in prompt
    assert "message-quality-protocol.md" in prompt
    assert "task-delegation-guide.md" in prompt
    assert '"resume":true' in prompt


def test_project_policy_keeps_obsidian_without_legacy_queue_writes(templates):
    text = (templates / "reference/operations/task-management.md").read_text(encoding="utf-8")
    assert "Obsidian Vault" in text
    assert "obsidian-product/SKILL.md" in text
    assert "Anima 内部の TaskStore" in text
    assert 'update_task(status="in_progress")' not in text


def test_data_access_policy_remains_in_active_template(templates):
    prompt = paths.load_prompt("behavior_rules", locale="ja")
    assert "Cnct_Env.py" in prompt
    assert "[IMPORTANT]" in prompt
