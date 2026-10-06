# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Data structures for the egress pipeline.

These are plain dataclasses shared by the config, stages, pipeline, and audit
modules. They carry no business-specific wording so the pipeline stays reusable
across domains.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Fact:
    """A single answer fact, optionally with supporting evidence snippets."""

    fact: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class EgressRequest:
    """An incoming answer that must be masked before leaving the enclave."""

    request_id: str
    case_id: str
    from_anima: str
    facts: list[Fact]


@dataclass
class EgressResult:
    """The masked result of a successful pipeline run."""

    audit_id: str
    facts: list[Fact]


class EgressBlockedError(Exception):
    """Raised when the pipeline must fail closed.

    ``audit_id`` lets callers correlate the failure with its audit record.
    ``reason`` is a stable, non-data-bearing category used in audit output.
    """

    def __init__(self, audit_id: str, reason: str) -> None:
        self.audit_id = audit_id
        self.reason = reason
        # No user data is included in the message: reason carries no text body.
        super().__init__(f"egress blocked: {reason}")
