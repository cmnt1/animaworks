from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""LLM classifier helper for legacy fact reconciliation."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from core.config.helper_models import ResolvedHelperModel, resolve_helper_model
from core.config.schemas import AnimaWorksConfig
from core.memory.facts.config import DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS, _coerce_timeout_seconds
from core.memory.facts.store import FactRecord

logger = logging.getLogger("animaworks.memory.fact_invalidation_llm")
_CODE_FENCE_RE = re.compile(r"```[a-zA-Z0-9_\-]*\s*\n(.*?)```", re.DOTALL)


def classify_fact_relation(new_fact: FactRecord, candidates: list[Any], anima_dir: Path) -> str:
    helper, timeout = _resolve_reconcile_helper_model(anima_dir)
    from core.llm.helper_completion import one_shot_helper_completion_sync

    text = one_shot_helper_completion_sync(
        _user_prompt(new_fact, candidates),
        role="fact_reconcile",
        anima_dir=anima_dir,
        resolved=helper,
        system_prompt=_SYSTEM_PROMPT,
        max_tokens=16,
        temperature=0.0,
        timeout=timeout,
        llm_extra={},
    )
    if text is None:
        raise RuntimeError("Fact relation LLM returned no content")
    return text


def classify_fact_relations(new_fact: FactRecord, candidates: list[Any], anima_dir: Path) -> dict[str, str]:
    """Classify multiple candidate relations in a single LLM call."""
    if not candidates:
        return {}

    helper, timeout = _resolve_reconcile_helper_model(anima_dir)
    from core.llm.helper_completion import one_shot_helper_completion_sync

    text = one_shot_helper_completion_sync(
        _batch_user_prompt(new_fact, candidates),
        role="fact_reconcile",
        anima_dir=anima_dir,
        resolved=helper,
        system_prompt=_BATCH_SYSTEM_PROMPT,
        max_tokens=32 + 40 * len(candidates),
        temperature=0.0,
        timeout=timeout,
        llm_extra={},
    )
    if text is None:
        raise RuntimeError("Fact relation LLM returned no content")

    body = str(text).strip()
    fence_match = _CODE_FENCE_RE.search(body)
    if fence_match:
        body = fence_match.group(1)
    payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("labels"), dict):
        raise ValueError("Fact relation LLM response must contain a labels object")
    return {str(fact_id): str(label) for fact_id, label in payload["labels"].items()}


def _candidate_facts_json(candidates: list[Any]) -> str:
    return json.dumps(
        [
            {
                "fact_id": candidate.record.fact_id,
                "text": candidate.record.text,
                "source_entity": candidate.record.source_entity,
                "target_entity": candidate.record.target_entity,
                "edge_type": candidate.record.edge_type,
                "valid_at": candidate.record.valid_at,
                "recorded_at": candidate.record.recorded_at,
                "valid_until": candidate.record.valid_until,
                "similarity": round(candidate.score, 4),
            }
            for candidate in candidates
        ],
        ensure_ascii=False,
    )


def _relation_prompt_context(new_fact: FactRecord, candidates: list[Any]) -> str:
    candidates_json = _candidate_facts_json(candidates)
    return (
        "New fact JSON:\n"
        f"{json.dumps(new_fact.to_dict(), ensure_ascii=False)}\n\n"
        "Existing active candidate facts JSON:\n"
        f"{candidates_json}\n\n"
        "Definitions:\n"
        "- DUPLICATE: same meaning, no new durable information.\n"
        "- CONTRADICT: cannot both be true for the same time period.\n"
        "- COMPLEMENT: compatible additional detail about the same subject.\n"
        "- ADD: distinct fact that should be appended.\n\n"
    )


def _user_prompt(new_fact: FactRecord, candidates: list[Any]) -> str:
    return f"{_relation_prompt_context(new_fact, candidates)}Label:"


def _batch_user_prompt(new_fact: FactRecord, candidates: list[Any]) -> str:
    return (
        f"{_relation_prompt_context(new_fact, candidates)}"
        'Return exactly a JSON object of the form {"labels": {"<fact_id>": "LABEL"}} '
        "with an entry for every candidate. LABEL must be exactly one of: "
        "DUPLICATE, CONTRADICT, COMPLEMENT, or ADD."
    )


def _resolve_reconcile_helper_model(anima_dir: Path) -> tuple[ResolvedHelperModel, int]:
    """Resolve the reconciliation role and its legacy per-call timeout."""
    try:
        from core.config import load_config

        config = load_config()
    except Exception:
        logger.debug("Failed to load fact reconciliation config", exc_info=True)
        config = AnimaWorksConfig()
    timeout = _coerce_timeout_seconds(
        getattr(getattr(config, "rag", None), "fact_extraction_timeout_seconds", None),
        DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS,
    )
    return resolve_helper_model("fact_reconcile", anima_dir, config=config), timeout


def _resolve_reconcile_llm_config(anima_dir: Path) -> tuple[str, dict[str, object], int, str]:
    """Compatibility facade for older fact-reconciliation callers."""
    helper, timeout = _resolve_reconcile_helper_model(anima_dir)
    return helper.model, {}, timeout, helper.credential or ""


_SYSTEM_PROMPT = (
    "You classify whether a new memory fact should be reconciled with existing active facts. "
    "Return exactly one label and no other text: CONTRADICT, COMPLEMENT, DUPLICATE, or ADD."
)
_BATCH_SYSTEM_PROMPT = (
    "You classify whether a new memory fact should be reconciled with existing active facts. "
    'Return exactly one JSON object with a "labels" mapping from every candidate fact_id to '
    "one label: CONTRADICT, COMPLEMENT, DUPLICATE, or ADD."
)
