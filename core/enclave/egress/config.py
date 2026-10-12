# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Configuration model for the egress pipeline.

The ``enclave.egress`` section of ``config.json`` (a plain dict) is validated
against these Pydantic models. Unknown stage types and an empty stage list are
treated as configuration errors because no pipeline can be built from them.
Legacy known-value stages are discarded with a one-time warning; when that
leaves no active stages, the default masker is installed as a safe fallback.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class EgressConfigError(ValueError):
    """Raised when the egress configuration is invalid or unusable."""


# ---------------------------------------------------------------------------
# Stage models
# ---------------------------------------------------------------------------


class PseudonymizePattern(BaseModel):
    name: str = ""
    regex: str
    prefix: str = "P"


class PseudonymizeStage(BaseModel):
    type: Literal["pseudonymize_ids"]
    patterns: list[PseudonymizePattern] = Field(default_factory=list)


class MaskerStage(BaseModel):
    type: Literal["masker"]
    profile: str = "default"


class RegexDenylistPattern(BaseModel):
    regex: str
    action: Literal["redact", "block"] = "redact"


class RegexDenylistStage(BaseModel):
    type: Literal["regex_denylist"]
    patterns: list[RegexDenylistPattern] = Field(default_factory=list)


class CommandStage(BaseModel):
    type: Literal["command"]
    argv: list[str]
    timeout_s: float = 30.0


Stage = Annotated[
    PseudonymizeStage | MaskerStage | RegexDenylistStage | CommandStage,
    Field(discriminator="type"),
]


class EgressConfig(BaseModel):
    """Validated ``enclave.egress`` configuration."""

    stages: list[Stage]
    max_fact_chars: int = 2000
    max_facts: int = 50

    @model_validator(mode="after")
    def _check_not_empty(self) -> EgressConfig:
        if not self.stages:
            raise EgressConfigError("enclave.egress.stages must not be empty")
        return self


_WARNED_LEGACY_STAGE = False


def load_egress_config(data: dict) -> EgressConfig:
    """Validate a raw ``enclave.egress`` dict into an :class:`EgressConfig`.

    Legacy known-value stages are ignored without preventing an existing
    enclave from starting. Unknown stage types and empty stage lists remain
    configuration errors.
    """
    global _WARNED_LEGACY_STAGE

    stages = data.get("stages")
    if isinstance(stages, list):
        active_stages = [
            stage for stage in stages if not (isinstance(stage, dict) and stage.get("type") == "known_values")
        ]
        if len(active_stages) != len(stages):
            if not _WARNED_LEGACY_STAGE:
                logger.warning("Ignoring legacy enclave egress known_values stage configuration")
                _WARNED_LEGACY_STAGE = True
            if not active_stages:
                active_stages = [{"type": "masker", "profile": "default"}]
            data = {**data, "stages": active_stages}

    try:
        return EgressConfig.model_validate(data)
    except EgressConfigError:
        raise
    except Exception as exc:  # pydantic.ValidationError and friends
        raise EgressConfigError(f"invalid egress config: {exc}") from exc
