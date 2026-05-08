from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Skill metadata package — Hermes-compatible loader and index.

Re-exports for convenience::

    from core.skills import SkillMetadata, SkillTrustLevel, SkillIndex
    from core.skills import load_skill_metadata, load_skill_document
"""

from core.skills.index import SkillIndex
from core.skills.loader import load_skill_body, load_skill_document, load_skill_metadata
from core.skills.models import (
    SkillMetadata,
    SkillScanVerdict,
    SkillSecurityScan,
    SkillSource,
    SkillTrustLevel,
)

__all__ = [
    "SkillIndex",
    "SkillMetadata",
    "SkillScanVerdict",
    "SkillSecurityScan",
    "SkillSource",
    "SkillTrustLevel",
    "load_skill_body",
    "load_skill_document",
    "load_skill_metadata",
]
