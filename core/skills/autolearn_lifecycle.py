from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Lifecycle integration for deterministic autonomous skill learning."""

import logging
from typing import Any

from core.skills.autolearn import AutonomousSkillLearner

logger = logging.getLogger(__name__)


def run_autonomous_skill_learning_for(anima: Any):
    """Run deterministic skill auto-learning after successful consolidation."""
    try:
        result = AutonomousSkillLearner(anima.anima_dir).run()
    except Exception:
        logger.debug("[%s] autonomous skill learning failed", anima.name, exc_info=True)
        return None

    for created in result.created:
        anima._activity.log(
            "skill_auto_created",
            summary=created.message,
            meta={
                "skill_name": created.skill_name,
                "path": created.active_path,
                "scan_verdict": created.scan_verdict,
            },
        )
    if result.skipped or result.blocked:
        anima._activity.log(
            "skill_autolearn_summary",
            summary=f"Autonomous skill learning skipped={len(result.skipped)} blocked={len(result.blocked)}",
            meta={
                "skipped": [
                    {
                        "skill_name": skip.skill_name,
                        "procedure_path": skip.procedure_path,
                        "reason": skip.reason,
                        "related_skill": skip.related_skill,
                    }
                    for skip in result.skipped
                ],
                "blocked": [blocked.to_dict() for blocked in result.blocked],
            },
        )
    return result
