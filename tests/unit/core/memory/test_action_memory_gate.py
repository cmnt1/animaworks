from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class FakeRule:
    doc_id: str
    content: str
    score: float = 0.95


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "mei"
    (d / "knowledge").mkdir(parents=True)
    return d


# ── find_action_rules ───────────────────────────────────────


def test_find_action_rules_only_above_threshold(anima_dir: Path, monkeypatch) -> None:
    from core.memory import action_gate

    monkeypatch.setattr(
        action_gate,
        "_search_action_rules",
        lambda *a, **k: [
            FakeRule("r-high", "## [ACTION-RULE] high\ntrigger_tools: call_human", 0.92),
            FakeRule("r-low", "## [ACTION-RULE] low", 0.79),
        ],
    )

    rules = action_gate.find_action_rules(anima_dir, "call_human", {})

    assert [r.rule_id for r in rules] == ["r-high"]


def test_find_action_rules_sorted_by_score_and_capped(anima_dir: Path, monkeypatch) -> None:
    from core.memory import action_gate

    monkeypatch.setattr(
        action_gate,
        "_search_action_rules",
        lambda *a, **k: [
            FakeRule(f"r{i}", "body", 0.80 + i * 0.02) for i in range(5)
        ],
    )

    rules = action_gate.find_action_rules(anima_dir, "gmail_send", {})

    assert len(rules) == 3
    assert [r.score for r in rules] == sorted((r.score for r in rules), reverse=True)


def test_find_action_rules_truncates_body(anima_dir: Path, monkeypatch) -> None:
    from core.memory import action_gate

    monkeypatch.setattr(
        action_gate,
        "_search_action_rules",
        lambda *a, **k: [FakeRule("r", "x" * 5000, 0.95)],
    )
    rules = action_gate.find_action_rules(anima_dir, "gmail_send", {})
    assert len(rules[0].content) == 2000


def test_find_action_rules_empty_when_search_raises(anima_dir: Path, monkeypatch) -> None:
    from core.memory import action_gate

    def raise_search(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(action_gate, "_search_action_rules", raise_search)
    assert action_gate.find_action_rules(anima_dir, "gmail_send", {}) == []


# ── format_action_rules ─────────────────────────────────────


def test_format_action_rules_empty_is_empty_string() -> None:
    from core.memory.action_gate import format_action_rules

    assert format_action_rules([]) == ""


def test_format_action_rules_includes_tag_and_body() -> None:
    from core.memory.action_gate import ActionRule, format_action_rules

    rendered = format_action_rules(
        [ActionRule(rule_id="mei/knowledge/rule.md#0", content="本文", score=0.87)]
    )
    assert '<action-rule path="mei/knowledge/rule.md#0" score="0.87">' in rendered
    assert "本文" in rendered
    assert "</action-rule>" in rendered


# ── tool-name resolution ────────────────────────────────────


def test_cli_argv_mapping() -> None:
    from core.memory.action_gate import action_tool_name_from_cli_argv

    assert action_tool_name_from_cli_argv(["gmail", "draft", "--to", "a@example.com"]) == "gmail_draft"
    assert action_tool_name_from_cli_argv(["gmail", "draft-update", "draft-id"]) == "gmail_draft_update"
    assert action_tool_name_from_cli_argv(["gmail", "send", "--to", "a@example.com"]) == "gmail_send"
    assert action_tool_name_from_cli_argv(["chatwork", "send", "room", "body"]) == "chatwork_send"
    assert action_tool_name_from_cli_argv(["slack", "send", "#ops", "body"]) == "slack_send"
    assert action_tool_name_from_cli_argv(["discord", "send", "general", "body"]) == "discord_send"
    assert action_tool_name_from_cli_argv(["call_human", "subject", "body"]) == "call_human"
    assert action_tool_name_from_cli_argv(["gmail", "unread"]) is None
    assert action_tool_name_from_cli_argv(["submit", "gmail", "send"]) is None


def test_handler_action_tool_names_are_current() -> None:
    from core.memory.action_gate import ACTION_TOOL_NAMES, action_tool_name_for_handler

    assert {
        "call_human",
        "send_message",
        "post_channel",
        "write_memory_file",
        "create_skill",
        "gmail_draft",
        "gmail_draft_update",
        "gmail_send",
        "chatwork_send",
        "slack_send",
        "discord_send",
    } == ACTION_TOOL_NAMES
    assert action_tool_name_for_handler("slack_post") is None


def test_sdk_tool_name_normalization() -> None:
    from core.memory.action_gate import action_tool_name_for_sdk

    assert action_tool_name_for_sdk("mcp__aw__send_message") == "send_message"
    assert action_tool_name_for_sdk("mcp__aw__write_memory_file") == "write_memory_file"
    assert action_tool_name_for_sdk("mcp__aw__gmail_draft") == "gmail_draft"
    assert action_tool_name_for_sdk("slack_post") is None
