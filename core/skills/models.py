from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Hermes-compatible Pydantic models for skill metadata."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from core.schemas import SkillMeta

# ── Enumerations ────────────────────────────────────────────


class SkillTrustLevel(str, Enum):  # noqa: UP042
    """Trust tier describing provenance and policy for a skill."""

    builtin = "builtin"
    official = "official"
    trusted = "trusted"
    community = "community"
    untrusted = "untrusted"
    quarantine = "quarantine"
    blocked = "blocked"


class SkillScanVerdict(str, Enum):  # noqa: UP042
    """Outcome classification from automated skill security review."""

    safe = "safe"
    caution = "caution"
    warn = "warn"
    dangerous = "dangerous"


# ── Supporting models ───────────────────────────────────────


class SkillSource(BaseModel):
    """Where a skill came from and how it is attributed."""

    type: str = "local"
    identifier: str | None = None
    owner_anima: str | None = None
    origin: str | None = None


class SkillSecurityScan(BaseModel):
    """Security scan summary attached to skill metadata."""

    verdict: SkillScanVerdict = SkillScanVerdict.safe
    scan_status: str = "not_scanned"
    findings: list[dict] = Field(default_factory=list)
    scanned_at: datetime | None = None
    scanner_version: str | None = None


# ── SkillMetadata ─────────────────────────────────────────


class SkillMetadata(BaseModel):
    """Full skill metadata record aligned with Hermes skill manifests."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    category: str | None = None
    platforms: list[str] = Field(default_factory=list)
    requires_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    trust_level: SkillTrustLevel = SkillTrustLevel.trusted
    source: SkillSource = Field(default_factory=SkillSource)
    version: int = 1
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    patch_count: int = 0
    last_used_at: datetime | None = None
    last_updated_at: datetime | None = None
    pinned: bool = False
    protected: bool = False
    security: SkillSecurityScan = Field(default_factory=SkillSecurityScan)
    path: Path | None = None
    is_common: bool = False
    is_procedure: bool = False

    def to_legacy(self) -> SkillMeta:
        """Convert to the legacy ``SkillMeta`` dataclass used elsewhere in core.

        Returns:
            ``SkillMeta`` suitable for code paths that still expect frontmatter-
            style metadata only.
        """
        from core.schemas import SkillMeta

        return SkillMeta(
            name=self.name,
            description=self.description,
            path=self.path or Path("."),
            is_common=self.is_common,
            allowed_tools=self.allowed_tools,
        )
