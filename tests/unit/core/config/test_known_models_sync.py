"""Ensure the picker catalog covers every concrete runtime default model."""

from __future__ import annotations

import json
from pathlib import Path

from core.config.model_mode import KNOWN_MODELS


def test_known_models_cover_concrete_template_defaults() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    models_path = repo_root / "templates" / "_shared" / "config_defaults" / "models.json"
    models = json.loads(models_path.read_text(encoding="utf-8"))
    known_by_name = {entry["name"]: entry for entry in KNOWN_MODELS}

    for name, model_config in models.items():
        if any(character in name for character in "*?["):
            continue
        assert name in known_by_name, f"{name} is missing from KNOWN_MODELS"
        assert known_by_name[name]["mode"] == model_config["mode"]
