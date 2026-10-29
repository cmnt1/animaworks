# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Egress pipeline: mask outgoing answers before they leave an enclave.

This package provides a pure library (no server or HTTP wiring) that applies a
configurable pipeline of masking stages to answer facts, so that no personal
information remains before data exits an isolated instance. Any stage failure
fails the whole answer closed and leaves an audit record.
"""

from __future__ import annotations

from core.enclave.egress.models import (
    EgressBlockedError,
    EgressRequest,
    EgressResult,
    Fact,
)
from core.enclave.egress.pipeline import EgressPipeline

__all__ = [
    "EgressBlockedError",
    "EgressPipeline",
    "EgressRequest",
    "EgressResult",
    "Fact",
]
