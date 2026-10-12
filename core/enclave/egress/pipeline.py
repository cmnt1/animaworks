# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Egress pipeline: apply configured stages and fail closed on any error.

Runs the configured stages over the request facts, verifies the output
structure, and writes one audit record per run (success or failure). Any
stage failure produces an :class:`EgressBlockedError` carrying an ``audit_id``
so callers can correlate the block with its audit log entry.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.enclave.egress.audit import write_audit
from core.enclave.egress.config import EgressConfig
from core.enclave.egress.models import EgressBlockedError, EgressRequest, EgressResult, Fact
from core.enclave.egress.stages import EgressStageError, run_stage

logger = logging.getLogger(__name__)


class EgressPipeline:
    """A configured, reusable egress pipeline bound to a data directory."""

    def __init__(self, config: EgressConfig, data_dir: Path) -> None:
        self.config = config
        self.data_dir = data_dir

    def run(self, req: EgressRequest) -> EgressResult:
        audit_id = uuid4().hex
        stages_log: list[dict[str, Any]] = []
        in_facts = list(req.facts)

        current = list(req.facts)
        reason: str | None = None
        blocked = False
        try:
            for stage in self.config.stages:
                try:
                    current, count = run_stage(
                        stage,
                        current,
                        data_dir=self.data_dir,
                        case_id=req.case_id,
                    )
                except EgressStageError as exc:
                    stages_log.append({"type": stage.type, "ok": False, "replacements": 0, "error": exc.reason})
                    raise
                stages_log.append({"type": stage.type, "ok": True, "replacements": count, "error": None})
            out_facts = self._validate_output(current)
        except EgressStageError as exc:
            current = None
            out_facts = None
            blocked = True
            reason = exc.reason
            logger.warning("egress stage failed (audit_id=%s, reason=%s)", audit_id, reason)
        except Exception:  # unexpected error -> fail closed
            current = None
            out_facts = None
            blocked = True
            reason = "internal_error"
            logger.exception("egress pipeline internal error (audit_id=%s)", audit_id)

        write_audit(
            self.data_dir,
            audit_id=audit_id,
            request=req,
            input_facts=in_facts,
            output_facts=out_facts,
            stages=stages_log,
            blocked=blocked,
            reason=reason,
        )

        if blocked:
            raise EgressBlockedError(audit_id, reason or "unknown")

        return EgressResult(audit_id=audit_id, facts=out_facts)

    def _validate_output(self, facts: list[Fact]) -> list[Fact]:
        """Structural checks; any violation blocks the answer."""
        if len(facts) > self.config.max_facts:
            raise EgressStageError("too_many_facts")
        for fact in facts:
            if not isinstance(fact.fact, str):
                raise EgressStageError("non_string_fact")
            if len(fact.fact) > self.config.max_fact_chars:
                raise EgressStageError("fact_too_long")
            if not isinstance(fact.evidence, list):
                raise EgressStageError("non_list_evidence")
            for item in fact.evidence:
                if not isinstance(item, str):
                    raise EgressStageError("non_string_evidence")
                if len(item) > self.config.max_fact_chars:
                    raise EgressStageError("fact_too_long")
        return facts
