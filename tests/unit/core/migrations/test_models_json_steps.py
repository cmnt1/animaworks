from __future__ import annotations

import json
from pathlib import Path

from core.migrations.steps import step_models_json_mode_b_to_a


def test_models_json_mode_b_to_a_preserves_non_b_entries(tmp_path: Path) -> None:
    models_path = tmp_path / "models.json"
    models_path.write_text(
        json.dumps({"ollama/*": {"mode": "B", "context_window": 8192}, "claude-*": {"mode": "S"}}),
        encoding="utf-8",
    )

    result = step_models_json_mode_b_to_a(tmp_path, dry_run=False, verbose=True)

    assert result.error is None
    assert result.changed == 1
    models = json.loads(models_path.read_text(encoding="utf-8"))
    assert models["ollama/*"] == {"mode": "A", "context_window": 8192}
    assert models["claude-*"]["mode"] == "S"


def test_models_json_steps_dry_run_does_not_write(tmp_path: Path) -> None:
    models_path = tmp_path / "models.json"
    original = {"ollama/*": {"mode": "B"}}
    models_path.write_text(json.dumps(original), encoding="utf-8")

    result = step_models_json_mode_b_to_a(tmp_path, dry_run=True, verbose=True)

    assert result.changed == 1
    assert json.loads(models_path.read_text(encoding="utf-8")) == original
