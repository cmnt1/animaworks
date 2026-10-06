# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""APScheduler management for heartbeat and cron tasks.

Handles registration, execution, overlap prevention, and hot-reload
of heartbeat and cron schedules for a single Anima process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import zlib
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config.model_mode import is_claude_cli_alias
from core.config.models import load_config
from core.i18n import t
from core.platform.atomic_io import atomic_write_json
from core.platform.tasks import spawn
from core.runtime.cron_followup import command_followup_output
from core.runtime.memory_service import MemoryService
from core.runtime.schedule_parser import parse_cron_md, parse_heartbeat_config, parse_schedule
from core.runtime.task_runner_supervisor import TaskRunnerSupervisor
from core.schemas import CronTask
from core.time_utils import get_app_timezone, now_local

_INDENTED_SCHEDULE_RE = re.compile(r"^\s+schedule:", re.MULTILINE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCED_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)


def _strip_cron_documentation(content: str) -> str:
    """Remove non-configuration documentation before cron parse diagnostics.

    ``parse_cron_md`` strips HTML comments before parsing, so the diagnostic
    must inspect the same effective document. Fenced examples are also prose
    and must not be treated as indented configuration directives.
    """
    content = _HTML_COMMENT_RE.sub("", content)
    return _FENCED_CODE_BLOCK_RE.sub("", content)


# Map an Anima's main-credential field value to the Governor provider key.
# Kept local to avoid a core → server import.
_CREDENTIAL_TO_GOVERNOR_PROVIDER: dict[str, str] = {
    "anthropic": "claude",
    "openai": "openai",
    "nanogpt": "nanogpt",
    "opencode-go": "opencode_go",
}


def _cron_failure_output(result: dict[str, Any]) -> str:
    """Format a failed command cron result for the follow-up LLM."""
    exit_code = result.get("exit_code", "")
    stdout = str(result.get("stdout") or "").strip()
    stderr = str(result.get("stderr") or "").strip()
    if not stdout and not stderr:
        return ""
    parts = [
        "COMMAND_CRON_FAILED",
        f"task: {result.get('task', '')}",
        f"exit_code: {exit_code}",
    ]
    duration_ms = result.get("duration_ms")
    if duration_ms is not None:
        parts.append(f"duration_ms: {duration_ms}")
    if stdout:
        parts.extend(["stdout:", stdout])
    if stderr:
        parts.extend(["stderr:", stderr])
    return "\n".join(parts)


def _read_anima_credential(anima_dir: Path) -> str:
    """Read the ``credential`` field from an Anima's status.json."""
    return _read_anima_status_field(anima_dir, "credential")


def _read_anima_status_field(anima_dir: Path, key: str) -> str:
    """Read a string field from an Anima's status.json."""
    status = anima_dir / "status.json"
    if not status.is_file():
        return ""
    try:
        data = json.loads(status.read_text("utf-8"))
        value = data.get(key, "") or ""
        return value if isinstance(value, str) else ""
    except Exception:
        return ""


def _read_governor_state() -> dict[str, Any]:
    from core.paths import get_data_dir

    state_path = get_data_dir() / "usage_governor_state.json"
    if not state_path.is_file():
        return {}
    try:
        return json.loads(state_path.read_text("utf-8"))
    except Exception:
        return {}


def _read_activity_map(data: dict[str, Any], key: str) -> dict[str, int | None]:
    by_provider = data.get(key)
    if isinstance(by_provider, dict) and by_provider:
        return {k: v for k, v in by_provider.items() if v is None or isinstance(v, int)}

    # Backward compat: the original single map was front-oriented, but it is
    # still the best available provider pressure signal for both roles.
    by_provider = data.get("governor_activity_level_by_provider")
    if isinstance(by_provider, dict) and by_provider:
        return {k: v for k, v in by_provider.items() if v is None or isinstance(v, int)}

    legacy = data.get("governor_activity_level")
    if isinstance(legacy, int):
        return {
            "claude": legacy,
            "openai": legacy,
            "nanogpt": legacy,
            "opencode_go": legacy,
        }
    return {}


def _level_for_provider(activity_map: dict[str, int | None], provider: str | None) -> int | None:
    if provider is None:
        return None
    level = activity_map.get(provider)
    return level if isinstance(level, int) else None


def _provider_from_credential(credential: str) -> str | None:
    return _CREDENTIAL_TO_GOVERNOR_PROVIDER.get(credential)


