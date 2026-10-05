from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from core.prompt.builder import _build_group1, _build_group6


def test_group1_uses_file_backed_environment_and_behavior_rules(tmp_path: Path) -> None:
    memory = MagicMock()
    memory.read_identity.return_value = ""
    memory.read_injection.return_value = ""
    with (
        patch("core.prompt.builder.load_prompt") as load,
        patch("core.prompt.builder.load_prompt_text", return_value="file rules"),
    ):
        load.side_effect = lambda name, **kwargs: {
            "environment": "file environment",
        }[name]
        sections = _build_group1(tmp_path / "anima", tmp_path, memory, False, {})

    contents = {section.id: section.content for section in sections}
    assert contents["environment"] == "file environment"
    assert contents["behavior_rules"] == "file rules"


def test_group6_keeps_emotion_instruction() -> None:
    with patch("core.prompt.builder._build_emotion_instruction", return_value="file emotion"):
        sections = _build_group6("a", True, False, False, {})

    contents = {section.id: section.content for section in sections}
    assert contents["emotion_instruction"] == "file emotion"
