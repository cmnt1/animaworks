from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Procedure-to-skill promotion pipeline.

Generated skills are written to ``skills/quarantine`` first. Approval is a
separate explicit step that moves the skill into the active personal catalog.
"""

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from core.memory._io import atomic_write_text
from core.memory.frontmatter import parse_frontmatter
from core.skills.guard import SCANNER_VERSION, SkillScanner
from core.skills.models import ScanResult, SkillScanVerdict, SkillUsageEventType
from core.skills.usage import SkillUsageTracker
from core.time_utils import now_iso

PROMOTION_DRAFT_CREATED = "promotion_draft_created"
PROMOTION_APPROVED = "promotion_approved"


@dataclass(slots=True)
class PromotionPolicy:
    """Thresholds for detecting procedures that are worth promotion."""

    success_count_threshold: int = 3
    confidence_threshold: float = 0.8
    failure_count_max: int = 1
    last_used_within_days: int = 180
    auto_activate: bool = False
    require_approval_on_warn: bool = True


@dataclass(slots=True)
class ProcedurePromotionCandidate:
    """A procedure and the decision inputs for promotion eligibility."""

    path: Path
    name: str
    metadata: dict[str, Any]
    success_count: int
    failure_count: int
    confidence: float
    last_used_at: str | None
    eligible: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkillPromotionResult:
    """Result from draft or approval actions."""

    status: str
    skill_name: str
    procedure_path: str | None = None
    quarantine_path: str | None = None
    active_path: str | None = None
    scan_verdict: str | None = None
    requires_human_approval: bool = True
    message: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    size_violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "skill_name": self.skill_name,
            "procedure_path": self.procedure_path,
            "quarantine_path": self.quarantine_path,
            "active_path": self.active_path,
            "scan_verdict": self.scan_verdict,
            "requires_human_approval": self.requires_human_approval,
            "message": self.message,
            "findings": self.findings,
            "size_violations": self.size_violations,
        }


class ProcedureToSkillConverter:
    """Convert proven procedures into reviewed personal skills."""

    def __init__(
        self,
        anima_dir: Path,
        *,
        scanner: SkillScanner | None = None,
        policy: PromotionPolicy | None = None,
        owner_anima: str | None = None,
    ) -> None:
        self._anima_dir = anima_dir
        self._procedures_dir = anima_dir / "procedures"
        self._skills_dir = anima_dir / "skills"
        self._quarantine_dir = self._skills_dir / "quarantine"
        self._audit_path = anima_dir / "state" / "skill_promotion.jsonl"
        self._scanner = scanner or SkillScanner()
        self._policy = policy or PromotionPolicy()
        self._owner_anima = owner_anima or anima_dir.name

    @property
    def policy(self) -> PromotionPolicy:
        return self._policy

    def find_candidates(self, *, eligible_only: bool = True) -> list[ProcedurePromotionCandidate]:
        """Return procedure files that satisfy, or nearly satisfy, promotion policy."""
        if not self._procedures_dir.exists():
            return []

        candidates: list[ProcedurePromotionCandidate] = []
        for path in sorted(self._procedures_dir.glob("*.md")):
            candidate = self.candidate_from_path(path)
            if candidate is None:
                continue
            if eligible_only and not candidate.eligible:
                continue
            candidates.append(candidate)
        return candidates

    def candidate_from_path(self, path: str | Path) -> ProcedurePromotionCandidate | None:
        procedure_path = self._resolve_procedure_path(path)
        if not procedure_path.exists():
            return None

        meta, _body = parse_frontmatter(procedure_path.read_text(encoding="utf-8"))
        success_count = _as_int(meta.get("success_count"), default=0)
        failure_count = _as_int(meta.get("failure_count"), default=0)
        confidence = _as_float(meta.get("confidence"), default=0.0)
        last_used_at = _as_optional_str(meta.get("last_used") or meta.get("last_used_at"))

        reasons: list[str] = []
        if success_count < self._policy.success_count_threshold:
            reasons.append("success_count_below_threshold")
        if confidence < self._policy.confidence_threshold:
            reasons.append("confidence_below_threshold")
        if failure_count > self._policy.failure_count_max:
            reasons.append("failure_count_above_threshold")
        if not _within_days(last_used_at, self._policy.last_used_within_days):
            reasons.append("last_used_outside_window")

        return ProcedurePromotionCandidate(
            path=procedure_path,
            name=_safe_skill_name(meta.get("name") or procedure_path.stem),
            metadata=meta,
            success_count=success_count,
            failure_count=failure_count,
            confidence=confidence,
            last_used_at=last_used_at,
            eligible=not reasons,
            reasons=reasons,
        )

    def create_quarantine_skill(
        self,
        procedure_path: str | Path,
        *,
        skill_name: str | None = None,
        metadata_overrides: dict[str, Any] | None = None,
    ) -> SkillPromotionResult:
        """Generate a quarantine SKILL.md and scan it before review."""
        source_path = self._resolve_procedure_path(procedure_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Procedure not found: {source_path}")

        text = source_path.read_text(encoding="utf-8")
        proc_meta, proc_body = parse_frontmatter(text)
        final_skill_name = _safe_skill_name(skill_name or proc_meta.get("name") or source_path.stem)
        quarantine_skill_dir = self._quarantine_dir / final_skill_name
        if quarantine_skill_dir.exists():
            raise FileExistsError(f"Quarantine skill already exists: {quarantine_skill_dir}")

        meta = self._build_skill_metadata(
            skill_name=final_skill_name,
            procedure_path=source_path,
            procedure_metadata=proc_meta,
            overrides=metadata_overrides or {},
        )
        body = self._build_skill_body(final_skill_name, proc_meta, proc_body)

        quarantine_skill_dir.mkdir(parents=True, exist_ok=False)
        skill_md = quarantine_skill_dir / "SKILL.md"
        self._write_skill_file(skill_md, meta, body)

        scan_result = self._scanner.scan_skill(quarantine_skill_dir, source="anima")
        meta["security"] = _scan_security_metadata(scan_result)
        meta["risk"]["requires_human_approval"] = _runtime_approval_required(meta["risk"], scan_result)
        self._write_skill_file(skill_md, meta, body)

        if scan_result.verdict == SkillScanVerdict.dangerous or scan_result.size_violations:
            shutil.rmtree(quarantine_skill_dir, ignore_errors=True)
            self._append_audit(
                {
                    "event_type": "promotion_draft_blocked",
                    "procedure_path": str(source_path.relative_to(self._anima_dir)),
                    "skill_name": final_skill_name,
                    "scan_verdict": scan_result.verdict.value,
                    "size_violations": scan_result.size_violations,
                }
            )
            return SkillPromotionResult(
                status="blocked",
                skill_name=final_skill_name,
                procedure_path=str(source_path.relative_to(self._anima_dir)),
                scan_verdict=scan_result.verdict.value,
                requires_human_approval=True,
                message="Dangerous or oversized promoted skill draft was blocked before quarantine.",
                findings=[f.model_dump(mode="json") for f in scan_result.findings],
                size_violations=scan_result.size_violations,
            )

        self._append_audit(
            {
                "event_type": PROMOTION_DRAFT_CREATED,
                "procedure_path": str(source_path.relative_to(self._anima_dir)),
                "skill_name": final_skill_name,
                "target_path": str(skill_md.relative_to(self._anima_dir)),
                "scan_verdict": scan_result.verdict.value,
                "requires_human_approval": True,
            }
        )

        return SkillPromotionResult(
            status="review",
            skill_name=final_skill_name,
            procedure_path=str(source_path.relative_to(self._anima_dir)),
            quarantine_path=str(skill_md.relative_to(self._anima_dir)),
            scan_verdict=scan_result.verdict.value,
            requires_human_approval=True,
            message="Quarantine skill draft created. Human approval is required before activation.",
            findings=[f.model_dump(mode="json") for f in scan_result.findings],
            size_violations=scan_result.size_violations,
        )

    def approve_skill(self, skill_name: str, *, approved_by: str) -> SkillPromotionResult:
        """Move a reviewed quarantine skill into the active personal catalog."""
        final_skill_name = _safe_skill_name(skill_name)
        quarantine_skill_dir = self._quarantine_dir / final_skill_name
        quarantine_skill_md = quarantine_skill_dir / "SKILL.md"
        if not quarantine_skill_md.exists():
            raise FileNotFoundError(f"Quarantine skill not found: {quarantine_skill_md}")

        active_skill_dir = self._skills_dir / final_skill_name
        if active_skill_dir.exists():
            raise FileExistsError(f"Active skill already exists: {active_skill_dir}")

        meta, body = parse_frontmatter(quarantine_skill_md.read_text(encoding="utf-8"))
        scan = self._scanner.scan_skill(quarantine_skill_dir, source="anima")
        if scan.verdict == SkillScanVerdict.dangerous or scan.size_violations:
            raise ValueError("Dangerous or oversized quarantine skill cannot be approved")

        meta["security"] = _scan_security_metadata(scan)
        meta["trust_level"] = "trusted"
        meta["promotion_status"] = "active"
        meta["approved_by"] = approved_by
        meta["approved_at"] = now_iso()
        meta.setdefault("risk", {})
        meta["risk"]["requires_human_approval"] = _runtime_approval_required(meta["risk"], scan)

        self._write_skill_file(quarantine_skill_md, meta, body)
        active_skill_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(quarantine_skill_dir), str(active_skill_dir))

        SkillUsageTracker(self._anima_dir).record(
            final_skill_name,
            SkillUsageEventType.create,
            is_common=False,
            notes="procedure_promotion_approved",
        )
        self._append_audit(
            {
                "event_type": PROMOTION_APPROVED,
                "skill_name": final_skill_name,
                "target_path": str((active_skill_dir / "SKILL.md").relative_to(self._anima_dir)),
                "approved_by": approved_by,
                "scan_verdict": scan.verdict.value,
            }
        )

        return SkillPromotionResult(
            status="active",
            skill_name=final_skill_name,
            active_path=str((active_skill_dir / "SKILL.md").relative_to(self._anima_dir)),
            scan_verdict=scan.verdict.value,
            requires_human_approval=meta["risk"]["requires_human_approval"],
            message="Skill approved and activated.",
            findings=[f.model_dump(mode="json") for f in scan.findings],
            size_violations=scan.size_violations,
        )

    def _resolve_procedure_path(self, path: str | Path) -> Path:
        raw = Path(path)
        target = raw if raw.is_absolute() else self._anima_dir / raw
        resolved = target.resolve()
        procedures_root = self._procedures_dir.resolve()
        if not resolved.is_relative_to(procedures_root) or resolved.suffix.lower() != ".md":
            raise ValueError("Procedure path must point to a .md file under procedures/")
        return resolved

    def _build_skill_metadata(
        self,
        *,
        skill_name: str,
        procedure_path: Path,
        procedure_metadata: dict[str, Any],
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        description = _first_non_empty(
            overrides.get("description"),
            procedure_metadata.get("description"),
            procedure_metadata.get("title"),
            f"Promoted procedure skill for {skill_name}",
        )
        use_when = _as_list(overrides.get("use_when") or procedure_metadata.get("use_when") or description)
        trigger_phrases = _as_list(
            overrides.get("trigger_phrases")
            or procedure_metadata.get("trigger_phrases")
            or skill_name.replace("-", " ")
        )
        negative_phrases = _as_list(
            overrides.get("negative_phrases")
            or procedure_metadata.get("negative_phrases")
            or procedure_metadata.get("do_not_use_when")
        )
        domains = _as_list(overrides.get("domains") or procedure_metadata.get("domains") or procedure_metadata.get("tags"))
        if not domains:
            domains = ["general"]
        tags = _as_list(overrides.get("tags") or procedure_metadata.get("tags"))
        risk = _normalise_risk(overrides.get("risk") or procedure_metadata.get("risk") or {})

        return {
            "name": skill_name,
            "description": description,
            "version": 1,
            "trust_level": "quarantine",
            "promotion_status": "review",
            "source": {
                "type": "anima",
                "owner_anima": self._owner_anima,
                "origin": "procedure_promotion",
                "identifier": str(procedure_path.relative_to(self._anima_dir)),
            },
            "use_when": use_when,
            "trigger_phrases": trigger_phrases,
            "negative_phrases": negative_phrases,
            "domains": domains,
            "tags": tags,
            "risk": risk,
        }

    def _build_skill_body(
        self,
        skill_name: str,
        procedure_metadata: dict[str, Any],
        procedure_body: str,
    ) -> str:
        title = _first_non_empty(procedure_metadata.get("title"), skill_name.replace("-", " ").title())
        body = procedure_body.strip()
        if not body:
            body = f"# {title}\n\nFollow the promoted procedure for {skill_name}."
        if "## Pitfalls" not in body:
            body += "\n\n## Pitfalls\n\n- Review the original procedure assumptions before applying this skill."
        if "## Verification" not in body:
            body += "\n\n## Verification\n\n- Confirm the task result and report the skill outcome."
        return body.rstrip() + "\n"

    def _write_skill_file(self, path: Path, metadata: dict[str, Any], body: str) -> None:
        frontmatter = yaml.dump(
            metadata,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ).strip()
        atomic_write_text(path, f"---\n{frontmatter}\n---\n\n{body.rstrip()}\n")

    def _append_audit(self, event: dict[str, Any]) -> None:
        event = {"ts": now_iso(), **event}
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self._audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _safe_skill_name(raw: Any) -> str:
    name = str(raw or "").strip().lower()
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"[^a-z0-9_.-]+", "-", name).strip("-._")
    if not name:
        raise ValueError("skill_name must contain at least one ASCII letter or digit")
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"Invalid skill name: {raw}")
    return name


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _normalise_risk(raw: Any) -> dict[str, bool]:
    if not isinstance(raw, dict):
        raw = {}
    risk = {
        "read_only": bool(raw.get("read_only", False)),
        "destructive": bool(raw.get("destructive", False)),
        "external_send": bool(raw.get("external_send", False)),
        "handles_untrusted_data": bool(raw.get("handles_untrusted_data", False)),
        "open_world": bool(raw.get("open_world", False)),
        "requires_human_approval": bool(raw.get("requires_human_approval", False)),
    }
    if risk["destructive"] or risk["external_send"] or risk["open_world"]:
        risk["requires_human_approval"] = True
    return risk


def _runtime_approval_required(risk: dict[str, Any], scan_result: ScanResult) -> bool:
    return bool(
        risk.get("requires_human_approval")
        or risk.get("destructive")
        or risk.get("external_send")
        or risk.get("open_world")
        or scan_result.verdict in {SkillScanVerdict.caution, SkillScanVerdict.warn}
    )


def _scan_security_metadata(scan_result: ScanResult) -> dict[str, Any]:
    return {
        "verdict": scan_result.verdict.value,
        "scan_status": "scanned",
        "findings": [f.model_dump(mode="json") for f in scan_result.findings],
        "scanned_at": datetime.now(UTC).isoformat(),
        "scanner_version": SCANNER_VERSION,
    }


def _within_days(value: str | None, days: int) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    return parsed >= cutoff
