from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Configuration resolution for legacy atomic fact extraction."""

import logging
from pathlib import Path
from typing import Any

from core.config.helper_models import ResolvedHelperModel, resolve_helper_model
from core.config.schemas import AnimaWorksConfig

logger = logging.getLogger("animaworks.memory.fact_extraction")

DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS = 120


def _coerce_timeout_seconds(value: object, fallback: int) -> int:
    if value is None or value == "":
        return fallback
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return fallback
    return timeout if timeout > 0 else fallback


def _resolve_extraction_helper_model(anima_dir: Path) -> tuple[Any, ResolvedHelperModel]:
    """Load config and resolve the fact-extraction helper role."""
    try:
        from core.config import load_config

        config = load_config()
    except Exception:
        logger.debug("Failed to load config for fact extraction; using code defaults", exc_info=True)
        config = AnimaWorksConfig()
    return config, resolve_helper_model("fact_extraction", anima_dir, config=config)


def _resolve_extraction_config(anima_dir: Path) -> tuple[str, dict[str, object], str, int, str]:
    """Compatibility facade returning the centralized fact-extraction selection."""
    config, helper = _resolve_extraction_helper_model(anima_dir)
    timeout = _coerce_timeout_seconds(
        getattr(getattr(config, "rag", None), "fact_extraction_timeout_seconds", None),
        DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS,
    )
    try:
        from core.platform.status_store import read_status

        status = read_status(Path(anima_dir))
        if status.get("extraction_timeout"):
            timeout = _coerce_timeout_seconds(status["extraction_timeout"], timeout)
    except Exception:
        logger.debug("Failed to read fact extraction timeout override", exc_info=True)
    locale = str(getattr(config, "locale", "") or _resolve_locale())
    return helper.model, {}, locale, timeout, helper.credential or ""


def _resolve_extraction_max_tokens() -> int:
    """Resolve the maximum output tokens for atomic fact extraction.

    Uses ``config.rag.fact_extraction_max_tokens`` when configured (must be
    >= 1024), otherwise the default 8192.
    """
    try:
        from core.config import load_config

        value = getattr(getattr(load_config(), "rag", None), "fact_extraction_max_tokens", None)
        if isinstance(value, int) and value >= 1024:
            return value
    except Exception:
        logger.debug("Failed to resolve fact extraction max_tokens from config", exc_info=True)
    return 8192


def _resolve_locale() -> str:
    try:
        from core.config.models import load_config

        return str(load_config().locale or "ja")
    except Exception:
        return "ja"
