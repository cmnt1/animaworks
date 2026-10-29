from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path

from core.schemas import ModelConfig

# ── ConfigReader ──────────────────────────────────────────


class ConfigReader:
    """Model configuration reader backed by the shared config loader."""

    def __init__(self, anima_dir: Path) -> None:
        self._anima_dir = anima_dir

    def read_model_config(self) -> ModelConfig:
        """Load model config using the canonical ModelConfig loader."""
        from core.config.model_config import load_model_config

        return load_model_config(self._anima_dir)

    def resolve_api_key(self, config: ModelConfig | None = None) -> str | None:
        """Resolve the actual API key (config.json direct value, then env var fallback)."""
        cfg = config or self.read_model_config()
        if cfg.api_key:
            return cfg.api_key
        return os.environ.get(cfg.api_key_env)
