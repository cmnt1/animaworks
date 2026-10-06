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

from core.memory.facts.config import DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS, _coerce_timeout_seconds
from core.memory.facts.store import FactRecord

logger = logging.getLogger("animaworks.memory.fact_invalidation_llm")
_CODE_FENCE_RE = re.compile(r"```[a-zA-Z0-9_\-]*\s*\n(.*?)```", re.DOTALL)


def classify_fact_relation(new_fact: FactRecord, candidates: list[Any], anima_dir: Path) -> str:
    model, llm_extra, timeout, credential = _resolve_reconcile_llm_config(anima_dir)
    from core.llm.oneshot import one_shot_completion_sync

    text = one_shot_completion_sync(
        _user_prompt(new_fact, candidates),
        system_prompt=_SYSTEM_PROMPT,
        model=model,
        credential=credential,
        max_tokens=16,
        temperature=0.0,
        timeout=timeout,
        llm_extra=llm_extra,
        allow_agent_sdk_fallback=False,
    )
    if text is None:
        raise RuntimeError("Fact relation LLM returned no content")
    return text


def classify_fact_relations(new_fact: FactRecord, candidates: list[Any], anima_dir: Path) -> dict[str, str]:
    """Classify multiple candidate relations in a single LLM call."""
    if not candidates:
        return {}

    model, llm_extra, timeout, credential = _resolve_reconcile_llm_config(anima_dir)
    from core.llm.oneshot import one_shot_completion_sync

    text = one_shot_completion_sync(
        _batch_user_prompt(new_fact, candidates),
        system_prompt=_BATCH_SYSTEM_PROMPT,
        model=model,
        credential=credential,
        max_tokens=32 + 40 * len(candidates),
        temperature=0.0,
        timeout=timeout,
        llm_extra=llm_extra,
        allow_agent_sdk_fallback=False,
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


def _resolve_reconcile_llm_config(anima_dir: Path) -> tuple[str, dict[str, object], int, str]:
    """Resolve the model, llm_extra, timeout, and credential for fact reconciliation.

    Resolution order:
      1. ``config.consolidation.fact_reconcile_model`` (explicit model) +
         ``fact_reconcile_credential``.
      2. Otherwise the same result as :func:`core.memory.facts.config._resolve_extraction_config`
         (model, llm_extra, timeout, and credential). status.json's
         background_model is not used as an independent first choice here.
    """
    timeout = DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS
    llm_extra: dict[str, object] = {}
    try:
        from core.config import load_config

        cfg = load_config()
        timeout = _coerce_timeout_seconds(
            getattr(getattr(cfg, "rag", None), "fact_extraction_timeout_seconds", None),
            timeout,
        )
        consolidation = getattr(cfg, "consolidation", None)
        fact_model = getattr(consolidation, "fact_reconcile_model", None)
        if fact_model:
            fact_credential = getattr(consolidation, "fact_reconcile_credential", None) or ""
            return str(fact_model), llm_extra, timeout, str(fact_credential)
    except Exception:
        logger.debug("Failed to load fact reconciliation model from config", exc_info=True)

    from core.memory.facts.config import _resolve_extraction_config

    model, resolved_extra, _locale, extraction_timeout, credential = _resolve_extraction_config(anima_dir)
    return model, resolved_extra, extraction_timeout or timeout, credential


_SYSTEM_PROMPT = (
    "You classify whether a new memory fact should be reconciled with existing active facts. "
    "Return exactly one label and no other text: CONTRADICT, COMPLEMENT, DUPLICATE, or ADD."
)
_BATCH_SYSTEM_PROMPT = (
    "You classify whether a new memory fact should be reconciled with existing active facts. "
    'Return exactly one JSON object with a "labels" mapping from every candidate fact_id to '
    "one label: CONTRADICT, COMPLEMENT, DUPLICATE, or ADD."
)
