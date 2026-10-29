from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Asynchronous session-adjacent memory and peer-profile review."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

from core.config import load_config
from core.memory.io import atomic_write_json
from core.memory.peer_profiles import normalize_peer_name
from core.paths import load_prompt
from core.time_utils import now_local, today_local

logger = logging.getLogger("animaworks.memory.background_review")
_STATE_FILENAME = "background_review.json"
_REQUESTS_FILENAME = "background_review_requests.jsonl"
_MAX_KNOWLEDGE_NAMES = 100
_MAX_RELATED_PEERS = 10


@dataclass
class _ReviewRuntime:
    """Per-Anima in-process queue; durable pending triggers live in state JSON."""

    task: asyncio.Task[None] | None = None
    pending_triggers: list[str] = field(default_factory=list)
    user_turn_delta: int = 0
    wake: asyncio.Event = field(default_factory=asyncio.Event)


_RUNTIMES: dict[Path, _ReviewRuntime] = {}

# Disposable task runners exit right after their job, which would cancel an
# in-process review. They only record the request; the resident worker drains it.
_DEFERRED_REQUESTS = False


def enable_deferred_requests() -> None:
    """Record review requests to disk instead of running them in this process."""
    global _DEFERRED_REQUESTS
    _DEFERRED_REQUESTS = True


def _requests_path(anima_dir: Path) -> Path:
    return Path(anima_dir) / "state" / _REQUESTS_FILENAME


def _append_deferred_request(anima_dir: Path, trigger: str, *, user_turn: bool) -> None:
    path = _requests_path(anima_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"trigger": str(trigger)[:80], "user_turn": user_turn}, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _consume_deferred_requests(anima_dir: Path, runtime: _ReviewRuntime) -> None:
    path = _requests_path(anima_dir)
    if not path.is_file():
        return
    claimed = path.with_name(f"{path.name}.{id(runtime)}.claimed")
    try:
        path.replace(claimed)
        lines = claimed.read_text(encoding="utf-8").splitlines()
        claimed.unlink()
    except OSError:
        logger.warning("Failed to consume deferred background review requests for %s", anima_dir.name)
        return
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        if item.get("user_turn"):
            runtime.user_turn_delta += 1
        elif item.get("trigger"):
            runtime.pending_triggers.append(str(item["trigger"])[:80])


def has_pending_background_review(anima_dir: Path) -> bool:
    """True when a deferred request or a persisted pending trigger awaits a review."""
    if _requests_path(anima_dir).is_file():
        return True
    return bool(_load_state(_state_path(anima_dir)).get("pending_triggers"))


def request_background_review(anima_dir: Path, trigger: str, *, user_turn: bool = False) -> None:
    """Queue a review without awaiting it or blocking the caller."""
    try:
        if _DEFERRED_REQUESTS:
            if trigger or user_turn:
                _append_deferred_request(Path(anima_dir), trigger, user_turn=user_turn)
            return
        path = Path(anima_dir).resolve()
        runtime = _RUNTIMES.get(path)
        if runtime is None:
            runtime = _RUNTIMES[path] = _ReviewRuntime()
        if user_turn:
            runtime.user_turn_delta += 1
        if trigger and not user_turn:
            runtime.pending_triggers.append(str(trigger)[:80])
        runtime.wake.set()
        if runtime.task is None or runtime.task.done():
            runtime.task = asyncio.create_task(_drain_reviews(path, runtime), name=f"background-review-{path.name}")
            runtime.task.add_done_callback(lambda task, key=path: _review_task_done(key, task))
    except Exception:
        logger.warning("Failed to queue background review for %s", anima_dir, exc_info=True)


def _review_task_done(path: Path, task: asyncio.Task[None]) -> None:
    runtime = _RUNTIMES.get(path)
    if runtime is not None and runtime.task is task:
        runtime.task = None
    if not task.cancelled():
        try:
            task.result()
        except Exception:
            logger.warning("Background review worker failed for %s", path.name, exc_info=True)


def _review_config(anima_dir: Path) -> Any:
    config = load_config()
    settings = config.background_review
    anima_settings = config.animas.get(anima_dir.name)
    if not settings.enabled or (anima_settings and anima_settings.background_review_enabled is False):
        return None
    return settings


def _state_path(anima_dir: Path) -> Path:
    return Path(anima_dir) / "state" / _STATE_FILENAME


def _load_state(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    atomic_write_json(path, state)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now_local().tzinfo)
    return parsed


