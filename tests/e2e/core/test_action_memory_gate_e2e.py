from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.exceptions import ConfigError


@dataclass
class FakeRule:
    doc_id: str
    content: str
    score: float = 0.95


def test_action_gate_attaches_rule_body_and_passes_through(tmp_path: Path, monkeypatch) -> None:
    """ToolHandler attaches the relevant ACTION-RULE body instead of blocking."""
    from core.memory import action_gate
    from core.tooling.handler import ToolHandler

    anima_dir = tmp_path / "animas" / "mei"
    (anima_dir / "knowledge").mkdir(parents=True)
    (anima_dir / "procedures").mkdir()
    (anima_dir / "procedures" / "secretary-checklist.md").write_text(
        "# Secretary checklist\n\nCheck duplicates before sending.\n",
        encoding="utf-8",
    )
    memory = MagicMock()
    memory.search_memory_text.return_value = []
    with patch("core.config.models.load_config", side_effect=ConfigError("skip subordinate cache")):
        handler = ToolHandler(anima_dir=anima_dir, memory=memory, tool_registry=["gmail"])
    handler._external.dispatch = MagicMock(return_value="draft created")

    rule = FakeRule(
        "rule-e2e",
        (
            "## [ACTION-RULE] Gmail draft duplicate check\n"
            "trigger_tools: gmail_draft\n"
            "---\n"
            "Check duplicates before sending."
        ),
    )
    monkeypatch.setattr(action_gate, "_search_action_rules", lambda *args, **kwargs: [rule])

    result = handler.handle("gmail_draft", {"to": "a@example.com", "body": "hello"})

    assert result.startswith("draft created")
    assert '<action-rule path="rule-e2e"' in result
    assert "Check duplicates before sending." in result
