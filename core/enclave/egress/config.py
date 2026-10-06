# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Configuration model for the egress pipeline.

The ``enclave.egress`` section of ``config.json`` (a plain dict) is validated
against these Pydantic models. Unknown stage types and an empty stage list are
treated as configuration errors because no pipeline can be built from them.
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


class KnownValueSource(BaseModel):
    path: str
    format: Literal["jsonl", "csv", "json"] = "jsonl"
    fields: list[str] = Field(default_factory=list)


class KnownValuesStage(BaseModel):
    type: Literal["known_values"]
    sources: list[KnownValueSource] = Field(default_factory=list)
    min_length: int = 2
    ngram: int = 8


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
    PseudonymizeStage | KnownValuesStage | MaskerStage | RegexDenylistStage | CommandStage,
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


def load_egress_config(data: dict) -> EgressConfig:
    """Validate a raw ``enclave.egress`` dict into an :class:`EgressConfig`.

    Raises :class:`EgressConfigError` for unknown stage types and for an empty
    stage list.
    """
    try:
        return EgressConfig.model_validate(data)
    except EgressConfigError:
        raise
    except Exception as exc:  # pydantic.ValidationError and friends
        raise EgressConfigError(f"invalid egress config: {exc}") from exc
