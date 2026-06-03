from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Provider-level cooldowns for transient LLM rate limits.

The usage governor manages broad activity levels from usage telemetry.  This
module handles the sharper signal emitted by providers themselves: HTTP 429 /
RATE_LIMIT_EXCEEDED.  When one Anima hits a provider rate limit, all Animas
using the same provider should briefly stand down instead of each burning a
full stream retry loop.
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import get_data_dir
from core.schemas import ModelConfig

logger = logging.getLogger("animaworks.provider_cooldown")

_STATE_FILE = "provider_cooldowns.json"
_DEFAULT_COOLDOWN_S = 120.0
_MIN_COOLDOWN_S = 60.0
_MAX_COOLDOWN_S = 900.0
_RETRY_AFTER_BUFFER_S = 10.0


@dataclass(frozen=True)
class ProviderCooldown:
    provider: str
    until_ts: float
    remaining_s: float
    reason: str
    model: str
    trigger: str
    count: int

    @property
    def until_iso(self) -> str:
        return datetime.fromtimestamp(self.until_ts, tz=timezone.utc).isoformat()


def provider_key_for_model_config(model_config: ModelConfig) -> str | None:
    """Return a shared provider key for cooldown purposes."""
    model = (model_config.model or "").strip().lower()
    credential = (model_config.credential or "").strip().lower()
    api_key_env = (model_config.api_key_env or "").strip().lower()

    if credential == "antigravity" or model.startswith(("antigravity/", "gemini/")) or api_key_env == "antigravity_api_key":
        return "gemini"
    if credential in {"anthropic", "claude"} or model.startswith(("anthropic/", "claude-")):
        return "claude"
    if credential == "openai" or model.startswith("openai/") or api_key_env == "openai_api_key":
        return "openai"
    if credential == "nanogpt" or model.startswith("nanogpt/"):
        return "nanogpt"
    if model.startswith("ollama/"):
        return None
    if "/" in model:
        return model.split("/", 1)[0]
    return credential or None


def get_provider_cooldown(provider: str | None, *, now_ts: float | None = None) -> ProviderCooldown | None:
    """Return the active cooldown for *provider*, if any."""
    if not provider:
        return None
    now_ts = time.time() if now_ts is None else now_ts
    state = _load_state()
    entry = state.get(provider)
    if not isinstance(entry, dict):
        return None
    until_ts = _as_float(entry.get("until_ts"))
    if until_ts <= now_ts:
        _clear_provider(state, provider)
        return None
    return ProviderCooldown(
        provider=provider,
        until_ts=until_ts,
        remaining_s=max(0.0, until_ts - now_ts),
        reason=str(entry.get("reason") or "provider rate limit"),
        model=str(entry.get("model") or ""),
        trigger=str(entry.get("trigger") or ""),
        count=int(_as_float(entry.get("count"), default=1.0)),
    )


def record_provider_rate_limit(
    provider: str | None,
    *,
    retry_after_s: float | None = None,
    trigger: str = "",
    model: str = "",
    reason: str = "HTTP 429/RATE_LIMIT_EXCEEDED",
    now_ts: float | None = None,
) -> ProviderCooldown | None:
    """Persist a provider cooldown and return the resulting active entry."""
    if not provider:
        return None
    now_ts = time.time() if now_ts is None else now_ts
    cooldown_s = _cooldown_seconds(retry_after_s)
    until_ts = now_ts + cooldown_s
    state = _load_state()
    previous = state.get(provider) if isinstance(state.get(provider), dict) else {}
    previous_until = _as_float(previous.get("until_ts")) if isinstance(previous, dict) else 0.0
    count = int(_as_float(previous.get("count"), default=0.0)) + 1 if isinstance(previous, dict) else 1
    if previous_until > until_ts:
        until_ts = previous_until
    state[provider] = {
        "until_ts": until_ts,
        "observed_ts": now_ts,
        "retry_after_s": retry_after_s,
        "reason": reason,
        "trigger": trigger,
        "model": model,
        "count": count,
    }
    _save_state(state)
    cooldown = get_provider_cooldown(provider, now_ts=now_ts)
    if cooldown:
        logger.warning(
            "Provider cooldown active: provider=%s remaining=%.1fs model=%s trigger=%s reason=%s",
            provider,
            cooldown.remaining_s,
            model,
            trigger,
            reason,
        )
    return cooldown


def clear_provider_cooldown(provider: str | None) -> None:
    """Clear one provider cooldown, primarily for tests and manual repair."""
    if not provider:
        return
    state = _load_state()
    _clear_provider(state, provider)


def format_cooldown_message(cooldown: ProviderCooldown) -> str:
    return (
        "RATE_LIMIT_DEFERRED: provider "
        f"{cooldown.provider} is cooling down for {cooldown.remaining_s:.0f}s "
        f"after {cooldown.reason}; until={cooldown.until_iso}"
    )


def _cooldown_seconds(retry_after_s: float | None) -> float:
    if retry_after_s is None:
        raw = _DEFAULT_COOLDOWN_S
    else:
        raw = float(retry_after_s) + _RETRY_AFTER_BUFFER_S
    return min(_MAX_COOLDOWN_S, max(_MIN_COOLDOWN_S, raw))


def _state_path() -> Path:
    override = os.environ.get("ANIMAWORKS_PROVIDER_COOLDOWN_FILE")
    if override:
        return Path(override).expanduser().resolve()
    return get_data_dir() / _STATE_FILE


def _load_state() -> dict[str, Any]:
    path = _state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        logger.warning("Failed to read provider cooldown state: %s", path, exc_info=True)
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _clear_provider(state: dict[str, Any], provider: str) -> None:
    if provider not in state:
        return
    state.pop(provider, None)
    _save_state(state)


def _as_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
