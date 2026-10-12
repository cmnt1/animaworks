from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Low-latency atomic-fact extraction from completed conversation activity."""

import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

from core.config.helper_models import ResolvedHelperModel, resolve_helper_model
from core.platform.atomic_io import atomic_write_json
from core.time_utils import ensure_aware, get_app_timezone, now_local

logger = logging.getLogger("animaworks.memory.live_fact_extraction")

_ACTIVITY_TYPES = (
    "message_received",
    "message_sent",
    "response_sent",
    "human_notify",
    "inbox_processing_end",
    "task_exec_end",
    "task_completed",
    "task_result",
    "memory_write",
)
_MESSAGE_RECEIVED_TYPES = frozenset({"message_received", "dm_received"})
_MESSAGE_SENT_TYPES = frozenset({"message_sent", "dm_sent"})
_TASK_RESULT_TYPES = frozenset({"task_exec_end", "task_completed", "task_result"})
_HUMAN_OR_ANIMA_SOURCES = frozenset(
    {
        "human",
        "anima",
        "external",
        "external_platform",
        "slack",
        "chatwork",
        "googlechat",
        "discord",
        "zoom",
    }
)
_KNOWN_UNSUCCESSFUL_TASK_STATUSES = frozenset({"failed", "error", "cancelled", "canceled", "budget_skipped", "skipped"})
_MAX_ACTIVITY_BODY_CHARS = 2_000
_CHECKPOINT_NAME = "live_fact_checkpoint.json"


@dataclass(frozen=True)
class LiveFactInput:
    """Bounded activity text and whether it contains a live-extraction trigger."""

    text: str
    qualifies: bool
    entry_count: int


@dataclass(frozen=True)
class LiveFactRunResult:
    """Summary of one live fact extraction attempt."""

    trigger: str
    since: datetime
    until: datetime
    input_chars: int = 0
    facts_extracted: int = 0
    duplicates: int = 0
    failed: bool = False
    skipped_reason: str = ""
    extract_llm_calls: int = 0
    reconcile_llm_calls: int = 0


@dataclass(frozen=True)
class _LiveFactOptions:
    enabled: bool
    model: str
    credential: str
    min_input_chars: int
    max_input_chars: int
    debounce_seconds: int
    helper_model: ResolvedHelperModel | None = None


def _parse_datetime(value: datetime | str | None, *, fallback: datetime | None = None) -> datetime:
    """Parse an ISO timestamp and normalize naive values to the app timezone."""
    if isinstance(value, datetime):
        return ensure_aware(value)
    if isinstance(value, str) and value.strip():
        try:
            return ensure_aware(datetime.fromisoformat(value))
        except ValueError:
            pass
    return ensure_aware(fallback or now_local())


def _load_options(anima_dir: Path | None = None) -> _LiveFactOptions:
    from core.config import load_config
    from core.config.schemas import ConsolidationConfig

    config = load_config()
    consolidation = getattr(config, "consolidation", None)
    defaults = ConsolidationConfig()
    helper_model = resolve_helper_model("fact_extraction", anima_dir, config=config)
    return _LiveFactOptions(
        enabled=bool(getattr(consolidation, "live_fact_extraction_enabled", defaults.live_fact_extraction_enabled)),
        model=helper_model.model,
        credential=helper_model.credential or "",
        helper_model=helper_model,
        min_input_chars=max(
            0, int(getattr(consolidation, "live_fact_min_input_chars", defaults.live_fact_min_input_chars))
        ),
        max_input_chars=max(
            0, int(getattr(consolidation, "live_fact_max_input_chars", defaults.live_fact_max_input_chars))
        ),
        debounce_seconds=max(
            0,
            int(getattr(consolidation, "live_fact_debounce_seconds", defaults.live_fact_debounce_seconds)),
        ),
    )


def resolve_live_fact_model_and_credential(consolidation: Any) -> tuple[str, str]:
    """Compatibility facade for the former live-fact model resolver."""
    from types import SimpleNamespace

    helper_model = resolve_helper_model(
        "fact_extraction",
        config=SimpleNamespace(consolidation=consolidation),
    )
    return helper_model.model, helper_model.credential or ""


def _is_consolidation_active(anima_dir: Path) -> bool:
    return (Path(anima_dir) / "state" / ".consolidation_mode").exists()


def _checkpoint_path(anima_dir: Path) -> Path:
    return Path(anima_dir) / "state" / _CHECKPOINT_NAME


def _read_checkpoint(anima_dir: Path) -> datetime | None:
    path = _checkpoint_path(anima_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    last_until = payload.get("last_until")
    if not isinstance(last_until, str):
        return None
    try:
        return ensure_aware(datetime.fromisoformat(last_until))
    except ValueError:
        logger.debug("Ignoring malformed live fact checkpoint at %s", path)
        return None


def _write_checkpoint(anima_dir: Path, until: datetime) -> None:
    """Persist the processed range end via a sibling-temp-file atomic rename."""
    atomic_write_json(_checkpoint_path(anima_dir), {"last_until": until.isoformat()})


def _canonical_type(event_type: str) -> str:
    return {"dm_received": "message_received", "dm_sent": "message_sent"}.get(event_type, event_type)


def _entry_body(entry: Any) -> str:
    event_type = _canonical_type(str(getattr(entry, "type", "")))
    meta = entry.meta if isinstance(getattr(entry, "meta", None), dict) else {}

    if event_type == "memory_write":
        raw_body = getattr(entry, "summary", "")
    elif event_type in _TASK_RESULT_TYPES:
        raw_body = getattr(entry, "content", "") or meta.get("result") or getattr(entry, "summary", "")
    elif event_type == "human_notify":
        raw_body = getattr(entry, "content", "") or meta.get("subject") or getattr(entry, "summary", "")
    else:
        raw_body = getattr(entry, "content", "") or getattr(entry, "summary", "")

    body = " ".join(str(raw_body or "").split())
    return body[:_MAX_ACTIVITY_BODY_CHARS]


def _entry_peer(entry: Any) -> str:
    event_type = _canonical_type(str(getattr(entry, "type", "")))
    meta = entry.meta if isinstance(getattr(entry, "meta", None), dict) else {}
    if event_type in _MESSAGE_RECEIVED_TYPES:
        return str(getattr(entry, "from_person", "") or "unknown")
    if event_type in _MESSAGE_SENT_TYPES or event_type == "response_sent":
        return str(getattr(entry, "to_person", "") or "unknown")
    if event_type == "human_notify":
        return str(getattr(entry, "to_person", "") or meta.get("subject") or "human")
    if event_type in _TASK_RESULT_TYPES:
        return str(meta.get("title") or meta.get("task_id") or "task")
    if event_type == "inbox_processing_end":
        senders = meta.get("senders")
        if isinstance(senders, list):
            return ",".join(str(sender) for sender in senders[:5]) or "inbox"
    if event_type == "memory_write":
        return str(meta.get("path") or "memory")
    return ""


def _entry_qualifies(entry: Any) -> bool:
    event_type = _canonical_type(str(getattr(entry, "type", "")))
    meta = entry.meta if isinstance(getattr(entry, "meta", None), dict) else {}

    if event_type in _MESSAGE_RECEIVED_TYPES:
        source = str(meta.get("from_type") or getattr(entry, "origin", "") or "").strip().lower()
        return source in _HUMAN_OR_ANIMA_SOURCES
    if event_type == "human_notify":
        return True
    if event_type == "response_sent":
        context = str(getattr(entry, "ctx", "") or "").lower()
        channel = str(getattr(entry, "channel", "") or "").lower()
        session_type = str(meta.get("session_type", "") or "").lower()
        if context == "heartbeat" or context.startswith("cron:"):
            return False
        return channel in {"", "chat", "inbox"} or session_type in {"chat", "inbox"}
    if event_type in _MESSAGE_SENT_TYPES:
        source = str(meta.get("from_type", "") or "").strip().lower()
        return source in {"external", "external_platform", "human", "slack", "chatwork", "googlechat", "discord"}
    if event_type in _TASK_RESULT_TYPES:
        status = str(meta.get("status", "") or "").strip().lower()
        return not status or status not in _KNOWN_UNSUCCESSFUL_TASK_STATUSES
    return False


def _render_entry(entry: Any) -> str:
    body = _entry_body(entry)
    if not body:
        return ""
    timestamp = str(getattr(entry, "ts", "") or "unknown-time")
    event_type = str(getattr(entry, "type", "unknown"))
    peer = _entry_peer(entry)
    peer_label = f" {peer}" if peer else ""
    return f"{timestamp} {event_type}{peer_label}: {body}"


def build_live_fact_input(
    anima_dir: Path,
    since: datetime | str,
    until: datetime | str,
    *,
    max_input_chars: int = 24_000,
    exclusive_since: bool = False,
) -> LiveFactInput:
    """Build bounded LLM input from conversation/result activity only.

    Activity is read through :class:`ActivityLogger`; non-conversation events
    such as tool calls, cron executions, and heartbeat events are excluded.
    When the combined budget is exceeded, newest entries are retained first.
    """
    start = _parse_datetime(since)
    end = _parse_datetime(until)
    if start > end:
        return LiveFactInput("", False, 0)

    from core.activity.logger import ActivityLogger

    activity = ActivityLogger(Path(anima_dir))
    entries = activity._load_entries(since=start, until=end, types=list(_ACTIVITY_TYPES))
    bounded_entries: list[Any] = []
    for entry in entries:
        try:
            timestamp = ensure_aware(datetime.fromisoformat(entry.ts))
        except (TypeError, ValueError):
            continue
        if timestamp < start or timestamp > end or (exclusive_since and timestamp <= start):
            continue
        bounded_entries.append(entry)

    rendered = [(entry, _render_entry(entry)) for entry in bounded_entries]
    rendered = [(entry, line) for entry, line in rendered if line]
    budget = max(0, int(max_input_chars))
    selected_newest_first: list[tuple[Any, str]] = []
    used_chars = 0
    for entry, line in reversed(rendered):
        separator_chars = 1 if selected_newest_first else 0
        available = budget - used_chars - separator_chars
        if available <= 0:
            break
        if len(line) <= available:
            selected_newest_first.append((entry, line))
            used_chars += separator_chars + len(line)
            continue
        selected_newest_first.append((entry, line[:available]))
        used_chars += separator_chars + available
        break

    selected = list(reversed(selected_newest_first))
    text = "\n".join(line for _entry, line in selected)
    qualifies = any(_entry_qualifies(entry) for entry, _line in selected)
    return LiveFactInput(text=text, qualifies=qualifies, entry_count=len(selected))


def _make_fact_extractor(anima_dir: Path, options: _LiveFactOptions) -> Any:
    from core.config import load_config
    from core.memory.facts.config import (
        DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS,
        _coerce_timeout_seconds,
        _resolve_extraction_max_tokens,
    )
    from core.memory.facts.extractor import FactExtractor

    config = load_config()
    timeout = _coerce_timeout_seconds(
        getattr(getattr(config, "rag", None), "fact_extraction_timeout_seconds", None),
        DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS,
    )
    locale = str(getattr(config, "locale", "") or "ja")
    helper_model = options.helper_model or resolve_helper_model("fact_extraction", anima_dir, config=config)
    return FactExtractor(
        model=options.model,
        credential=options.credential,
        locale=locale,
        timeout=timeout,
        llm_extra={},
        anima_dir=anima_dir,
        max_tokens=helper_model.max_output_tokens or _resolve_extraction_max_tokens(),
        allow_agent_sdk_fallback=helper_model.allow_agent_sdk_fallback,
        helper_model=helper_model,
    )


def build_background_fact_extractor(anima_dir: Path) -> Any:
    """Build the extractor used outside the conversation lanes.

    Daily consolidation and live extraction share the registered
    ``fact_extraction`` role so fact calls remain separate from episode-summary
    calls unless the configured role explicitly assigns them the same model.
    """
    return _make_fact_extractor(anima_dir, _load_options(anima_dir))


def _log_run(result: LiveFactRunResult, elapsed_seconds: float) -> None:
    logger.info(
        "Live fact extraction: trigger=%s range=%s~%s input_chars=%d facts_extracted=%d duplicates=%d "
        "elapsed=%.2fs extract_llm_calls=%d reconcile_llm_calls=%d",
        result.trigger,
        result.since.isoformat(),
        result.until.isoformat(),
        result.input_chars,
        result.facts_extracted,
        result.duplicates,
        elapsed_seconds,
        result.extract_llm_calls,
        result.reconcile_llm_calls,
    )


async def run_live_fact_extraction(
    anima_dir: Path,
    *,
    trigger: str,
    session_started_at: datetime | str | None = None,
    until: datetime | str | None = None,
) -> LiveFactRunResult:
    """Extract facts for a just-completed chat, inbox, or task session."""
    import time

    started_mono = time.monotonic()
    anima_dir = Path(anima_dir)
    options = _load_options(anima_dir)
    end = _parse_datetime(until, fallback=now_local())
    start_hint = _parse_datetime(session_started_at, fallback=end)
    checkpoint = _read_checkpoint(anima_dir)
    since = max(start_hint, checkpoint) if checkpoint is not None else start_hint

    result = LiveFactRunResult(trigger=trigger, since=since, until=end)
    if not options.enabled:
        return replace(result, skipped_reason="disabled")
    if _is_consolidation_active(anima_dir):
        return replace(result, skipped_reason="consolidation_mode")
    if since >= end:
        _log_run(result, time.monotonic() - started_mono)
        return replace(result, skipped_reason="already_processed")

    activity_input = await asyncio.to_thread(
        build_live_fact_input,
        anima_dir,
        since,
        end,
        max_input_chars=options.max_input_chars,
        exclusive_since=checkpoint is not None and since == checkpoint,
    )
    input_chars = len(activity_input.text)
    result = LiveFactRunResult(trigger=trigger, since=since, until=end, input_chars=input_chars)
    if not activity_input.qualifies or input_chars < options.min_input_chars:
        _write_checkpoint(anima_dir, end)
        _log_run(result, time.monotonic() - started_mono)
        reason = "no_qualifying_entry" if not activity_input.qualifies else "input_too_short"
        return replace(result, skipped_reason=reason)

    if _is_consolidation_active(anima_dir):
        return replace(result, skipped_reason="consolidation_mode")

    from core.memory.maintenance.consolidation import ConsolidationEngine

    extractor = _make_fact_extractor(anima_dir, options)
    source_date = end.astimezone(get_app_timezone()).date().isoformat()
    engine = ConsolidationEngine(anima_dir, anima_dir.name)
    outcome = await engine.extract_facts_from_text_outcome(
        activity_input.text,
        source_episode=f"activity_log/{source_date}.jsonl",
        source_session_id=f"live:{trigger}:{end.isoformat()}",
        extractor=extractor,
        origin="live",
    )
    result = LiveFactRunResult(
        trigger=trigger,
        since=since,
        until=end,
        input_chars=input_chars,
        facts_extracted=outcome.facts_extracted,
        duplicates=outcome.duplicates,
        failed=outcome.failed,
        extract_llm_calls=outcome.extract_llm_calls,
        reconcile_llm_calls=outcome.reconcile_llm_calls,
    )
    _log_run(result, time.monotonic() - started_mono)
    if outcome.failed:
        reason = (outcome.failure_reason or outcome.failure_stage or "extraction failed").replace("\n", " ")
        logger.warning(
            "Live fact extraction failed: trigger=%s range=%s~%s reason=%s",
            trigger,
            since.isoformat(),
            end.isoformat(),
            reason[:240],
        )
        return result

    _write_checkpoint(anima_dir, end)
    return result


class _LiveFactCoordinator:
    """Per-anima debounce loop; its asyncio lock serializes extraction runs."""

    def __init__(
        self,
        anima_dir: Path,
        *,
        runner: Callable[..., Awaitable[LiveFactRunResult]] | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.anima_dir = Path(anima_dir)
        self._runner = runner
        self._sleeper = sleeper
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._generation = 0
        self._trigger = ""
        self._session_started_at: datetime | None = None
        self._debounce_seconds = 0.0

    def schedule(
        self,
        trigger: str,
        session_started_at: datetime | str | None,
        debounce_seconds: float,
    ) -> None:
        """Queue or coalesce one extraction after the latest trigger goes quiet."""
        requested_start = _parse_datetime(session_started_at, fallback=now_local())
        if self._session_started_at is None or requested_start < self._session_started_at:
            self._session_started_at = requested_start
        self._trigger = trigger
        self._debounce_seconds = max(0.0, float(debounce_seconds))
        self._generation += 1
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name=f"live-fact-{self.anima_dir.name}")

    async def _run(self) -> None:
        current = asyncio.current_task()
        try:
            while True:
                generation = self._generation
                await self._sleeper(self._debounce_seconds)
                if generation != self._generation:
                    continue

                trigger = self._trigger
                session_started_at = self._session_started_at or now_local()
                async with self._lock:
                    if generation != self._generation:
                        continue
                    runner = self._runner or run_live_fact_extraction
                    try:
                        await runner(
                            self.anima_dir,
                            trigger=trigger,
                            session_started_at=session_started_at,
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001 - background task must not affect the caller
                        reason = f"{type(exc).__name__}: {exc}".replace("\n", " ")
                        logger.warning(
                            "Live fact extraction failed: trigger=%s reason=%s",
                            trigger,
                            reason[:240],
                        )

                if generation == self._generation:
                    return
        except asyncio.CancelledError:
            raise
        finally:
            if self._task is current:
                self._task = None
                self._trigger = ""
                self._session_started_at = None


_COORDINATORS: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[Path, _LiveFactCoordinator]] = WeakKeyDictionary()
_COORDINATORS_LOCK = threading.Lock()


def _coordinator_for(anima_dir: Path, loop: asyncio.AbstractEventLoop) -> _LiveFactCoordinator:
    key = Path(anima_dir).resolve()
    with _COORDINATORS_LOCK:
        per_loop = _COORDINATORS.setdefault(loop, {})
        coordinator = per_loop.get(key)
        if coordinator is None:
            coordinator = _LiveFactCoordinator(key)
            per_loop[key] = coordinator
        return coordinator


def schedule_live_fact_extraction(
    anima_dir: Path,
    *,
    trigger: str,
    session_started_at: datetime | str | None = None,
) -> bool:
    """Start/coalesce extraction in the background without blocking a response."""
    normalized_trigger = str(trigger or "").strip().lower()
    if normalized_trigger == "heartbeat" or normalized_trigger.startswith("heartbeat:"):
        return False
    if normalized_trigger == "cron" or normalized_trigger.startswith("cron:"):
        return False

    try:
        anima_dir = Path(anima_dir)
        options = _load_options(anima_dir)
        if not options.enabled or _is_consolidation_active(anima_dir):
            return False
    except Exception as exc:  # noqa: BLE001 - scheduling must not affect the completed session
        reason = f"{type(exc).__name__}: {exc}".replace("\n", " ")
        logger.warning("Live fact extraction was not scheduled: %s", reason[:240])
        return False

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # A session hook must never create a synchronous extraction fallback.
        logger.warning("Live fact extraction was not scheduled outside an asyncio event loop")
        return False

    try:
        coordinator = _coordinator_for(anima_dir, loop)
        coordinator.schedule(normalized_trigger or "unknown", session_started_at, options.debounce_seconds)
        return True
    except Exception as exc:  # noqa: BLE001 - scheduling must not affect the completed session
        reason = f"{type(exc).__name__}: {exc}".replace("\n", " ")
        logger.warning("Live fact extraction was not scheduled: %s", reason[:240])
        return False
