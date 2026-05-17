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
from core.skills.curator import (
    CuratorReplay,
    DuplicateCandidate,
    LifecycleSuggestion,
    SkillCurator,
)
from core.skills.index import SkillIndex
from core.skills.loader import (
    is_skill_blocked,
    is_skill_loadable,
    load_skill_body,
    load_skill_document,
    load_skill_metadata,
    skill_access_decision,
)
from core.skills.models import (
    ScanFinding,
    ScanResult,
    SkillCuratorEvent,
    SkillCuratorEventType,
    SkillLifecycleState,
    SkillMetadata,
    SkillRiskMetadata,
    SkillRoutingMetadata,
    SkillScanVerdict,
    SkillSecurityScan,
    SkillSource,
    SkillTrustLevel,
    SkillUsageEvent,
    SkillUsageEventType,
    SkillUsageStats,
    ThreatPattern,
)
from core.skills.promotion import (
    ProcedurePromotionCandidate,
    ProcedureToSkillConverter,
    PromotionPolicy,
    SkillPromotionResult,
)
from core.skills.router import SkillRouteCandidate, SkillRouter
from core.skills.usage import SkillUsageTracker

__all__ = [
    "ScanFinding",
    "ScanResult",
    "CuratorReplay",
    "DuplicateCandidate",
    "LifecycleSuggestion",
    "SkillCurator",
    "SkillIndex",
    "SkillCuratorEvent",
    "SkillCuratorEventType",
    "SkillLifecycleState",
    "SkillMetadata",
    "SkillPromotionResult",
    "SkillRouteCandidate",
    "SkillRouter",
    "SkillRiskMetadata",
    "SkillRoutingMetadata",
    "SkillScanVerdict",
    "SkillScanner",
    "SkillSecurityScan",
    "SkillSource",
    "SkillTrustLevel",
    "SkillUsageEvent",
    "SkillUsageEventType",
    "SkillUsageStats",
    "SkillUsageTracker",
    "ThreatPattern",
    "ProcedurePromotionCandidate",
    "ProcedureToSkillConverter",
    "PromotionPolicy",
    "is_skill_blocked",
    "is_skill_loadable",
    "load_skill_body",
    "load_skill_document",
    "load_skill_metadata",
    "skill_access_decision",
]