def _review_delay(state: dict[str, Any], settings: Any) -> float:
    now = now_local()
    today = today_local().isoformat()
    if state.get("daily_date") != today:
        state["daily_date"] = today
        state["daily_count"] = 0
    if int(state.get("daily_count", 0) or 0) >= settings.max_per_day:
        tomorrow = datetime.combine(now.date() + timedelta(days=1), time.min, tzinfo=now.tzinfo)
        return max(1.0, (tomorrow - now).total_seconds())

    last_attempt = _parse_datetime(state.get("last_attempt_at")) or _parse_datetime(state.get("last_review_at"))
    if last_attempt is None:
        return 0.0
    due_at = last_attempt + timedelta(minutes=settings.min_interval_minutes)
    return max(0.0, (due_at - now).total_seconds())


async def _drain_reviews(anima_dir: Path, runtime: _ReviewRuntime) -> None:
    state_path = _state_path(anima_dir)
    state = _load_state(state_path)
    try:
        while True:
            settings = _review_config(anima_dir)
            if settings is None:
                runtime.pending_triggers.clear()
                runtime.user_turn_delta = 0
                return

            _consume_deferred_requests(anima_dir, runtime)
            incoming = runtime.pending_triggers[:]
            runtime.pending_triggers.clear()
            user_turn_delta = runtime.user_turn_delta
            runtime.user_turn_delta = 0
            runtime.wake.clear()
            pending = state.setdefault("pending_triggers", [])
            if not isinstance(pending, list):
                pending = state["pending_triggers"] = []
            pending.extend(item for item in incoming if isinstance(item, str) and item not in pending)

            if user_turn_delta:
                turn_count = int(state.get("chat_user_turns", 0) or 0) + user_turn_delta
                if turn_count >= settings.chat_every_user_turns:
                    pending.append("chat_user_turns")
                    turn_count %= settings.chat_every_user_turns
                state["chat_user_turns"] = turn_count

            if pending and not state.get("pending_since"):
                state["pending_since"] = now_local().isoformat()
            if not pending:
                _save_state(state_path, state)
                return

            delay = _review_delay(state, settings)
            _save_state(state_path, state)
            if delay > 0:
                try:
                    await asyncio.wait_for(runtime.wake.wait(), timeout=delay)
                except TimeoutError:
                    pass
                continue

            triggers = list(dict.fromkeys(str(item) for item in pending))
            trigger = "+".join(triggers)
            since = _parse_datetime(state.get("last_review_at"))
            attempt_at = now_local()
            state["last_attempt_at"] = attempt_at.isoformat()
            state["daily_count"] = int(state.get("daily_count", 0) or 0) + 1
            state["daily_date"] = today_local().isoformat()
            _save_state(state_path, state)

            success = False
            try:
                success = await perform_background_review(anima_dir, trigger, since=since, settings=settings)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Background review failed for anima=%s trigger=%s error=%s",
                    anima_dir.name,
                    trigger,
                    type(exc).__name__,
                )

            if success:
                state["last_review_at"] = attempt_at.isoformat()
                state["pending_triggers"] = []
                state.pop("pending_since", None)
                _save_state(state_path, state)
            else:
                # Keep the trigger durable; the minimum interval prevents a hot retry loop.
                _save_state(state_path, state)
                delay = _review_delay(state, settings)
                if delay > 0:
                    try:
                        await asyncio.wait_for(runtime.wake.wait(), timeout=delay)
                    except TimeoutError:
                        pass
    except asyncio.CancelledError:
        # The persisted pending trigger list survives process shutdown.
        raise
    except Exception:
        logger.warning("Background review queue failed for anima=%s", anima_dir.name, exc_info=True)


def _utf8_prefix(text: str, byte_limit: int) -> str:
    if byte_limit <= 0:
        return ""
    return text.encode("utf-8")[:byte_limit].decode("utf-8", errors="ignore")


