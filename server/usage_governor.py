from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Usage Governor — automatic throttling based on provider usage data.

Periodically fetches usage from the internal usage module, evaluates a
configurable rule-set, and suspends cloud-provider Anima processes to
stay within budget.  Local-LLM (ollama) animas are never affected.

Policy is stored in ``usage_policy.json`` next to ``config.json``.
Governor runtime state (suspended animas) is kept in
``usage_governor_state.json`` so recovery works across restarts.

Credential-to-provider mapping:
  - ``anthropic`` → ``claude`` rules
  - ``openai``    → ``openai`` rules
  - ``ollama``    → exempt (local)

Rule mode:
  - **time_proportional** — compares ``usage_remaining_%`` against
    ``time_remaining_%``; room (= remaining / time) determines throttle
    severity.  ``1.0`` means usage is on pace, values above ``1.0`` mean
    headroom, and values below ``1.0`` mean over-consuming.
    ``throttle_rules`` with ``room_under`` thresholds fire when room drops
    below the specified value.
  - **burn_rate_landing** estimates current burn rate and adjusts activity so
    projected remaining usage at reset lands near ``target_remaining_at_reset``.
    Early/low-signal windows fall back to ``time_proportional``.
  - **threshold** (list format, legacy) — fixed remaining-% cut-offs.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.i18n import t

logger = logging.getLogger("animaworks.usage_governor")

# Map anima credential values to policy provider keys
_CREDENTIAL_TO_PROVIDER: dict[str, str] = {
    "anthropic": "claude",
    "openai": "openai",
    "nanogpt": "nanogpt",
    "opencode-go": "opencode_go",
}

# ── Policy schema ────────────────────────────────────────────────────────────


def _default_throttle_rules() -> list[dict[str, int | float]]:
    return [
        {"room_under": 4, "activity_level": 400},
        {"room_under": 3, "activity_level": 300},
        {"room_under": 2, "activity_level": 200},
        {"room_under": 1.5, "activity_level": 150},
        {"room_under": 1.4, "activity_level": 140},
        {"room_under": 1.3, "activity_level": 130},
        {"room_under": 1.2, "activity_level": 120},
        {"room_under": 1.1, "activity_level": 110},
        {"room_under": 1, "activity_level": 100},
        {"room_under": 0.9, "activity_level": 90},
        {"room_under": 0.8, "activity_level": 80},
        {"room_under": 0.7, "activity_level": 70},
        {"room_under": 0.6, "activity_level": 60},
        {"room_under": 0.5, "activity_level": 50},
        {"room_under": 0.4, "activity_level": 40},
        {"room_under": 0.3, "activity_level": 30},
        {"room_under": 0.2, "activity_level": 20},
        {"room_under": 0.1, "activity_level": 10},
    ]


def _default_window_policy() -> dict[str, Any]:
    return {
        "mode": "burn_rate_landing",
        "target_remaining_at_reset": 0,
        "min_elapsed_pct": 3,
        "min_used_pct": 1,
        "min_activity_level": 1,
        "max_activity_level": 400,
        "fallback_mode": "time_proportional",
        "throttle_rules": _default_throttle_rules(),
    }


DEFAULT_POLICY: dict[str, Any] = {
    "enabled": True,
    "check_interval_seconds": 120,
    "hard_floor_pct": 15,  # absolute minimum remaining % for any window
    "hard_floor_activity_level": 5,
    "providers": {
        "claude": {
            "five_hour": _default_window_policy(),
            "seven_day": _default_window_policy(),
        },
        "openai": {
            "5h": _default_window_policy(),
            "Week": _default_window_policy(),
        },
        "nanogpt": {
            "Week": _default_window_policy(),
        },
        "opencode_go": {
            "5h": _default_window_policy(),
            "Week": _default_window_policy(),
            "Month": _default_window_policy(),
        },
    },
    "suspend_thresholds": {
        "non_essential_below": 30,
        "all_except_coo_below": 15,
    },
    "coo_anima": "sakura",
    "essential_animas": ["sakura"],
    "calibration": {
        "enabled": True,
        "min_observation_sec": 600,
        "min_used_pct": 1,
        "base_burn_ema_alpha": 0.1,
        "norm_burn_ema_alpha": 0.2,
        "low_activity_threshold_pct": 20,
        "initial_base_burn_per_day_pct": 0,
        "calibration_log_max_entries": 5000,
    },
}


# Activity history retention — keep one week of (timestamp, applied level)
# samples per provider so calibration can survive restarts and inspect
# week-window observations.
_HISTORY_RETENTION_SEC = 7 * 24 * 3600


# ── Governor state ───────────────────────────────────────────────────────────


_RELOGIN_MAX_PER_HOUR = 3
_RELOGIN_COOLDOWN_SECONDS = 600  # 10 min after consecutive failures


