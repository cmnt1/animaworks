from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Dynamic model routing for Inbox/chat requests.

Heuristic-first, preemptive escalation: when a request likely needs Bash or
external tools (``animaworks-tool`` dispatch, Gmail/Slack/GitHub/etc.) and the
configured background model has weak ``tool_use_capability``, route the
request to the main model instead.  This keeps heartbeat/cron on the cheap
background model while lifting weak-model ceilings for actual work.

No session conversion happens here: the router picks the ``ModelConfig``
before any LLM turn runs, so history compatibility is irrelevant.
"""

import logging
from typing import TYPE_CHECKING

from core.config.model_mode import resolve_tool_use_capability

if TYPE_CHECKING:
    from core.schemas import ModelConfig

logger = logging.getLogger("animaworks.model_router")

# Keyword hints that a request needs Bash / external tools / significant
# mechanical work.  Includes English, Japanese, and product-specific tokens
# observed in real inbox traffic.  Kept permissive on purpose — a false
# positive costs API budget, a false negative costs a failed task.
_BASH_KEYWORDS: tuple[str, ...] = (
    # Direct tool invocation
    "animaworks-tool",
    "animaworks tool",
    "bash",
    "shell",
    "run_command",
    "execute_command",
    "command:",
    # External services
    "gmail",
    "slack",
    "chatwork",
    "discord",
    "line",
    "telegram",
    "notebooklm",
    "github",
    "aws",
    "web_search",
    "web search",
    "x_search",
    "search_threads",
    "image_gen",
    "novelai",
    "meshy",
    # File/code mechanics
    "write file",
    "create file",
    "make file",
    "ファイル作成",
    "ファイルを作",
    "スクリプト",
    "script",
    # Japanese action verbs that typically imply real work
    "実行して",
    "起動",
    "送って",
    "送信",
    "投稿",
    "返信",
    "作って",
    "調べて",
    "確認して",
    "取得",
    "一覧",
    "チェック",
)

# Triggers that should bypass routing entirely.  Heartbeat and consolidation
# legitimately run on the background model; we do not want to silently
# upgrade them to the main model just because the observation checklist
# mentions the word "gmail".
_ROUTING_EXCLUDED_TRIGGERS: frozenset[str] = frozenset(
    {"heartbeat"}
)


def _trigger_is_excluded(trigger: str) -> bool:
    if not trigger:
        return False
    if trigger in _ROUTING_EXCLUDED_TRIGGERS:
        return True
    # Prefix matches: consolidation:*, cron:*
    if trigger.startswith("consolidation:") or trigger.startswith("cron:"):
        return True
    return False


def _needs_heavy_tools(body: str) -> bool:
    if not body:
        return False
    lower = body.lower()
    return any(kw in lower for kw in _BASH_KEYWORDS)


def route_model_config(
    main_config: ModelConfig,
    bg_config: ModelConfig | None,
    body: str,
    trigger: str,
) -> ModelConfig | None:
    """Return the ``ModelConfig`` to run this request on, or ``None`` for main.

    Logic:
      * No background override configured → return ``None`` (use main).
      * Excluded trigger (heartbeat/cron/consolidation) → return ``bg_config``.
      * Background model has ``high``/``medium`` capability → return
        ``bg_config`` (trust it).
      * Background model has ``low``/``none`` capability AND body contains
        Bash/tool keywords → return ``None`` (escalate to main).
      * Otherwise → return ``bg_config`` (give bg a chance on light requests).
    """
    if bg_config is None:
        return None

    if _trigger_is_excluded(trigger):
        return bg_config

    capability = resolve_tool_use_capability(bg_config.model)
    if capability in ("high", "medium"):
        return bg_config

    if _needs_heavy_tools(body):
        logger.info(
            "model_router: preemptive escalation to main model "
            "(bg=%s capability=%s trigger=%s)",
            bg_config.model,
            capability,
            trigger,
        )
        return None

    return bg_config


__all__ = [
    "route_model_config",
    "_needs_heavy_tools",
    "_trigger_is_excluded",
]
