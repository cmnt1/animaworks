from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Skill metadata package — Hermes-compatible loader and index.

Re-exports for convenience::

    from core.skills import SkillMetadata, SkillTrustLevel, SkillIndex
    from core.skills import load_skill_metadata, load_skill_document
"""

from core.skills.guard import SkillScanner
from core.skills.index import SkillIndex
from core.skills.loader import (
    is_skill_blocked,
    load_skill_body,
    load_skill_document,
    load_skill_metadata,
)
from core.skills.models import (
    ScanFinding,
    ScanResult,
    SkillMetadata,
    SkillScanVerdict,
    SkillSecurityScan,
    SkillSource,
    SkillTrustLevel,
    ThreatPattern,
)

__all__ = [
    "ScanFinding",
    "ScanResult",
    "SkillIndex",
    "SkillMetadata",
    "SkillScanVerdict",
    "SkillScanner",
    "SkillSecurityScan",
    "SkillSource",
    "SkillTrustLevel",
    "ThreatPattern",
    "is_skill_blocked",
    "load_skill_body",
    "load_skill_document",
    "load_skill_metadata",
]