def _entry_line(entry: Any) -> str:
    data = {
        "ts": entry.ts,
        "type": entry.type,
        "from": entry.from_person,
        "to": entry.to_person,
        "channel": entry.channel,
        "tool": entry.tool,
        "summary": entry.summary,
        "content": entry.content,
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _collect_activity(anima_dir: Path, since: datetime | None, *, max_entries: int = 2000) -> list[Any]:
    from core.activity.logger import ActivityLogger

    days = 2
    if since is not None:
        days = min(90, max(2, (today_local() - since.date()).days + 1))
    entries = ActivityLogger(anima_dir).recent(days=days, limit=max_entries)
    if since is not None:
        entries = [entry for entry in entries if (_parse_datetime(entry.ts) or since) > since]
    return [entry for entry in entries if entry.type != "background_review"]


def _related_people(entries: list[Any], anima_name: str) -> list[str]:
    names: list[str] = []
    for entry in reversed(entries):
        # Inbox batches record several senders as one comma-separated field.
        candidates = [
            part for field_value in (entry.from_person, entry.to_person) for part in str(field_value or "").split(",")
        ]
        for candidate in candidates:
            name = candidate.strip()
            if not name or name == anima_name or normalize_peer_name(name) == normalize_peer_name(anima_name):
                continue
            if not normalize_peer_name(name):
                continue
            if name not in names:
                names.append(name)
            if len(names) >= _MAX_RELATED_PEERS:
                return names
    return names


def _build_prompt(
    anima_dir: Path,
    trigger: str,
    entries: list[Any],
    memory: Any,
    settings: Any,
) -> str:
    knowledge_names = memory.list_knowledge_files()[:_MAX_KNOWLEDGE_NAMES]
    peer_lines: list[str] = []
    for name in _related_people(entries, anima_dir.name):
        # List every related person so a first peer note can be written.
        profile = memory.read_peer_profile(name, max_chars=settings.peer_profile_max_chars)
        peer_lines.append(f"### {name}\n{profile or '(no notes yet)'}")

    def _empty_prompt() -> str:
        knowledge_files = "\n".join(f"- {name[:100]}" for name in knowledge_names) or "(none)"
        peer_profiles = "\n\n".join(peer_lines) or "(none)"
        return load_prompt(
            "memory/background_review",
            activity="",
            anima_name=anima_dir.name,
            trigger=trigger,
            knowledge_files=knowledge_files,
            peer_profiles=peer_profiles,
        )

    empty_prompt = _empty_prompt()
    while len(empty_prompt.encode("utf-8")) > settings.max_input_bytes and peer_lines:
        peer_lines.pop()
        empty_prompt = _empty_prompt()
    while len(empty_prompt.encode("utf-8")) > settings.max_input_bytes and knowledge_names:
        knowledge_names.pop()
        empty_prompt = _empty_prompt()
    activity_budget = max(0, settings.max_input_bytes - len(empty_prompt.encode("utf-8")))
    selected_lines: list[str] = []
    for entry in reversed(entries):
        line = _entry_line(entry)
        separator_bytes = 1 if selected_lines else 0
        remaining = activity_budget - sum(len(item.encode("utf-8")) for item in selected_lines) - separator_bytes
        if remaining <= 0:
            break
        line_bytes = len(line.encode("utf-8"))
        if line_bytes <= remaining:
            selected_lines.append(line)
            continue
        clipped = _utf8_prefix(line, remaining)
        if clipped:
            selected_lines.append(clipped)
        break
    activity_text = "\n".join(selected_lines)
    if not activity_text and len("(no activity entries)") <= activity_budget:
        activity_text = "(no activity entries)"
    prompt = load_prompt(
        "memory/background_review",
        activity=activity_text,
        anima_name=anima_dir.name,
        trigger=trigger,
        knowledge_files="\n".join(f"- {name[:100]}" for name in knowledge_names) or "(none)",
        peer_profiles="\n\n".join(peer_lines) or "(none)",
    )
    if len(prompt.encode("utf-8")) > settings.max_input_bytes:
        prompt = _utf8_prefix(prompt, settings.max_input_bytes)
    return prompt


def _parse_operations(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            value = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    operations = value.get("operations", []) if isinstance(value, dict) else []
    if not isinstance(operations, list):
        return []
    return [operation for operation in operations if isinstance(operation, dict)]


def _apply_operations(
    memory: Any,
    anima_dir: Path,
    operations: list[dict[str, Any]],
    allowed_peers: list[str],
    settings: Any,
) -> int:
    from core.time_utils import now_local

    written = 0
    allowed_peer_keys = {normalize_peer_name(name): name for name in allowed_peers}
    anima_root = anima_dir.resolve()
    knowledge_root = (anima_root / "knowledge").resolve()
    if not knowledge_root.is_relative_to(anima_root):
        logger.warning("Background review knowledge path escapes anima directory: %s", anima_dir.name)
        return 0
    for operation in operations:
        if written >= settings.max_writes:
            break
        op = operation.get("op")
        if op == "none":
            continue
        if op == "knowledge_upsert":
            requested = str(operation.get("path") or "").strip()
            if not requested or Path(requested).name != requested or "/" in requested or "\\" in requested:
                continue
            filename = requested if requested.endswith(".md") else f"{requested}.md"
            if not re.fullmatch(r"[\w.-]{1,120}\.md", filename, flags=re.UNICODE) or filename in {".md", "..md"}:
                continue
            candidate = knowledge_root / filename
            if candidate.is_symlink():
                continue
            target = candidate.resolve()
            if not target.is_relative_to(knowledge_root):
                continue
            content = str(operation.get("content") or "").strip()
            if not content:
                continue
            existing = memory.read_knowledge_content(target) if target.exists() else ""
            today = today_local().isoformat()
            updated = f"{existing.rstrip()}\n\n## {today}\n\n{content}" if existing else content
            metadata = memory.read_knowledge_metadata(target) if target.exists() else {}
            metadata.setdefault("confidence", 0.5)
            metadata.setdefault("created_at", now_local().isoformat())
            metadata.setdefault("source_episodes", 0)
            metadata.setdefault("auto_consolidated", False)
            metadata["updated_at"] = now_local().isoformat()
            metadata["version"] = int(metadata.get("version", 1) or 1) + (1 if existing else 0)
            memory.write_knowledge_with_meta(target, updated, metadata)
            memory.index_knowledge_file(target, origin="background_review")
            written += 1
        elif op == "peer_update":
            peer = str(operation.get("peer") or "").strip()
            peer_key = normalize_peer_name(peer)
            if not peer_key or peer_key not in allowed_peer_keys:
                continue
            content = str(operation.get("content") or "").strip()
            if not content:
                continue
            memory.write_peer_profile(
                allowed_peer_keys[peer_key],
                content,
                max_chars=settings.peer_profile_max_chars,
            )
            written += 1
    return written


async def _run_model(prompt: str, anima_dir: Path, memory: Any, config: Any) -> tuple[str | None, str]:
    from core.anima.lifecycle import _complete_episode_prompt, _episode_summary_model_configs
    from core.config.helper_models import resolve_helper_model

    base_config = memory.read_model_config()
    helper_model = resolve_helper_model("episode_summary", anima_dir, config=config)
    model_configs = _episode_summary_model_configs(
        base_config,
        helper_model.model,
        config,
        anima_dir=anima_dir,
        helper_model=helper_model,
    )
    consolidation = getattr(config, "consolidation", None)
    legacy_max_tokens = getattr(consolidation, "episode_summary_max_output_tokens", 4096)
    raw, _reason = await _complete_episode_prompt(
        prompt,
        model_configs,
        max_output_tokens=helper_model.max_output_tokens or legacy_max_tokens,
        allow_agent_sdk_fallback=helper_model.allow_agent_sdk_fallback,
    )
    return raw, helper_model.model


async def perform_background_review(
    anima_dir: Path,
    trigger: str,
    *,
    since: datetime | None,
    settings: Any,
) -> bool:
    """Run one bounded review; failures are recorded and never escape to callers."""
    from core.activity.logger import ActivityLogger
    from core.memory.manager import MemoryManager

    memory = MemoryManager(anima_dir)
    entries = _collect_activity(anima_dir, since)
    prompt = _build_prompt(anima_dir, trigger, entries, memory, settings)
    input_bytes = len(prompt.encode("utf-8"))
    operations: list[dict[str, Any]] = []
    written = 0
    model = "unavailable"
    success = True
    try:
        if entries:
            raw, model = await _run_model(prompt, anima_dir, memory, load_config())
            if not raw:
                success = False
                logger.warning("Background review LLM failed for anima=%s trigger=%s", anima_dir.name, trigger)
            else:
                operations = _parse_operations(raw)
                allowed_peers = _related_people(entries, anima_dir.name)
                written = _apply_operations(memory, anima_dir, operations, allowed_peers, settings)
    except Exception as exc:
        success = False
        logger.warning(
            "Background review failed for anima=%s trigger=%s error=%s",
            anima_dir.name,
            trigger,
            type(exc).__name__,
        )

    logger.info(
        "background_review anima=%s trigger=%s input_bytes=%d ops=%d written=%d model=%s",
        anima_dir.name,
        trigger,
        input_bytes,
        len(operations),
        written,
        model,
    )
    try:
        await ActivityLogger(anima_dir).alog(
            "background_review",
            summary=f"Background review ({trigger}): wrote {written} item(s)",
            meta={
                "trigger": trigger,
                "input_bytes": input_bytes,
                "operations": len(operations),
                "written": written,
                "model": model,
                "success": success,
            },
            safe=True,
        )
    except Exception:
        logger.warning("Failed to record background review activity for anima=%s", anima_dir.name, exc_info=True)
    return success
