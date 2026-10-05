from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.i18n import t
from core.skills.curator import SkillCurator
from core.tooling.handler_skills import SkillsToolsMixin


class _Handler(SkillsToolsMixin):
    def __init__(self, anima_dir: Path) -> None:
        self._anima_dir = anima_dir
        self._anima_name = "test-anima"
        self._curator_instance = SkillCurator(anima_dir)

    def _curator(self) -> SkillCurator:
        return self._curator_instance


def _config(*, auto_apply: bool = False) -> SimpleNamespace:
    return SimpleNamespace(consolidation=SimpleNamespace(curator_auto_apply_enabled=auto_apply))


def test_state_change_proposal_return_is_explicitly_pending_approval(tmp_path: Path) -> None:
    handler = _Handler(tmp_path)
    args = {"skill_name": "old-skill", "reason": "unused"}

    with patch("core.config.load_config", return_value=_config()):
        response = json.loads(handler._handle_archive_skill(args))

    assert response["applied"] is False
    assert response["status"] == "proposed_pending_approval"
    assert response["duplicate"] is False
    assert "old-skill" in response["message"]
    assert len(handler._curator_instance.replay_state().events) == 1


def test_duplicate_pending_state_change_is_not_appended_or_applied(tmp_path: Path) -> None:
    handler = _Handler(tmp_path)
    args = {"skill_name": "old-skill", "reason": "unused"}

    with patch("core.config.load_config", return_value=_config()):
        first = json.loads(handler._handle_archive_skill(args))
        duplicate = json.loads(handler._handle_archive_skill(args))

    assert first["duplicate"] is False
    assert duplicate["applied"] is False
    assert duplicate["status"] == "proposed_pending_approval"
    assert duplicate["duplicate"] is True
    assert "duplicate" in duplicate["message"].lower() or "重複" in duplicate["message"]
    assert len(handler._curator_instance.replay_state().events) == 1


def test_pending_approval_messages_are_localized_in_japanese_and_english() -> None:
    proposed_ja = t(
        "tooling.skill_state_change_proposed_pending_approval", locale="ja", skill_name="x", state="archived"
    )
    proposed_en = t(
        "tooling.skill_state_change_proposed_pending_approval", locale="en", skill_name="x", state="archived"
    )
    duplicate_ja = t(
        "tooling.skill_state_change_duplicate_pending_approval", locale="ja", skill_name="x", state="archived"
    )
    duplicate_en = t(
        "tooling.skill_state_change_duplicate_pending_approval", locale="en", skill_name="x", state="archived"
    )

    assert "まだ適用されていません" in proposed_ja
    assert "not been applied" in proposed_en
    assert "重複" in duplicate_ja
    assert "duplicate" in duplicate_en
