from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cli.commands.models_cmd import cmd_models_helpers
from core.config.schemas import AnimaWorksConfig


@pytest.mark.unit
def test_models_helpers_json_shows_credential_names_but_never_values(capsys: pytest.CaptureFixture[str]) -> None:
    config = AnimaWorksConfig.model_validate(
        {
            "credentials": {
                "anthropic": {"api_key": "very-secret-anthropic-value"},
                "openai": {"api_key": "very-secret-openai-value"},
            },
            "consolidation": {"llm_model": "openai/helper-summary", "llm_credential": "openai"},
            "helper_models": {
                "episode_summary": {"fallbacks": [{"model": "anthropic/claude-haiku-4-5", "credential": "anthropic"}]}
            },
        }
    )

    with patch("core.config.models.load_config", return_value=config):
        cmd_models_helpers(argparse.Namespace(anima=None, json_output=True))

    output = capsys.readouterr().out
    rows = json.loads(output)
    summary = next(row for row in rows if row["role"] == "episode_summary")
    assert summary["model"] == "openai/helper-summary"
    assert summary["credential"] == "openai"
    assert summary["fallbacks"] == [{"model": "anthropic/claude-haiku-4-5", "credential": "anthropic"}]
    assert "very-secret-anthropic-value" not in output
    assert "very-secret-openai-value" not in output


@pytest.mark.unit
def test_models_helpers_resolves_anima_status_overrides(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    anima_dir = tmp_path / "animas" / "mei"
    anima_dir.mkdir(parents=True)
    (anima_dir / "status.json").write_text(
        '{"helper_models":{"fact_reconcile":{"model":"openai/status-reconcile","credential":"gpu40-direct"}}}',
        encoding="utf-8",
    )
    config = AnimaWorksConfig.model_validate({"consolidation": {"llm_model": "codex/gpt-6-luna"}})

    with (
        patch("core.config.models.load_config", return_value=config),
        patch("core.paths.get_animas_dir", return_value=tmp_path / "animas"),
    ):
        cmd_models_helpers(argparse.Namespace(anima="mei", json_output=True))

    rows = json.loads(capsys.readouterr().out)
    reconcile = next(row for row in rows if row["role"] == "fact_reconcile")
    assert reconcile["model"] == "openai/status-reconcile"
    assert reconcile["credential"] == "gpu40-direct"
    assert reconcile["source"] == "status.helper_models.fact_reconcile"


def test_models_helpers_rejects_unknown_anima(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("core.config.models.load_config", return_value=AnimaWorksConfig()),
        patch("core.paths.get_animas_dir", return_value=tmp_path),
        pytest.raises(SystemExit) as exc_info,
    ):
        cmd_models_helpers(argparse.Namespace(anima="missing", json_output=True))

    assert exc_info.value.code == 1
    assert "missing" in capsys.readouterr().err