def _read_governor_front_activity_level(anima_dir: Path | None = None) -> int | None:
    """Read Governor activity for response/front-model work.

    Front activity follows the Anima's main ``credential`` because it controls
    chat/inbox/external-response depth.
    """
    data = _read_governor_state()
    if not data or anima_dir is None:
        return None

    provider = _provider_from_credential(_read_anima_credential(anima_dir))
    return _level_for_provider(_read_activity_map(data, "front_activity_level_by_provider"), provider)


def _read_governor_activity_level(anima_dir: Path | None = None) -> int | None:
    """Backward-compatible alias for front activity."""
    return _read_governor_front_activity_level(anima_dir)


def _read_governor_background_activity_level(anima_dir: Path | None = None) -> int | None:
    """Read Governor activity for background/self-initiated work.

    Background activity follows ``background_credential``/``background_model``.
    If no background model is configured, it falls back to the front provider.
    """
    data = _read_governor_state()
    if not data or anima_dir is None:
        return None

    bg_credential = _read_anima_status_field(anima_dir, "background_credential")
    provider = _provider_from_credential(bg_credential)
    if provider is None:
        provider = _model_to_governor_provider(_read_anima_status_field(anima_dir, "background_model"))
    if provider is None:
        provider = _provider_from_credential(_read_anima_credential(anima_dir))
    return _level_for_provider(_read_activity_map(data, "background_activity_level_by_provider"), provider)


def _model_to_governor_provider(model_name: str | None) -> str | None:
    """Map a model name to the Governor provider key used by usage policy.

    Returns ``None`` for models not tracked by the Governor (ollama, bedrock,
    cursor, gemini, etc.).
    """
    if not model_name:
        return None
    # Anthropic: bare ``claude-*`` or ``anthropic/claude-*``
    if model_name.startswith(("claude-", "anthropic/")) or is_claude_cli_alias(model_name):
        return "claude"
    # OpenAI: ``openai/*`` and ``codex/*`` (Codex uses OpenAI credentials)
    if model_name.startswith("openai/") or model_name.startswith("codex/"):
        return "openai"
    if model_name.startswith("nanogpt/"):
        return "nanogpt"
    if model_name.startswith("opencode-go/"):
        return "opencode_go"
    return None


def resolve_user_activity_level(config, anima_dir: Path) -> int:
    """Resolve the user-configured activity level for an Anima.

    Looks up ``config.activity_level_by_provider[provider]`` using the
    Anima's main-credential provider (mapped via
    ``_CREDENTIAL_TO_GOVERNOR_PROVIDER``).  Falls back to the
    ``default`` entry, then to ``config.activity_level``.
    """
    by_provider = getattr(config, "activity_level_by_provider", None) or {}
    if not by_provider:
        return config.activity_level
    credential = _read_anima_credential(anima_dir)
    provider = _CREDENTIAL_TO_GOVERNOR_PROVIDER.get(credential, "default")
    if provider in by_provider:
        return by_provider[provider]
    if "default" in by_provider:
        return by_provider["default"]
    return config.activity_level


_SECONDS_PER_HOUR = 3600
_DAILY_STALE_THRESHOLD_SEC = 36 * _SECONDS_PER_HOUR
_WEEKLY_STALE_THRESHOLD_SEC = 8 * 24 * _SECONDS_PER_HOUR

if TYPE_CHECKING:
    from core.anima.digital_anima import DigitalAnima

logger = logging.getLogger(__name__)


def _active_hour_spec(active_start: int | None, active_end: int | None) -> str:
    """Return a CronTrigger hour spec for heartbeat active hours."""
    if active_start is None or active_end is None or active_start == active_end:
        return "*"
    if active_start < active_end:
        return f"{active_start}-{active_end - 1}"
    if active_end == 0:
        return f"{active_start}-23"
    return f"{active_start}-23,0-{active_end - 1}"


def read_per_anima_heartbeat_interval(anima_dir: Path, app_config: Any) -> int:
    """Read heartbeat_interval_minutes from status.json, fallback to global config.

    Only int/float values in [1, 1440] are accepted; anything else (missing,
    malformed, or out of range) falls back to ``app_config.heartbeat.interval_minutes``.
    """
    try:
        status_path = anima_dir / "status.json"
        if status_path.is_file():
            data = json.loads(status_path.read_text(encoding="utf-8"))
            val = data.get("heartbeat_interval_minutes")
            if isinstance(val, (int, float)) and 1 <= val <= 1440:
                return int(val)
    except (json.JSONDecodeError, OSError, ValueError):
        logger.debug("Failed to read heartbeat_interval_minutes from %s", anima_dir)
    return app_config.heartbeat.interval_minutes