class GovernorState:
    """Mutable runtime state persisted to ``usage_governor_state.json``."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self.suspended_animas: list[str] = []
        self.reason: str = ""
        self.since: str = ""
        self.last_check: float = 0.0
        self.last_usage: dict[str, Any] = {}
        # Legacy-compatible provider activity map.  New readers prefer the
        # explicit front/background maps below.
        self.governor_activity_level_by_provider: dict[str, int | None] = {}
        self.front_activity_level_by_provider: dict[str, int | None] = {}
        self.background_activity_level_by_provider: dict[str, int | None] = {}
        self._relogin_timestamps: dict[str, list[float]] = {}
        self._relogin_cooldown_until: dict[str, float] = {}
        # Per-provider calibration EMA snapshots.  Updated by _tick() and used
        # by _evaluate_burn_rate_landing to predict burn at activity_level=100%.
        self.calibration_by_provider: dict[str, dict[str, Any]] = {}
        self._load()

    def can_relogin(self, provider: str) -> bool:
        """Return True if a relogin attempt is allowed for *provider*."""
        now = time.time()
        if self._relogin_cooldown_until.get(provider, 0) > now:
            return False
        recent = [t for t in self._relogin_timestamps.get(provider, []) if now - t < 3600]
        self._relogin_timestamps[provider] = recent
        return len(recent) < _RELOGIN_MAX_PER_HOUR

    def record_relogin(self, provider: str, *, success: bool) -> None:
        """Record a relogin attempt.  On failure, activate cooldown."""
        now = time.time()
        self._relogin_timestamps.setdefault(provider, []).append(now)
        if not success:
            self._relogin_cooldown_until[provider] = now + _RELOGIN_COOLDOWN_SECONDS

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text("utf-8"))
            self.suspended_animas = data.get("suspended_animas", [])
            self.reason = data.get("reason", "")
            self.since = data.get("since", "")
            # Prefer role-specific maps; fall back to legacy per-provider map,
            # then to legacy single-value field.
            legacy_map = data.get("governor_activity_level_by_provider")
            front_map = data.get("front_activity_level_by_provider")
            bg_map = data.get("background_activity_level_by_provider")
            by_provider = front_map if isinstance(front_map, dict) else legacy_map
            if isinstance(by_provider, dict):
                self.governor_activity_level_by_provider = {
                    k: v for k, v in by_provider.items() if v is None or isinstance(v, int)
                }
                self.front_activity_level_by_provider = dict(self.governor_activity_level_by_provider)
            else:
                legacy = data.get("governor_activity_level")
                if legacy is not None:
                    # Migration: apply legacy single value to all tracked providers
                    self.governor_activity_level_by_provider = {
                        "claude": legacy,
                        "openai": legacy,
                        "nanogpt": legacy,
                        "opencode_go": legacy,
                    }
                    self.front_activity_level_by_provider = dict(self.governor_activity_level_by_provider)
            if isinstance(bg_map, dict):
                self.background_activity_level_by_provider = {
                    k: v for k, v in bg_map.items() if v is None or isinstance(v, int)
                }
            else:
                self.background_activity_level_by_provider = dict(self.governor_activity_level_by_provider)
            calib = data.get("calibration_by_provider")
            if isinstance(calib, dict):
                self.calibration_by_provider = {
                    k: dict(v) for k, v in calib.items() if isinstance(v, dict)
                }
        except Exception:
            logger.debug("Failed to load governor state", exc_info=True)

    def save(self) -> None:
        data = {
            "suspended_animas": self.suspended_animas,
            "reason": self.reason,
            "since": self.since,
            "governor_activity_level_by_provider": self.governor_activity_level_by_provider,
            "front_activity_level_by_provider": self.front_activity_level_by_provider,
            "background_activity_level_by_provider": self.background_activity_level_by_provider,
            "calibration_by_provider": self.calibration_by_provider,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception:
            logger.warning("Failed to save governor state", exc_info=True)

    @property
    def history_path(self) -> Path:
        return self._path.parent / "usage_governor_history.json"

    @property
    def calibration_log_path(self) -> Path:
        return self._path.parent / "usage_governor_calibration.jsonl"

    @property
    def is_governing(self) -> bool:
        throttling = any(
            lvl is not None and lvl < 100
            for activity_map in (
                self.front_activity_level_by_provider,
                self.background_activity_level_by_provider,
                self.governor_activity_level_by_provider,
            )
            for lvl in activity_map.values()
        )
        return bool(self.suspended_animas) or bool(self.reason) or throttling


class GovernorHistory:
    """Per-provider applied activity_level history persisted separately.

    Stored as a step function: each entry is (timestamp, level) and the level
    is assumed to remain in effect until the next sample.  Old samples beyond
    ``_HISTORY_RETENTION_SEC`` (one week) are trimmed on every append.

    Persisted to ``usage_governor_history.json`` to avoid bloating the main
    state file with append-mostly time-series data.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        # provider_key -> list of [timestamp, level]
        self.history_by_provider: dict[str, list[list[float]]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text("utf-8"))
            raw = data.get("history_by_provider", {})
            if isinstance(raw, dict):
                for prov, entries in raw.items():
                    if not isinstance(entries, list):
                        continue
                    cleaned: list[list[float]] = []
                    for entry in entries:
                        if (
                            isinstance(entry, list)
                            and len(entry) == 2
                            and isinstance(entry[0], (int, float))
                            and isinstance(entry[1], (int, float))
                        ):
                            cleaned.append([float(entry[0]), float(entry[1])])
                    if cleaned:
                        self.history_by_provider[str(prov)] = cleaned
        except Exception:
            logger.debug("Failed to load governor history", exc_info=True)

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(
                    {"history_by_provider": self.history_by_provider},
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
        except Exception:
            logger.warning("Failed to save governor history", exc_info=True)

    def append(self, provider: str, ts: float, level: int | None) -> None:
        """Append a sample, treating None as 100 (unconstrained)."""
        effective = 100 if level is None else int(level)
        entries = self.history_by_provider.setdefault(provider, [])
        # Skip duplicate consecutive samples (keep file small)
        if entries and int(entries[-1][1]) == effective and ts - entries[-1][0] < 60:
            return
        entries.append([float(ts), float(effective)])
        # Trim old samples
        cutoff = ts - _HISTORY_RETENTION_SEC
        # Keep one anchor entry just before the cutoff so we can integrate
        # right at the boundary.
        while len(entries) >= 2 and entries[1][0] < cutoff:
            entries.pop(0)

    def avg_activity_pct(
        self,
        provider: str,
        t_start: float,
        t_end: float,
    ) -> float | None:
        """Time-weighted average of applied activity_level over [t_start, t_end].

        Returns the average expressed as a fraction (e.g., 0.6 means 60%).
        Returns None if history is empty for the provider.  Samples before
        ``t_start`` are clamped to ``t_start``; the most recent sample is held
        constant up to ``t_end``.
        """
        entries = self.history_by_provider.get(provider, [])
        if not entries or t_end <= t_start:
            return None

        # Walk pairs: [(ts_i, level_i), (ts_{i+1}, level_{i+1}), ...]
        # Each interval contributes level_i * dt where
        # dt = clamp(ts_{i+1}, t_start, t_end) - clamp(ts_i, t_start, t_end).
        # Last interval extends from last sample timestamp to t_end.
        sentinel = [t_end, entries[-1][1]]
        walk: list[list[float]] = entries + [sentinel]

        total_dt = 0.0
        weighted_sum = 0.0
        for i in range(len(walk) - 1):
            ts_i, level_i = walk[i]
            ts_next = walk[i + 1][0]
            seg_start = max(ts_i, t_start)
            seg_end = min(ts_next, t_end)
            if seg_end <= seg_start:
                continue
            dt = seg_end - seg_start
            weighted_sum += level_i * dt
            total_dt += dt

        if total_dt <= 0:
            # Fall back to most recent sample
            return float(entries[-1][1]) / 100.0
        return (weighted_sum / total_dt) / 100.0


# ── Policy I/O ───────────────────────────────────────────────────────────────


def _policy_path(data_dir: Path) -> Path:
    return data_dir / "usage_policy.json"


def load_policy(data_dir: Path) -> dict[str, Any]:
    path = _policy_path(data_dir)
    if path.is_file():
        try:
            return json.loads(path.read_text("utf-8-sig"))
        except Exception:
            logger.warning("Failed to load usage policy, using defaults")
    return dict(DEFAULT_POLICY)


def save_policy(data_dir: Path, policy: dict[str, Any]) -> None:
    path = _policy_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(policy, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _migrate_deficit_to_room(window_config: dict[str, Any]) -> bool:
    """Migrate ``deficit_rules``/``deficit_above`` → ``throttle_rules``/``room_under``.

    Returns True if any migration was performed.
    """
    if "deficit_rules" not in window_config:
        return False
    old_rules = window_config.pop("deficit_rules")
    new_rules = []
    for rule in old_rules:
        new_rule = dict(rule)
        if "deficit_above" in new_rule:
            # deficit_above: N → room_under: -N (sign inversion)
            new_rule["room_under"] = -new_rule.pop("deficit_above")
        new_rules.append(new_rule)
    window_config["throttle_rules"] = new_rules
    return True


def _migrate_time_proportional_to_burn_rate(window_config: dict[str, Any]) -> bool:
    """Move legacy default windows to burn-rate landing mode."""
    if window_config.get("mode") != "time_proportional":
        return False
    window_config["mode"] = "burn_rate_landing"
    window_config.setdefault("target_remaining_at_reset", 0)
    window_config.setdefault("min_elapsed_pct", 3)
    window_config.setdefault("min_used_pct", 1)
    window_config.setdefault("min_activity_level", 1)
    window_config.setdefault("max_activity_level", 400)
    window_config.setdefault("fallback_mode", "time_proportional")
    window_config.setdefault("throttle_rules", _default_throttle_rules())
    return True


def ensure_policy_file(data_dir: Path) -> None:
    """Create default policy file if it doesn't exist.

    Also migrates legacy ``deficit_rules``/``deficit_above`` →
    ``throttle_rules``/``room_under`` when found in an existing policy file.
    """
    path = _policy_path(data_dir)
    if not path.is_file():
        save_policy(data_dir, DEFAULT_POLICY)
        logger.info("Created default usage policy at %s", path)
        return

    try:
        policy = json.loads(path.read_text("utf-8-sig"))
        changed = False

        # Migrate deficit_rules/deficit_above → throttle_rules/room_under
        for _prov_key, prov_windows in policy.get("providers", {}).items():
            if not isinstance(prov_windows, dict):
                continue
            for _win_key, win_config in prov_windows.items():
                if not isinstance(win_config, dict):
                    continue
                if _migrate_deficit_to_room(win_config):
                    changed = True
                if _migrate_time_proportional_to_burn_rate(win_config):
                    changed = True

        if changed:
            save_policy(data_dir, policy)
            logger.info("Migrated usage_policy.json: deficit_rules → throttle_rules")
    except Exception:
        logger.debug("Policy migration check failed", exc_info=True)


# ── Credential resolution ───────────────────────────────────────────────────


def _model_to_provider(model_name: str | None) -> str | None:
    """Map a model name to a policy provider key when credential is absent."""
    if not model_name:
        return None
    if model_name.startswith("claude-") or model_name.startswith("anthropic/"):
        return "claude"
    if model_name.startswith("openai/") or model_name.startswith("codex/"):
        return "openai"
    if model_name.startswith("nanogpt/"):
        return "nanogpt"
    if model_name.startswith("opencode-go/"):
        return "opencode_go"
    return None


def _read_anima_status(animas_dir: Path, name: str) -> dict[str, Any]:
    """Read an anima's status.json."""
    status = animas_dir / name / "status.json"
    if not status.is_file():
        return {}
    try:
        data = json.loads(status.read_text("utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_anima_credential(animas_dir: Path, name: str) -> str:
    """Read the ``credential`` field from an anima's status.json."""
    return str(_read_anima_status(animas_dir, name).get("credential", "") or "")


def _providers_for_anima(animas_dir: Path, name: str) -> set[str]:
    """Return provider keys used by either front or background model.

    The process-level suspend switch cannot pause only FR or only BG work, so
    an Anima belongs to both providers when they differ. If either provider
    crosses suspend thresholds, the whole Anima is suspended.
    """
    data = _read_anima_status(animas_dir, name)
    providers: set[str] = set()

    front_provider = _CREDENTIAL_TO_PROVIDER.get(str(data.get("credential", "") or ""))
    if front_provider:
        providers.add(front_provider)

    bg_provider = _CREDENTIAL_TO_PROVIDER.get(str(data.get("background_credential", "") or ""))
    if bg_provider is None:
        bg_provider = _model_to_provider(data.get("background_model"))
    if bg_provider:
        providers.add(bg_provider)

    if not providers:
        providers.add("local")
    return providers


def _classify_animas(
    animas_dir: Path,
    anima_names: list[str],
) -> dict[str, list[str]]:
    """Group anima names by the policy provider keys they use.

    An Anima may appear in two groups when its front and background providers
    differ. This makes suspend thresholds process-wide: if either FR or BG
    provider crosses a suspend threshold, the Anima is stopped.
    """
    groups: dict[str, list[str]] = {}
    for name in anima_names:
        for provider in sorted(_providers_for_anima(animas_dir, name)):
            groups.setdefault(provider, []).append(name)
    return groups


def _anima_names_with_status(animas_dir: Path) -> set[str]:
    """Return Anima names that have an on-disk status.json."""
    if not animas_dir.is_dir():
        return set()
    try:
        return {
            anima_dir.name
            for anima_dir in animas_dir.iterdir()
            if anima_dir.is_dir() and (anima_dir / "status.json").is_file()
        }
    except OSError:
        logger.debug("Failed to scan animas directory: %s", animas_dir, exc_info=True)
        return set()


def _configured_anima_names(data_dir: Path) -> set[str] | None:
    """Return config.json Anima keys, or None when config is unavailable."""
    config_path = data_dir / "config.json"
    if not config_path.is_file():
        return None
    try:
        data = json.loads(config_path.read_text("utf-8-sig"))
    except Exception:
        logger.warning("Governor: failed to read config.json while validating Anima registry", exc_info=True)
        return None
    animas = data.get("animas")
    if not isinstance(animas, dict):
        return None
    return {str(name) for name in animas}


# ── Timestamp helpers ────────────────────────────────────────────────────────


def _parse_resets_at(value: Any) -> float | None:
    """Convert ``resets_at`` (ISO string or unix seconds/ms) → epoch seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # unix seconds (< 1e12) or ms
        return float(value) if value < 1e12 else float(value) / 1000.0
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).timestamp()
        except (ValueError, TypeError):
            return None
    return None


def _time_remaining_pct(resets_at_ts: float, window_seconds: int) -> float:
    """Calculate what % of the window period remains.

    Returns 0–100.  Clamps to [0, 100].
    """
    remaining_secs = resets_at_ts - time.time()
    if remaining_secs <= 0:
        return 0.0
    pct = (remaining_secs / window_seconds) * 100.0
    return min(pct, 100.0)


# ── Rule evaluation ──────────────────────────────────────────────────────────


def _evaluate_threshold(
    remaining: float,
    thresholds: list[dict[str, Any]],
    provider_key: str,
    window_key: str,
) -> tuple[int | None, str]:
    """Evaluate fixed-threshold rules.  Returns (activity_level, reason)."""
    sorted_thresholds = sorted(thresholds, key=lambda t: t["remaining_below"])
    for rule in sorted_thresholds:
        if remaining < rule["remaining_below"]:
            level = _clamp_activity_level(rule["activity_level"])
            reason = (
                f"{provider_key}.{window_key} remaining {remaining:.0f}% "
                f"< {rule['remaining_below']}% → activity {level}%"
            )
            return level, reason
    return None, ""


def _clamp_activity_level(level: Any) -> int:
    """Keep Governor policy output within the supported activity level range."""
    return max(1, min(400, int(level)))


def _evaluate_time_proportional(
    remaining: float,
    window_data: dict[str, Any],
    config: dict[str, Any],
    provider_key: str,
    window_key: str,
) -> tuple[int | None, str]:
    """Evaluate time-proportional rules.  Returns (activity_level, reason).

    Compares ``usage_remaining_%`` vs ``time_remaining_%`` of the window.
    ``room = remaining / time_pct`` (1.0 = on pace; lower = over-consuming).
    ``throttle_rules`` with ``room_under`` thresholds fire when room drops
    below the specified value.  Sorted ascending; first match wins (most
    restrictive applicable rule).

    Legacy ``deficit_rules`` / ``deficit_above`` keys are also accepted for
    backward compatibility.
    """
    resets_at = window_data.get("resets_at")
    window_seconds = window_data.get("window_seconds")

    resets_ts = _parse_resets_at(resets_at)
    if resets_ts is None or not window_seconds:
        # Cannot calculate — fall back to no-op
        return None, ""

    time_pct = _time_remaining_pct(resets_ts, window_seconds)
    if time_pct <= 0:
        room = float("inf") if remaining > 0 else 0.0
    else:
        room = remaining / time_pct

    # Support both new (throttle_rules/room_under) and legacy (deficit_rules/deficit_above)
    rules = config.get("throttle_rules") or config.get("deficit_rules", [])

    def _threshold(r: dict[str, Any]) -> float:
        if "room_under" in r:
            return r["room_under"]
        # Legacy: deficit_above N → equivalent to room_under -N
        return -r.get("deficit_above", 0)

    sorted_rules = sorted(rules, key=_threshold)
    for rule in sorted_rules:
        threshold = _threshold(rule)
        if room < threshold:
            level = _clamp_activity_level(rule["activity_level"])
            reason = (
                f"{provider_key}.{window_key} remaining {remaining:.0f}% "
                f"vs time {time_pct:.0f}% (room {room:.2f} < {threshold}) "
                f"→ activity {level}%"
            )
            return level, reason

    return None, ""


def _update_calibration(
    calib: dict[str, Any] | None,
    observed_burn_per_sec: float,
    avg_activity_pct: float,
    elapsed_sec: float,
    window_seconds: float | None,
    config: dict[str, Any],
    *,
    window_key: str | None = None,
) -> dict[str, Any]:
    """EMA update of base_burn and norm_burn estimates.

    base_burn  — burn rate that does not scale with activity_level
                 (human chats, cron, external receipts).  Updated only when
                 ``avg_activity_pct`` is below ``low_activity_threshold_pct``.
    norm_burn  — burn rate at activity_level=100% for the *scalable* portion.

    Also computes ``match_activity_level``: the constant level that would have
    consumed exactly the full window budget over its full duration
    (= consumption pace matches time progression).
    """
    base_alpha = float(config.get("base_burn_ema_alpha", 0.1))
    norm_alpha = float(config.get("norm_burn_ema_alpha", 0.2))
    low_thresh_pct = float(config.get("low_activity_threshold_pct", 20))
    initial_base_per_day = float(config.get("initial_base_burn_per_day_pct", 0))

    prev = calib or {}
    # Reset calibration when the observation window has changed — the EMA
    # values are in "%/sec of [window]'s quota" units, so values learned on
    # a different window must not be reused.
    prev_window = prev.get("window_key")
    if window_key is not None and prev_window is not None and prev_window != window_key:
        prev = {}
    base_burn_ema = float(prev.get("base_burn_ema", initial_base_per_day / 86400.0))
    norm_burn_ema = float(prev.get("norm_burn_ema", 0.0))
    samples = int(prev.get("samples", 0))

    # Update base_burn only when activity has been very low (signal dominated
    # by non-scalable load).
    if avg_activity_pct * 100.0 <= low_thresh_pct:
        base_burn_ema = base_burn_ema + base_alpha * (observed_burn_per_sec - base_burn_ema)
        if base_burn_ema < 0:
            base_burn_ema = 0.0

    # Update normalized scalable burn (always, when activity is meaningful).
    scalable = max(0.0, observed_burn_per_sec - base_burn_ema)
    if avg_activity_pct >= 0.05:  # at least 5% applied activity to be useful
        norm_at_100 = scalable / avg_activity_pct
        if norm_burn_ema <= 0:
            norm_burn_ema = norm_at_100
        else:
            norm_burn_ema = norm_burn_ema + norm_alpha * (norm_at_100 - norm_burn_ema)

    # Prediction error (predicted vs. observed burn at the avg_applied level)
    predicted = base_burn_ema + norm_burn_ema * avg_activity_pct
    error = observed_burn_per_sec - predicted

    # match_activity_level: level X such that predicted burn over the window
    # would exactly deplete 100% by reset.  i.e., target_burn = 100% / window_sec.
    match_level: float | None = None
    if window_seconds and norm_burn_ema > 0:
        target_burn = 100.0 / float(window_seconds)
        budget_for_scalable = target_burn - base_burn_ema
        if budget_for_scalable > 0:
            match_level = (budget_for_scalable / norm_burn_ema) * 100.0
        else:
            match_level = 0.0  # base burn alone already exceeds time-pace

    return {
        "base_burn_ema": base_burn_ema,
        "norm_burn_ema": norm_burn_ema,
        "samples": samples + 1,
        "last_avg_applied_pct": avg_activity_pct * 100.0,
        "last_observed_burn_per_sec": observed_burn_per_sec,
        "last_predicted_burn_per_sec": predicted,
        "last_prediction_error_per_sec": error,
        "last_elapsed_sec": elapsed_sec,
        "last_window_seconds": float(window_seconds) if window_seconds else None,
        "window_key": window_key,
        "match_activity_level": match_level,
        "last_updated_ts": time.time(),
    }


def _evaluate_burn_rate_landing(
    remaining: float,
    window_data: dict[str, Any],
    config: dict[str, Any],
    provider_key: str,
    window_key: str,
    *,
    calibration: dict[str, Any] | None = None,
    avg_activity_pct: float | None = None,
    calibration_enabled: bool = False,
) -> tuple[int | None, str]:
    """Throttle so the current burn rate lands near the target reset balance.

    When ``calibration_enabled`` and ``calibration`` provides usable
    ``norm_burn_ema``/``base_burn_ema`` values, the target activity_level is
    derived from the linear model:

        predicted_burn(level) = base_burn + norm_burn * level/100

    Otherwise the legacy formula (``raw_level = target / observed * 100``)
    is used, which implicitly assumes the observation was made at level=100%.
    """
    resets_at = window_data.get("resets_at")
    window_seconds = window_data.get("window_seconds")

    resets_ts = _parse_resets_at(resets_at)
    if resets_ts is None or not window_seconds:
        return None, ""

    now = time.time()
    reset_in = resets_ts - now
    if reset_in <= 0:
        return None, ""

    elapsed = max(0.0, float(window_seconds) - reset_in)
    elapsed_pct = (elapsed / float(window_seconds)) * 100.0 if window_seconds else 0.0
    used = max(0.0, 100.0 - remaining)

    min_elapsed_pct = float(config.get("min_elapsed_pct", 3))
    min_used_pct = float(config.get("min_used_pct", 1))
    if elapsed_pct < min_elapsed_pct or used < min_used_pct:
        fallback = config.get("fallback_mode", "time_proportional")
        if fallback == "time_proportional":
            return _evaluate_time_proportional(remaining, window_data, config, provider_key, window_key)
        return None, ""

    target_remaining = float(config.get("target_remaining_at_reset", 0))
    burn_per_sec = used / elapsed if elapsed > 0 else 0.0
    if burn_per_sec <= 0:
        return None, ""

    target_budget = max(0.0, remaining - target_remaining)
    target_burn_per_sec = target_budget / reset_in

    min_level = _clamp_activity_level(config.get("min_activity_level", 1))
    max_level = _clamp_activity_level(config.get("max_activity_level", 400))
    if min_level > max_level:
        min_level, max_level = max_level, min_level

    # Prefer calibrated computation when enabled and we have usable EMAs.
    used_calibration = False
    if (
        calibration_enabled
        and calibration is not None
        and avg_activity_pct is not None
        and avg_activity_pct >= 0.05
    ):
        norm_burn = float(calibration.get("norm_burn_ema", 0) or 0)
        base_burn = float(calibration.get("base_burn_ema", 0) or 0)
        if norm_burn > 0:
            scalable_target = target_burn_per_sec - base_burn
            if scalable_target <= 0:
                # Even at level=0, base burn alone exceeds the target.
                # Fall to minimum and let suspension thresholds handle it.
                raw_level = float(min_level)
            else:
                raw_level = (scalable_target / norm_burn) * 100.0
            level = max(min_level, min(max_level, int(round(raw_level))))
            projected_remaining = remaining - (
                (base_burn + norm_burn * (level / 100.0)) * reset_in
            )
            reason = (
                f"{provider_key}.{window_key} landing {projected_remaining:.0f}% "
                f"target {target_remaining:.0f}% "
                f"(obs {burn_per_sec * 86400:.1f}%/d @ avg {avg_activity_pct * 100:.0f}%, "
                f"base {base_burn * 86400:.1f}%/d, norm@100 {norm_burn * 86400:.1f}%/d, "
                f"target {target_burn_per_sec * 86400:.1f}%/d) "
                f"-> activity {level}%"
            )
            used_calibration = True
            return level, reason

    # Legacy uncalibrated path (assumes observation was at activity_level=100%).
    raw_level = (target_burn_per_sec / burn_per_sec) * 100.0
    level = max(min_level, min(max_level, int(round(raw_level))))

    projected_remaining = remaining - (burn_per_sec * reset_in)
    suffix = " [uncalibrated]" if not used_calibration else ""
    reason = (
        f"{provider_key}.{window_key} landing {projected_remaining:.0f}% "
        f"target {target_remaining:.0f}% (burn {burn_per_sec * 86400:.1f}%/d, "
        f"target {target_burn_per_sec * 86400:.1f}%/d) "
        f"-> activity {level}%{suffix}"
    )
    return level, reason


def _evaluate_hard_floor(
    remaining: float,
    hard_floor: float,
    hard_floor_activity_level: Any,
    provider_key: str,
    window_key: str,
) -> tuple[int | None, str]:
    """Absolute safety net: if remaining drops below hard floor, emergency throttle."""
    if remaining < hard_floor:
        level = _clamp_activity_level(hard_floor_activity_level)
        reason = (
            f"{provider_key}.{window_key} remaining {remaining:.0f}% < hard floor {hard_floor:.0f}% → activity {level}%"
        )
        return level, reason
    return None, ""


def _evaluate_provider_remaining(
    usage_data: dict[str, Any],
    policy: dict[str, Any],
    provider_key: str,
    *,
    calibration: dict[str, Any] | None = None,
    avg_activity_pct: float | None = None,
    calibration_enabled: bool = False,
    calibration_window_key: str | None = None,
) -> tuple[float, int | None, str]:
    """Evaluate rules for a single provider.

    Handles both threshold (list) and time_proportional (dict) window configs.

    Returns (worst_remaining_pct, target_activity_level_or_None, reason).
    """
    providers_rules = policy.get("providers", {})
    windows_rules = providers_rules.get(provider_key, {})
    provider_data = usage_data.get(provider_key, {})
    hard_floor = policy.get("hard_floor_pct", 15)
    hard_floor_activity_level = policy.get("hard_floor_activity_level", 10)

    if provider_data.get("error"):
        return 100.0, None, ""

    worst_remaining: float = 100.0
    worst_level: int | None = None
    worst_reason = ""

    def _update_worst(level: int | None, reason: str) -> None:
        nonlocal worst_level, worst_reason
        if level is not None and (worst_level is None or level < worst_level):
            worst_level = level
            worst_reason = reason

    for window_key, window_config in windows_rules.items():
        window = provider_data.get(window_key)
        if not window or not isinstance(window, dict):
            continue

        remaining = window.get("remaining")
        if remaining is None:
            continue

        worst_remaining = min(worst_remaining, remaining)

        # Determine mode
        if isinstance(window_config, list):
            # Threshold mode (backward-compatible list format)
            level, reason = _evaluate_threshold(
                remaining,
                window_config,
                provider_key,
                window_key,
            )
            _update_worst(level, reason)
        elif isinstance(window_config, dict):
            mode = window_config.get("mode", "threshold")
            if mode == "time_proportional":
                level, reason = _evaluate_time_proportional(
                    remaining,
                    window,
                    window_config,
                    provider_key,
                    window_key,
                )
                _update_worst(level, reason)
            elif mode == "burn_rate_landing":
                # burn_rate_landing only fires on the calibration window
                # (longest available).  Other windows would mix
                # quota-percentage units with the per-provider calibration
                # EMAs and produce nonsensical target_levels.  Hard-floor
                # evaluation below still protects shorter windows.
                if (
                    calibration_window_key is not None
                    and window_key != calibration_window_key
                ):
                    pass
                else:
                    level, reason = _evaluate_burn_rate_landing(
                        remaining,
                        window,
                        window_config,
                        provider_key,
                        window_key,
                        calibration=calibration,
                        avg_activity_pct=avg_activity_pct,
                        calibration_enabled=calibration_enabled,
                    )
                    _update_worst(level, reason)
            else:
                # Dict with "rules" key treated as threshold
                rules = window_config.get("rules", [])
                level, reason = _evaluate_threshold(
                    remaining,
                    rules,
                    provider_key,
                    window_key,
                )
                _update_worst(level, reason)

        # Hard floor — always checked regardless of mode
        level, reason = _evaluate_hard_floor(
            remaining,
            hard_floor,
            hard_floor_activity_level,
            provider_key,
            window_key,
        )
        _update_worst(level, reason)

    return worst_remaining, worst_level, worst_reason


def _animas_to_suspend(
    worst_remaining: float,
    policy: dict[str, Any],
    provider_animas: list[str],
) -> list[str]:
    """Determine which animas of a given provider should be suspended."""
    thresholds = policy.get("suspend_thresholds", {})
    essential = set(policy.get("essential_animas", []))
    coo = policy.get("coo_anima", "sakura")

    all_except_coo_below = thresholds.get("all_except_coo_below", 15)
    non_essential_below = thresholds.get("non_essential_below", 30)

    to_suspend: list[str] = []
    if worst_remaining < all_except_coo_below:
        for name in provider_animas:
            if name != coo:
                to_suspend.append(name)
    elif worst_remaining < non_essential_below:
        for name in provider_animas:
            if name not in essential:
                to_suspend.append(name)

    return to_suspend


def _provider_usage_fetch_failed(usage_data: dict[str, Any], provider_key: str) -> bool:
    """Return True when provider usage could not be fetched this cycle."""
    provider_data = usage_data.get(provider_key, {})
    return bool(provider_data.get("error"))


# ── Governor loop ────────────────────────────────────────────────────────────


class UsageGovernor:
    """Background task that monitors usage and suspends cloud-provider animas."""

    def __init__(self, app: Any, data_dir: Path, animas_dir: Path) -> None:
        self._app = app
        self._data_dir = data_dir
        self._animas_dir = animas_dir
        self._state = GovernorState(data_dir / "usage_governor_state.json")
        self._history = GovernorHistory(data_dir / "usage_governor_history.json")
        self._task: asyncio.Task | None = None

    @property
    def history(self) -> GovernorHistory:
        return self._history

    @property
    def state(self) -> GovernorState:
        return self._state

    async def start(self) -> None:
        ensure_policy_file(self._data_dir)
        if self._state.suspended_animas:
            logger.info(
                "Governor restoring state: %d animas suspended",
                len(self._state.suspended_animas),
            )
        self._task = asyncio.create_task(self._loop())
        logger.info("Usage Governor started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Usage Governor stopped")

    async def _loop(self) -> None:
        await asyncio.sleep(10)

        while True:
            try:
                policy = load_policy(self._data_dir)
                if not policy.get("enabled", True):
                    await asyncio.sleep(60)
                    continue

                interval = policy.get("check_interval_seconds", 120)
                await self._tick(policy)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Usage Governor tick failed")
                await asyncio.sleep(60)

    async def _tick(self, policy: dict[str, Any]) -> None:
        """Single governor check cycle."""
        from server.routes.usage_routes import (
            _fetch_claude_usage,
            _fetch_nanogpt_usage,
            _fetch_openai_usage,
            _fetch_opencode_go_usage,
            _relogin_claude,
        )

        usage_data = {
            "claude": _fetch_claude_usage(),
            "openai": _fetch_openai_usage(),
            "nanogpt": _fetch_nanogpt_usage(),
            "opencode_go": _fetch_opencode_go_usage(),
        }

        # Auto-recovery: if Claude fetch failed with recoverable error,
        # try token refresh / relogin then retry (rate-limited to avoid
        # excessive OAuth requests).
        claude_error = usage_data.get("claude", {}).get("error", "")
        if claude_error in ("rate_limited", "unauthorized", "no_credentials"):
            if self._state.can_relogin("claude"):
                logger.info("Governor: Claude usage fetch failed (%s), attempting relogin", claude_error)
                relogin_result, _status = _relogin_claude()
                success = bool(relogin_result.get("success"))
                self._state.record_relogin("claude", success=success)
                if success:
                    logger.info("Governor: relogin succeeded, retrying usage fetch")
                    usage_data["claude"] = _fetch_claude_usage(skip_cache=True)
                else:
                    logger.warning(
                        "Governor: relogin failed — %s",
                        relogin_result.get("message", "unknown"),
                    )
            else:
                logger.info("Governor: skipping relogin for claude (rate-limited / cooldown)")

        self._state.last_check = time.time()
        self._state.last_usage = usage_data

        # Classify running animas by provider credential
        all_names = self._get_all_anima_names()
        groups = _classify_animas(self._animas_dir, all_names)
        currently_suspended = set(self._state.suspended_animas)

        all_suspend: list[str] = []
        reasons: list[str] = []
        level_by_provider: dict[str, int | None] = {}
        calib_config = policy.get("calibration", {}) or {}
        calibration_enabled = bool(calib_config.get("enabled", True))
        # Evaluate all cloud providers, including providers with no currently
        # running animas so their activity level remains visible to readers.
        for provider_key in ("claude", "openai", "nanogpt", "opencode_go"):
            provider_animas = groups.get(provider_key, [])

            if _provider_usage_fetch_failed(usage_data, provider_key):
                if provider_animas:
                    retained = sorted(currently_suspended.intersection(provider_animas))
                    all_suspend.extend(retained)
                    error_code = usage_data.get(provider_key, {}).get("error", "unknown")
                    if retained:
                        reasons.append(
                            f"{provider_key} usage unavailable ({error_code}) → keeping {', '.join(retained)} suspended",
                        )
                    else:
                        reasons.append(f"{provider_key} usage unavailable ({error_code})")
                continue

            # ── Compute observation window for calibration ──────────────────
            # Use the longest window so the signal is stable; per-second
            # quantization on a 5h window can swing wildly per tick.
            (
                avg_activity_pct,
                observed_burn,
                observed_elapsed,
                observation_window,
                calibration_window_key,
            ) = self._observation_for_provider(usage_data, policy, provider_key)
            calibration = self._state.calibration_by_provider.get(provider_key)

            # Update calibration EMAs from this tick's observation
            if (
                avg_activity_pct is not None
                and observed_burn is not None
                and observed_elapsed is not None
                and observed_elapsed >= float(calib_config.get("min_observation_sec", 600))
            ):
                window_seconds = (
                    observation_window.get("window_seconds") if observation_window else None
                )
                calibration = _update_calibration(
                    calibration,
                    observed_burn,
                    avg_activity_pct,
                    observed_elapsed,
                    window_seconds,
                    calib_config,
                    window_key=calibration_window_key,
                )
                self._state.calibration_by_provider[provider_key] = calibration
                self._append_calibration_log(
                    provider_key, calibration, calib_config
                )

            remaining, level, reason = _evaluate_provider_remaining(
                usage_data,
                policy,
                provider_key,
                calibration=calibration,
                avg_activity_pct=avg_activity_pct,
                calibration_enabled=calibration_enabled,
                calibration_window_key=calibration_window_key,
            )

            # Record this provider's activity level (throttles only animas
            # whose main credential matches this provider)
            level_by_provider[provider_key] = level

            if provider_animas:
                to_suspend = _animas_to_suspend(remaining, policy, provider_animas)
                all_suspend.extend(to_suspend)
            if reason:
                reasons.append(reason)

        # Bail out before mutating process state if the governor is shutting down.
        task = asyncio.current_task()
        if task is not None and task.cancelled():
            return

        # Set the reason before notifications so escalation text carries the
        # current quota explanation, not the previous tick's value.
        self._state.reason = " | ".join(reasons) if reasons else ""

        # Apply suspensions (only cloud-provider animas; local ones untouched)
        await self._apply_suspensions(set(all_suspend))

        # Apply per-provider activity levels.  The numeric pressure signal is
        # provider-based; readers decide whether to apply it as front-response
        # depth or background/self-initiated cadence/depth.
        prev_by_provider = self._state.governor_activity_level_by_provider
        prev_front_by_provider = self._state.front_activity_level_by_provider
        prev_background_by_provider = self._state.background_activity_level_by_provider
        state_changed = False
        if (
            prev_by_provider != level_by_provider
            or prev_front_by_provider != level_by_provider
            or prev_background_by_provider != level_by_provider
        ):
            self._state.governor_activity_level_by_provider = level_by_provider
            self._state.front_activity_level_by_provider = dict(level_by_provider)
            self._state.background_activity_level_by_provider = dict(level_by_provider)
            logger.info(
                "Governor: activity_level_by_provider front=%s background=%s → %s",
                prev_front_by_provider or prev_by_provider,
                prev_background_by_provider or prev_by_provider,
                level_by_provider,
            )
            state_changed = True

        if state_changed:
            await self._broadcast_reschedule()

        throttling = any(lvl is not None and lvl < 100 for lvl in level_by_provider.values())
        active = throttling
        if all_suspend and not self._state.since:
            self._state.since = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        elif not all_suspend and not active:
            self._state.since = ""

        # Append per-provider applied activity_level to rolling history.
        now_ts = time.time()
        for provider_key, level in level_by_provider.items():
            self._history.append(provider_key, now_ts, level)
        self._history.save()

        self._state.save()

    async def _broadcast_reschedule(self) -> None:
        """Broadcast reschedule_heartbeat IPC to all running animas."""
        supervisor = getattr(self._app.state, "supervisor", None)
        if not supervisor or not hasattr(supervisor, "send_request"):
            return
        known_names = self._known_anima_names()
        for name in list(getattr(supervisor, "processes", {}).keys()):
            if name not in known_names:
                logger.warning("Governor: skipping reschedule for unknown Anima %s", name)
                continue
            try:
                await supervisor.send_request(name, "reschedule_heartbeat", {})
            except Exception:
                logger.debug("Governor: failed to reschedule %s", name, exc_info=True)

    def _known_anima_names(self) -> set[str]:
        """Return names that belong to the current Anima registry."""
        disk_names = _anima_names_with_status(self._animas_dir)
        configured_names = _configured_anima_names(self._data_dir)
        if configured_names:
            return disk_names.intersection(configured_names)
        return disk_names

    def _get_all_anima_names(self) -> list[str]:
        """Get all registered anima names (running + governor-suspended)."""
        supervisor = getattr(self._app.state, "supervisor", None)
        names = set()
        if supervisor and hasattr(supervisor, "processes"):
            names.update(supervisor.processes.keys())
        # Include animas we suspended (they won't be in processes)
        names.update(self._state.suspended_animas)
        known_names = self._known_anima_names()
        unknown = names - known_names
        if unknown:
            logger.warning(
                "Governor: ignoring unknown Anima name(s) from process/state registry: %s",
                ", ".join(sorted(unknown)),
            )
        return sorted(names.intersection(known_names))

    def _observation_for_provider(
        self,
        usage_data: dict[str, Any],
        policy: dict[str, Any],
        provider_key: str,
    ) -> tuple[
        float | None,
        float | None,
        float | None,
        dict[str, Any] | None,
        str | None,
    ]:
        """Pick the longest usable window and compute observation tuple.

        The longest window is chosen so calibration / throttle decisions are
        based on a stable signal — short windows oscillate too aggressively
        and quantize poorly (a single tool call can swing %/s wildly when
        elapsed is small).  Hard-floor evaluation on shorter windows still
        protects against acute exhaustion.

        Returns ``(avg_activity_pct, observed_burn_per_sec, observed_elapsed_sec,
        window_data, window_key)`` or all ``None`` when no usable signal exists.
        """
        provider_data = usage_data.get(provider_key, {})
        if not isinstance(provider_data, dict) or provider_data.get("error"):
            return None, None, None, None, None

        windows_rules = policy.get("providers", {}).get(provider_key, {})

        # (window_sec, window_data, window_key) — pick the longest window.
        best: tuple[float, dict[str, Any], str] | None = None
        for window_key in windows_rules:
            win = provider_data.get(window_key)
            if not isinstance(win, dict):
                continue
            ws = win.get("window_seconds")
            if not ws:
                continue
            if best is None or float(ws) > best[0]:
                best = (float(ws), win, window_key)

        if best is None:
            return None, None, None, None, None

        window_seconds, window, window_key = best
        resets_ts = _parse_resets_at(window.get("resets_at"))
        remaining = window.get("remaining")
        if resets_ts is None or remaining is None:
            return None, None, None, window, window_key

        now = time.time()
        reset_in = resets_ts - now
        elapsed = max(0.0, window_seconds - reset_in)
        used = max(0.0, 100.0 - float(remaining))
        observed_burn = (used / elapsed) if elapsed > 0 else 0.0

        avg_activity = self._history.avg_activity_pct(
            provider_key, now - elapsed, now
        )
        return avg_activity, observed_burn, elapsed, window, window_key

    def _append_calibration_log(
        self,
        provider_key: str,
        calibration: dict[str, Any],
        calib_config: dict[str, Any],
    ) -> None:
        """Append a calibration snapshot to the JSONL log, with size rotation."""
        log_path = self._state.calibration_log_path
        max_entries = int(calib_config.get("calibration_log_max_entries", 5000))
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": time.time(),
                "provider": provider_key,
                "base_burn_per_day_pct": calibration.get("base_burn_ema", 0) * 86400.0,
                "norm_burn_at_100_per_day_pct": calibration.get("norm_burn_ema", 0) * 86400.0,
                "samples": calibration.get("samples", 0),
                "last_avg_applied_pct": calibration.get("last_avg_applied_pct"),
                "last_observed_burn_per_day_pct": (
                    calibration.get("last_observed_burn_per_sec", 0) * 86400.0
                ),
                "last_predicted_burn_per_day_pct": (
                    calibration.get("last_predicted_burn_per_sec", 0) * 86400.0
                ),
                "last_prediction_error_per_day_pct": (
                    calibration.get("last_prediction_error_per_sec", 0) * 86400.0
                ),
                "match_activity_level": calibration.get("match_activity_level"),
            }
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            # Lightweight rotation: when file grows past 2x max_entries, keep
            # the most recent max_entries lines.
            if max_entries > 0:
                try:
                    line_count = sum(1 for _ in log_path.open("r", encoding="utf-8"))
                except Exception:
                    line_count = 0
                if line_count > max_entries * 2:
                    with log_path.open("r", encoding="utf-8") as f:
                        lines = f.readlines()
                    keep = lines[-max_entries:]
                    log_path.write_text("".join(keep), encoding="utf-8")
        except Exception:
            logger.debug("Failed to append calibration log", exc_info=True)

    async def _apply_suspensions(self, target_suspended: set[str]) -> None:
        supervisor = getattr(self._app.state, "supervisor", None)
        if not supervisor:
            return

        known_names = self._known_anima_names()
        unknown_targets = target_suspended - known_names
        if unknown_targets:
            logger.warning(
                "Governor: refusing to suspend unknown Anima name(s): %s",
                ", ".join(sorted(unknown_targets)),
            )
            target_suspended = target_suspended.intersection(known_names)

        currently_suspended = set(self._state.suspended_animas)
        unknown_current = currently_suspended - known_names
        if unknown_current:
            logger.warning(
                "Governor: pruning unknown Anima name(s) from suspended state: %s",
                ", ".join(sorted(unknown_current)),
            )
            currently_suspended = currently_suspended.intersection(known_names)

        # Resume animas that are no longer in the suspend list
        to_resume = currently_suspended - target_suspended
        for name in to_resume:
            try:
                if name not in supervisor.processes:
                    await supervisor.start_anima(name)
                    logger.info("Governor: resumed anima %s", name)
            except Exception:
                logger.warning("Governor: failed to resume %s", name, exc_info=True)

        # Suspend animas that should be stopped.
        newly_suspended = target_suspended - currently_suspended
        for name in target_suspended:
            try:
                if name in supervisor.processes:
                    await supervisor.stop_anima(name)
                    logger.info("Governor: suspended anima %s", name)
                    if name in newly_suspended:
                        await self._notify_supervisor(name, self._state.reason)
            except Exception:
                logger.warning("Governor: failed to suspend %s", name, exc_info=True)

        self._state.suspended_animas = sorted(target_suspended)

    async def _notify_supervisor(self, anima_name: str, reason: str) -> None:
        """Notify the suspended anima's supervisor (or human if top-level)."""
        try:
            import json as _json

            if anima_name not in self._known_anima_names():
                logger.warning("Governor: suppressing notification for unknown Anima %s", anima_name)
                return

            status_path = self._animas_dir / anima_name / "status.json"
            if not status_path.is_file():
                return
            status = _json.loads(status_path.read_text("utf-8"))
            supervisor_name = status.get("supervisor")

            if supervisor_name:
                sup_status_path = self._animas_dir / supervisor_name / "status.json"
                sup_enabled = False
                if sup_status_path.is_file():
                    sup_data = _json.loads(sup_status_path.read_text("utf-8"))
                    sup_enabled = sup_data.get("enabled", False)

                if sup_enabled:
                    from core.messenger import Messenger
                    from core.paths import get_shared_dir

                    messenger = Messenger(get_shared_dir(), "system")
                    messenger.send(
                        to=supervisor_name,
                        content=t(
                            "governor.supervisor_notify",
                            anima=anima_name,
                            reason=reason,
                        ),
                        intent="report",
                    )
                    logger.info("Governor: notified supervisor %s about %s suspension", supervisor_name, anima_name)
                    return

            from core.config.models import load_config as _lc_hn
            from core.notification.notifier import HumanNotifier

            cfg = _lc_hn()
            notifier = HumanNotifier.from_config(cfg.human_notification)
            if notifier.channel_count > 0:
                msg = t("governor.human_notify", anima=anima_name, reason=reason)
                await notifier.notify(
                    subject=t("governor.human_notify_subject"),
                    body=msg,
                    anima_name=anima_name,
                )
            logger.info("Governor: notified human about %s suspension (no active supervisor)", anima_name)
        except Exception:
            logger.warning("Failed to notify supervisor for %s", anima_name, exc_info=True)
