from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Small metadata helpers for skill routing."""

from collections.abc import Sequence
from pathlib import Path

from core.memory.frontmatter import strip_frontmatter
from core.skills.models import SkillMetadata, SkillRiskMetadata


def merged_risk(meta: SkillMetadata) -> SkillRiskMetadata:
    base = meta.risk
    nested = meta.routing.risk
    return SkillRiskMetadata(
        read_only=base.read_only or nested.read_only,
        destructive=base.destructive or nested.destructive,
        external_send=base.external_send or nested.external_send,
        handles_untrusted_data=base.handles_untrusted_data or nested.handles_untrusted_data,
        credential=base.credential or nested.credential,
        production=base.production or nested.production,
        billing=base.billing or nested.billing,
        private_data=base.private_data or nested.private_data,
        requires_human_approval=base.requires_human_approval or nested.requires_human_approval,
        open_world=base.open_world or nested.open_world,
    )


def dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def has_strong_signal(reasons: Sequence[str]) -> bool:
    strong_prefixes = (
        "trigger:",
        "use_when:",
        "tag:",
        "tool:",
        "platform:",
        "example:",
        "dense:",
        "name:exact:",
        "name:identifier:",
        "path:exact:",
        "path:identifier:",
    )
    return any(reason.startswith(strong_prefixes) for reason in reasons)


def fill_routing_metadata_gaps(meta: dict, *, skill_name: str, description: str, body: str = "") -> dict:
    """Return deterministic routing metadata for auto-created skills."""
    result = dict(meta)
    text = body.strip()
    trigger = skill_name.replace("-", " ").strip()
    if not result.get("trigger_phrases"):
        result["trigger_phrases"] = [trigger] if trigger else []
    if not result.get("use_when"):
        result["use_when"] = [description] if description else result.get("trigger_phrases", [])
    if not result.get("domains") and not result.get("tags"):
        result["domains"] = ["general"]
    if not result.get("routing_examples"):
        first_line = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), "")
        example = first_line or description or trigger
        result["routing_examples"] = [example] if example else []
    return result


def read_body(path: Path | None, *, max_chars: int = 8000) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return strip_frontmatter(path.read_text(encoding="utf-8"))[:max_chars]
    except OSError:
        return ""