class SchedulerManager:
    """APScheduler management: heartbeat/cron registration, execution, reload."""

    def __init__(
        self,
        anima: DigitalAnima,
        anima_name: str,
        anima_dir: Path,
        emit_event: Callable[[str, dict[str, Any]], None],
    ) -> None:
        self._anima = anima
        self._anima_name = anima_name
        self._anima_dir = anima_dir
        self._emit_event = emit_event

        self.scheduler: AsyncIOScheduler | None = None
        self._heartbeat_running: bool = False
        self._cron_running: set[str] = set()
        self._direct_cron_tasks: set[asyncio.Task[Any]] = set()
        self._cron_md_mtime: float = 0.0
        self._heartbeat_md_mtime: float = 0.0
        self._last_schedule_level: int | None = None
        self._task_runner_supervisor: TaskRunnerSupervisor
        pool_size: int | None = None
        try:
            pool_size = int(getattr(anima, "_background_worker_pool_size", 1) or 1)
        except (TypeError, ValueError):
            pool_size = 1
        self._task_runner_supervisor = TaskRunnerSupervisor(
            anima_name=anima_name,
            anima_dir=anima_dir,
            shared_dir=Path(anima.shared_dir),
            max_concurrent=pool_size,
            runner_liveness_timeout_sec=float(load_config().server.runner_liveness_timeout),
            busy_status_owner=anima,
            memory_service=MemoryService(anima_name, anima_dir),
        )

        # Polling-based heartbeat state (used when effective_interval > 60)
        self._hb_effective_interval: int = 0
        self._hb_active_start: int | None = None
        self._hb_active_end: int | None = None
        self._hb_first_check_offset: int = 0
        self._hb_first_check_done: bool = False

    # ── Public Properties ────────────────────────────────────────

    @property
    def heartbeat_running(self) -> bool:
        """Whether a heartbeat is currently executing (read by InboxRateLimiter)."""
        return self._heartbeat_running

    @heartbeat_running.setter
    def heartbeat_running(self, value: bool) -> None:
        self._heartbeat_running = value

    # ── Setup ────────────────────────────────────────────────────

    def setup(self) -> None:
        """Set up and start the autonomous scheduler for heartbeat and cron."""
        if not self._anima:
            return

        try:
            self.scheduler = AsyncIOScheduler(timezone=get_app_timezone())
            self._last_schedule_level = load_config().activity_level
            self._setup_heartbeat()
            self._setup_cron_tasks()
            self._setup_activity_schedule()
            self._setup_background_review_drain()
            self.scheduler.start()

            # Wire up hot-reload callback
            self._anima.set_on_schedule_changed(self.reload_schedule)
            self._record_schedule_mtimes()

            job_count = len(self.scheduler.get_jobs())
            logger.info(
                "Scheduler started for %s: %d jobs registered",
                self._anima_name,
                job_count,
            )
        except Exception:
            logger.exception("Failed to setup scheduler for %s", self._anima_name)
            self.scheduler = None

    def _read_per_anima_interval(self, app_config: Any) -> int:
        """Read heartbeat_interval_minutes from status.json, fallback to global config."""
        return read_per_anima_heartbeat_interval(self._anima_dir, app_config)

    def _read_per_anima_max_interval(self) -> int | None:
        """Read optional heartbeat_max_interval_minutes from status.json."""
        try:
            status_path = self._anima_dir / "status.json"
            if status_path.is_file():
                data = json.loads(status_path.read_text(encoding="utf-8"))
                val = data.get("heartbeat_max_interval_minutes")
                if isinstance(val, (int, float)) and 5 <= val <= 1440:
                    return int(val)
        except (json.JSONDecodeError, OSError, ValueError):
            logger.debug("Failed to read heartbeat_max_interval_minutes from %s", self._anima_dir)
        return None

    def _setup_heartbeat(self) -> None:
        """Register heartbeat job from heartbeat.md + config.json + activity_level."""
        if not self._anima or not self.scheduler:
            return

        job_id = f"{self._anima_name}_heartbeat"
        if not self._anima.memory.read_model_config().heartbeat_enabled:
            if self.scheduler.get_job(job_id) is not None:
                self.scheduler.remove_job(job_id)
            logger.info("Heartbeat disabled for '%s'", self._anima_name)
            return

        hb_content = self._anima.memory.read_heartbeat_config()
        if not hb_content:
            return

        active_start, active_end = parse_heartbeat_config(hb_content)

        app_config = load_config()
        base_interval = self._read_per_anima_interval(app_config)

        # Governor is authoritative when present: it already accounts for
        # budget/time pressure.  Manual ``config.activity_level`` (resolved
        # per-provider) is only used as a fallback when no governor state
        # is available.  Heartbeat is background/self-initiated work, so it
        # follows the Anima's background provider when one is configured.
        governor_level = _read_governor_background_activity_level(self._anima_dir)
        if governor_level is not None:
            activity_pct = max(1, min(400, governor_level))
            activity_source = "governor"
        else:
            user_level = resolve_user_activity_level(app_config, self._anima_dir)
            activity_pct = max(10, min(400, user_level))
            activity_source = "config"

        # Urgent-mode override: if this Anima has active urgent tasks, pin
        # activity to 100% only when no Usage Governor level is present.
        # Governor is authoritative for provider budget pressure, even for
        # urgent work.
        try:
            from core.urgent import is_urgent_active

            if is_urgent_active(self._anima_dir):
                if governor_level is None:
                    activity_pct = max(activity_pct, 100)
                    activity_source = f"{activity_source}+urgent"
                else:
                    activity_source = f"{activity_source}+urgent-governed"
        except Exception:  # noqa: BLE001
            logger.debug("urgent check failed during scheduler setup", exc_info=True)

        effective_interval = base_interval / (activity_pct / 100.0)
        effective_interval = max(5.0, effective_interval)
        interval = round(effective_interval)
        max_interval = self._read_per_anima_max_interval()
        if max_interval is not None and interval > max_interval:
            interval = max_interval
            activity_source = f"{activity_source}+cap"

        # Always record the resolved interval for diagnostics/tests regardless
        # of whether CronTrigger or polling is selected below.
        self._hb_effective_interval = interval

        # Deterministic per-anima phase offset to de-synchronize heartbeats
        # across the fleet.  Spread across the full interval (capped at 30 min
        # so large idle intervals don't delay the first beat for hours) instead
        # of a fixed 0-9 window: with many Animas sharing one provider pool, a
        # narrow 10-slot spread piled multiple beats into the same minute and
        # burst past the provider's per-minute (RPM) rate limit.  ``min(...)``
        # keeps ``offset < interval`` so the cron minute-slot path stays valid.
        offset = zlib.crc32(self._anima_name.encode()) % min(interval, 30)

        # Determine active hours
        if active_start is not None and active_end is not None:
            log_active = f"active {active_start}:00-{active_end}:00"
        else:
            log_active = "24h"
        hour_spec = _active_hour_spec(active_start, active_end)

        # CronTrigger minute-slot approach only works when interval divides
        # evenly into 60; otherwise cross-hour gaps become shorter than the
        # intended interval (e.g. interval=43 → slots "9,52" → 43min then
        # 17min gap).  Fall through to polling for non-divisor intervals.
        if interval <= 60 and 60 % interval == 0:
            slots = []
            m = offset
            while m < 60:
                slots.append(str(m))
                m += interval
            minute_spec = ",".join(slots)

            self.scheduler.add_job(
                self.heartbeat_tick,
                CronTrigger(
                    minute=minute_spec,
                    hour=hour_spec,
                ),
                id=f"{self._anima_name}_heartbeat",
                name=f"{self._anima_name} heartbeat",
                replace_existing=True,
                misfire_grace_time=300,
                max_instances=1,
            )
            logger.info(
                "Heartbeat registered: %s minute=%s (offset=%d, interval=%dmin, activity=%d%% [%s]), %s",
                self._anima_name,
                minute_spec,
                offset,
                interval,
                activity_pct,
                activity_source,
                log_active,
            )
        else:
            # Polling: check every minute, fire when interval elapsed.
            # Replaces the old IntervalTrigger path which had end_date bugs.
            self._hb_effective_interval = interval
            self._hb_active_start = active_start
            self._hb_active_end = active_end
            self._hb_first_check_offset = offset
            self._hb_first_check_done = False

            self.scheduler.add_job(
                self._heartbeat_check,
                CronTrigger(minute="*", hour=hour_spec),
                id=f"{self._anima_name}_heartbeat",
                name=f"{self._anima_name} heartbeat",
                replace_existing=True,
                misfire_grace_time=120,
                max_instances=1,
            )
            logger.info(
                "Heartbeat registered (polling): %s every %dmin (offset=%d, activity=%d%% [%s]), %s",
                self._anima_name,
                interval,
                offset,
                activity_pct,
                activity_source,
                log_active,
            )

    def reschedule_heartbeat(self) -> None:
        """Reschedule heartbeat job with current root-owned config."""
        if not self.scheduler:
            return
        self._last_schedule_level = load_config().activity_level
        job_id = f"{self._anima_name}_heartbeat"
        try:
            self.scheduler.remove_job(job_id)
        except KeyError:
            pass
        self._setup_heartbeat()
        logger.info("Heartbeat rescheduled for %s", self._anima_name)

    # ── Activity Schedule ─────────────────────────────────────

    def _setup_background_review_drain(self) -> None:
        """Drain review requests recorded by disposable task runners."""
        if not self.scheduler:
            return
        self.scheduler.add_job(
            self._background_review_tick,
            CronTrigger(minute="*/5"),
            id=f"{self._anima_name}_background_review_drain",
            name=f"{self._anima_name} background review drain",
            replace_existing=True,
            misfire_grace_time=120,
            max_instances=1,
        )

    async def _background_review_tick(self) -> None:
        from core.memory.maintenance.background_review import (
            has_pending_background_review,
            request_background_review,
        )

        if has_pending_background_review(self._anima_dir):
            request_background_review(self._anima_dir, "")

    def _setup_activity_schedule(self) -> None:
        """Register a 1-minute safety poll for root-owned activity settings."""
        if not self.scheduler:
            return
        app_config = load_config()
        self.scheduler.add_job(
            self._activity_schedule_tick,
            CronTrigger(minute="*"),
            id=f"{self._anima_name}_activity_schedule",
            name=f"{self._anima_name} activity-level sync",
            replace_existing=True,
            misfire_grace_time=120,
            max_instances=1,
        )
        logger.info(
            "Activity-level safety poll registered for %s (schedule entries=%d)",
            self._anima_name,
            len(app_config.activity_schedule),
        )

    def _sync_activity_level(self) -> None:
        """Rebuild this Anima's heartbeat from the latest root-owned level."""
        current_level = load_config().activity_level
        if self._last_schedule_level is None:
            self._last_schedule_level = current_level
            return
        if current_level == self._last_schedule_level:
            return
        previous = self._last_schedule_level
        self._last_schedule_level = current_level
        self.reschedule_heartbeat()
        logger.info(
            "Activity level sync: %s %d%% → %d%%",
            self._anima_name,
            previous,
            current_level,
        )

    async def _activity_schedule_tick(self) -> None:
        """Reconcile heartbeat timing if a root IPC notification was missed."""
        self._sync_activity_level()

    def reload_activity_schedule(self) -> None:
        """Refresh the safety poll after root-owned activity schedule changes."""
        if not self.scheduler:
            return
        job_id = f"{self._anima_name}_activity_schedule"
        try:
            self.scheduler.remove_job(job_id)
        except KeyError:
            pass
        self._setup_activity_schedule()
        self._sync_activity_level()

    def _setup_cron_tasks(self) -> None:
        """Register cron jobs from cron.md."""
        if not self._anima or not self.scheduler:
            return

        config = self._anima.memory.read_cron_config()
        if not config:
            self._write_cron_registration([], [])
            return

        tasks = parse_cron_md(config)
        registered_tasks: list[dict[str, str]] = []
        rejected_tasks: list[dict[str, str]] = []
        registered = 0
        for i, task in enumerate(tasks):
            trigger = parse_schedule(task.schedule)
            if not trigger:
                # A section with no schedule *and* no action is prose (notes,
                # migration memos), not a misconfigured job — don't nag about it.
                is_job = bool(task.schedule.strip() or task.command or task.tool)
                if is_job:
                    reason = "Empty schedule expression" if not task.schedule.strip() else "Invalid cron expression"
                    rejected_tasks.append({"name": task.name, "reason": reason})
                logger.warning(
                    "Could not parse schedule for cron task '%s': '%s'",
                    task.name,
                    task.schedule,
                )
                continue

            self.scheduler.add_job(
                self.cron_tick,
                trigger,
                id=f"{self._anima_name}_cron_{i}",
                name=f"{self._anima_name}: {task.name}",
                args=[task],
                replace_existing=True,
                misfire_grace_time=1800,
                max_instances=1,
            )
            registered += 1
            registered_tasks.append({"name": task.name, "schedule": task.schedule})
            self._log_cron_event(task, "scheduled")
            logger.info(
                "Cron registered: %s -> %s (%s) [%s]",
                self._anima_name,
                task.name,
                task.schedule,
                task.type,
            )

        self._write_cron_registration(registered_tasks, rejected_tasks)
        self._check_cron_parse_health(config, tasks, registered)

    def _write_cron_registration(
        self,
        registered: list[dict[str, str]],
        rejected: list[dict[str, str]],
    ) -> None:
        """Persist the outcome of one cron registration cycle."""
        try:
            atomic_write_json(
                self._anima_dir / "state" / "cron_registration.json",
                {
                    "parsed_at": now_local().isoformat(),
                    "registered": registered,
                    "rejected": rejected,
                },
                sort_keys=True,
            )
        except OSError:
            logger.warning("Failed to persist cron registration for %s", self._anima_name, exc_info=True)

    def _log_cron_event(self, task: CronTask, event: str, reason: str = "") -> None:
        """Best-effort scheduler audit logging."""
        try:
            self._anima.memory.append_cron_event(
                task.name,
                event,
                reason=reason,
                schedule=task.schedule,
            )
        except Exception:
            logger.debug("Failed to record cron audit event", exc_info=True)

    # ── Cron parse diagnostics ────────────────────────────────────

    def _check_cron_parse_health(
        self,
        raw_config: str,
        tasks: list[CronTask],
        registered: int,
    ) -> None:
        """Validate cron parse results and notify the Anima if unhealthy.

        Called at the end of ``_setup_cron_tasks`` (both initial setup and
        hot-reload).  Writes a markdown file to ``background_notifications/``
        which is drained into the next heartbeat or cron context.
        """
        messages: list[str] = []
        effective_config = _strip_cron_documentation(raw_config)

        if tasks and registered == 0:
            messages.append(t("scheduler.cron_health_no_valid_schedule", task_count=len(tasks)))

        if _INDENTED_SCHEDULE_RE.search(effective_config):
            messages.append(t("scheduler.cron_health_indented_schedule"))

        if not tasks and "schedule:" in effective_config:
            messages.append(t("scheduler.cron_health_unrecognized_schedule"))

        if messages:
            self._write_cron_health_notification("\n\n".join(messages))

    def _write_cron_health_notification(self, message: str) -> None:
        """Write a cron health warning to ``background_notifications/``."""
        try:
            notif_dir = self._anima_dir / "state" / "background_notifications"
            notif_dir.mkdir(parents=True, exist_ok=True)
            ts = now_local().strftime("%Y%m%d_%H%M%S")
            notif_path = notif_dir / f"cron_health_{ts}.md"
            content = f"# {t('scheduler.cron_health_title')}\n\n{message}\n"
            notif_path.write_text(content, encoding="utf-8")
            logger.warning(
                "[%s] Cron health warning written: %s",
                self._anima_name,
                notif_path.name,
            )
        except Exception:
            logger.debug(
                "Failed to write cron health notification for %s",
                self._anima_name,
                exc_info=True,
            )

    # ── Polling-based Heartbeat ─────────────────────────────────

    def _in_active_hours(self, now: datetime) -> bool:
        """Return True if *now* falls within the configured active hours."""
        if self._hb_active_start is None or self._hb_active_end is None:
            return True
        hour = now.hour
        start, end = self._hb_active_start, self._hb_active_end
        if start < end:
            return start <= hour < end
        # Midnight-crossing (e.g. 22:00 – 06:00)
        return hour >= start or hour < end

    def _get_last_heartbeat_ts(self) -> datetime | None:
        """Return the timestamp of the most recent heartbeat_start from activity_log."""
        try:
            entries = self._anima._activity.recent(
                days=2,
                types=["heartbeat_start"],
                limit=1,
            )
        except Exception:
            logger.debug("Failed to read activity_log for last heartbeat", exc_info=True)
            return None
        if not entries:
            return None
        try:
            return datetime.fromisoformat(entries[-1].ts)
        except (ValueError, TypeError):
            return None

    async def _heartbeat_check(self) -> None:
        """Polling-based heartbeat trigger for intervals > 60 minutes.

        Registered as a CronTrigger(minute="*") job.  Each minute it checks
        whether enough time has elapsed since the last heartbeat (read from
        the activity_log) and whether the current time is within active hours.
        """
        if not self._anima:
            return

        now = now_local()

        if not self._in_active_hours(now):
            return

        last_hb = self._get_last_heartbeat_ts()
        if last_hb is not None:
            if last_hb.tzinfo is None:
                last_hb = last_hb.replace(tzinfo=now.tzinfo)
            elapsed_min = (now - last_hb).total_seconds() / 60.0
            required = self._hb_effective_interval
            if not self._hb_first_check_done:
                required += self._hb_first_check_offset
            if elapsed_min < required:
                return
        else:
            # No heartbeat_start in activity_log (fresh install).
            # Apply offset delay before first heartbeat to spread across Animas.
            if not self._hb_first_check_done and self._hb_first_check_offset > 0:
                # On the very first call _hb_first_check_done is False.
                # Mark it done and skip this minute — the offset will be
                # consumed on subsequent calls via the `required` increase above.
                # For simplicity, just allow immediate fire for fresh installs.
                pass

        self._hb_first_check_done = True
        await self.heartbeat_tick()

    # ── Tick Handlers ────────────────────────────────────────────

    def _awaiting_initial_setup(self) -> bool:
        """Keep periodic work out of the user's initial profile conversation."""
        from core.anima.bootstrap_state import get_bootstrap_status

        return bool(get_bootstrap_status(self._anima_dir).get("needs_bootstrap"))

    async def heartbeat_tick(self) -> None:
        """Execute a scheduled heartbeat."""
        if not self._anima:
            return
        # A job already dispatched by APScheduler can outlive a disable/reload.
        # Only this periodic entrance is gated; messages and cron keep working.
        if not self._anima.memory.read_model_config().heartbeat_enabled:
            return
        if self._awaiting_initial_setup():
            logger.debug("Scheduled heartbeat deferred until setup completes: %s", self._anima_name)
            return
        # Detect schedule file changes (Mode S Write/Edit bypass)
        self._check_schedule_freshness()
        if self._heartbeat_running:
            logger.info("Scheduled heartbeat SKIPPED (already running): %s", self._anima_name)
            return
        self._heartbeat_running = True
        try:
            logger.info("Scheduled heartbeat: %s", self._anima_name)
            isolated = await self._task_runner_supervisor.run_heartbeat()
            result = isolated.get("result")
            if not isinstance(result, dict):
                raise ValueError("isolated heartbeat result must be an object")
            self._emit_event(
                "anima.heartbeat",
                {
                    "name": self._anima_name,
                    "result": result,
                },
            )
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            logger.warning("Scheduled heartbeat cancelled without scheduler shutdown: %s", self._anima_name)
        except Exception:
            logger.exception("Scheduled heartbeat failed: %s", self._anima_name)
        finally:
            self._heartbeat_running = False

    async def cron_tick(self, task: CronTask) -> None:
        """Execute a scheduled cron task."""
        if not self._anima:
            return
        if self._awaiting_initial_setup():
            logger.debug("Scheduled cron deferred until setup completes: %s", self._anima_name)
            return

        # Detect schedule file changes and skip stale tasks
        if self._check_schedule_freshness():
            self._log_cron_event(task, "skipped", "schedule reloaded")
            logger.info(
                "Skipping stale cron '%s' for %s (schedule reloaded)",
                task.name,
                self._anima_name,
            )
            return

        if task.name in self._cron_running:
            self._log_cron_event(task, "skipped", "already running")
            logger.info(
                "Scheduled cron SKIPPED (already running): %s -> %s",
                self._anima_name,
                task.name,
            )
            return

        logger.info("Scheduled cron: %s -> %s [%s]", self._anima_name, task.name, task.type)
        self._log_cron_event(task, "fired")
        # Run in separate task to avoid blocking other scheduled jobs
        self._cron_running.add(task.name)
        try:
            spawn(
                self._run_cron_task(task),
                name=f"cron-{self._anima_name}-{task.name}",
            )
        except Exception:
            self._cron_running.discard(task.name)
            raise

    async def _run_command_cron(self, task: CronTask) -> dict[str, Any]:
        """Run a shell-command cron in this scheduler process, isolating only its LLM follow-up."""
        current = asyncio.current_task()
        if current is not None:
            self._direct_cron_tasks.add(current)
        try:
            result = await self._anima.run_cron_command(
                task.name,
                command=task.command,
                tool=task.tool,
                args=task.args,
                env=self._task_runner_supervisor.build_cron_command_environment(),
                serialize=False,
            )
            success = result.get("exit_code", 1) == 0
            followup_result: dict[str, Any] | None = None
            usage: dict[str, int] | None = None
            # Preserve the legacy flag's command-output follow-up semantics; it does not call heartbeat_tick.
            command_output = command_followup_output(task, result)
            if command_output is not None:
                followup = await self._task_runner_supervisor.run_cron_followup(task, command_output)
                followup_result = followup.get("result")
                if not isinstance(followup_result, dict):
                    raise ValueError("isolated cron follow-up result must be an object")
                success = success and bool(followup.get("success"))
                usage = followup.get("usage")
            return {
                "task_type": "command",
                "result": result,
                "followup_result": followup_result,
                "success": success,
                "usage": usage,
            }
        finally:
            if current is not None:
                self._direct_cron_tasks.discard(current)

    async def _run_cron_task(self, task: CronTask) -> None:
        """Run one cron task; shell commands stay in the Anima main, LLM work is isolated."""
        if not self._anima:
            return
        self._cron_running.add(task.name)
        success = False
        try:
            # Raw shell crons already bypass ToolHandler policy; tool-only crons
            # stay in the runner so their existing ToolHandler checks are preserved.
            if task.type == "command" and (task.command or not task.tool):
                isolated = await self._run_command_cron(task)
            else:
                isolated = await self._task_runner_supervisor.run_cron(task)
            success = bool(isolated.get("success"))
            result = isolated.get("result")
            if not isinstance(result, dict):
                raise ValueError("isolated cron result must be an object")
            self._emit_event(
                "anima.cron",
                {
                    "name": self._anima_name,
                    "task": task.name,
                    "task_type": task.type,
                    "result": result,
                },
            )
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            logger.warning("Cron task cancelled without scheduler shutdown: %s -> %s", self._anima_name, task.name)
        except Exception:
            logger.exception("Cron task failed: %s -> %s", self._anima_name, task.name)
        finally:
            if not success:
                self._log_cron_event(task, "failed", "execution failed")
            self._cron_running.discard(task.name)

    async def shutdown_task_runners(self) -> None:
        """Cancel Anima-main-side cron commands and reap isolated task processes."""
        current = asyncio.current_task()
        direct_tasks = [task for task in self._direct_cron_tasks if task is not current and not task.done()]
        for task in direct_tasks:
            task.cancel()
        if direct_tasks:
            await asyncio.gather(*direct_tasks, return_exceptions=True)
        if self._task_runner_supervisor is not None:
            await self._task_runner_supervisor.close()

    # ── Reload ───────────────────────────────────────────────────

    def reload_schedule(self, name: str) -> dict[str, Any]:
        """Reload heartbeat and cron schedules from disk (hot-reload callback)."""
        if not self.scheduler:
            return {"error": "Scheduler not running"}

        # Remove all existing jobs
        removed = 0
        for job in self.scheduler.get_jobs():
            job.remove()
            removed += 1

        # Re-setup from current files
        self._setup_heartbeat()
        self._setup_cron_tasks()
        self._setup_activity_schedule()
        self._setup_background_review_drain()
        self._record_schedule_mtimes()

        new_jobs = [j.id for j in self.scheduler.get_jobs()]
        logger.info(
            "Schedule reloaded for %s: removed=%d, new_jobs=%s",
            self._anima_name,
            removed,
            new_jobs,
        )
        return {"reloaded": name, "removed": removed, "new_jobs": new_jobs}

    # ── Schedule Freshness ─────────────────────────────────────

    def _record_schedule_mtimes(self) -> None:
        """Snapshot cron.md and heartbeat.md mtimes for later freshness checks."""
        cron_path = self._anima_dir / "cron.md"
        hb_path = self._anima_dir / "heartbeat.md"
        try:
            self._cron_md_mtime = cron_path.stat().st_mtime if cron_path.is_file() else 0.0
        except OSError:
            self._cron_md_mtime = 0.0
        try:
            self._heartbeat_md_mtime = hb_path.stat().st_mtime if hb_path.is_file() else 0.0
        except OSError:
            self._heartbeat_md_mtime = 0.0

    def _check_schedule_freshness(self) -> bool:
        """Check if cron.md or heartbeat.md changed since last setup.

        If a change is detected, reloads the schedule and returns True.
        Returns False when no change is detected.
        """
        cron_path = self._anima_dir / "cron.md"
        hb_path = self._anima_dir / "heartbeat.md"
        try:
            cron_mtime = cron_path.stat().st_mtime if cron_path.is_file() else 0.0
        except OSError:
            cron_mtime = 0.0
        try:
            hb_mtime = hb_path.stat().st_mtime if hb_path.is_file() else 0.0
        except OSError:
            hb_mtime = 0.0

        if cron_mtime != self._cron_md_mtime or hb_mtime != self._heartbeat_md_mtime:
            logger.info(
                "Schedule file changed for %s (cron mtime %.0f->%.0f, hb mtime %.0f->%.0f), reloading",
                self._anima_name,
                self._cron_md_mtime,
                cron_mtime,
                self._heartbeat_md_mtime,
                hb_mtime,
            )
            self.reload_schedule(self._anima_name)
            return True
        return False

    # ── Cleanup ──────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Stop the scheduler."""
        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception:
                logger.debug(
                    "Scheduler shutdown failed for %s (may not have been started)", self._anima_name, exc_info=True
                )
            logger.info("Scheduler stopped for %s", self._anima_name)
