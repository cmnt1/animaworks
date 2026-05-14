"""Attention policy for TaskBoard-driven prompt gates."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from core.paths import get_taskboard_db_path
from core.taskboard.models import AttentionDecision, AttentionVisibility, BoardTask, TaskBoardMetadata
from core.taskboard.store import TaskBoardStore
from core.time_utils import ensure_aware, now_local

logger = logging.getLogger("animaworks.taskboard.attention")

FAILED_REVIEW_WINDOW = timedelta(days=7)
PROMPT_REINJECTION_WINDOW = timedelta(hours=24)

_TERMINAL_STATUSES = {"done", "cancelled"}
_EXECUTION_TERMINAL_STATUSES = {"done", "cancelled", "failed"}
_SUPPRESSED_VISIBILITIES = {
    AttentionVisibility.EXPIRED,
    AttentionVisibility.ARCHIVED,
    AttentionVisibility.TOMBSTONED,
}
_TASK_REF_RE = re.compile(r"\b[A-Za-z0-9]{8,}\b")
_AW_TASK_REF_RE = re.compile(r"aw://task/([^/\s]+)/([A-Za-z0-9_-]+)")


class AttentionResolver:
    """Resolve whether TaskBoard entries may re-enter prompt context."""

    def __init__(self, store: TaskBoardStore | None = None) -> None:
        self.store = store

    def resolve_task(self, board_task: BoardTask, now: datetime | None = None) -> AttentionDecision:
        """Return a deterministic prompt decision for one projected task."""
        resolved_now = _normalize_now(now)

        if board_task.queue_missing:
            return _hidden("queue_missing")

        if self._is_expired(board_task.expires_at, resolved_now):
            self._record_visibility(board_task.anima_name, board_task.task_id, AttentionVisibility.EXPIRED)
            return _hidden("expired")

        visibility = board_task.visibility
        if visibility == AttentionVisibility.SNOOZED:
            snoozed_until = _parse_datetime(board_task.snoozed_until)
            if snoozed_until is None:
                logger.warning("Invalid snoozed_until for task %s/%s", board_task.anima_name, board_task.task_id)
                visibility = AttentionVisibility.ACTIVE
            elif snoozed_until > resolved_now:
                return _hidden("snoozed")
            else:
                visibility = AttentionVisibility.ACTIVE
                self._record_visibility(board_task.anima_name, board_task.task_id, AttentionVisibility.ACTIVE)

        if visibility in _SUPPRESSED_VISIBILITIES:
            return _hidden(visibility.value)

        if board_task.queue_status in _TERMINAL_STATUSES:
            return _hidden("terminal")

        if board_task.queue_status == "failed":
            updated_at = _parse_datetime(board_task.queue_updated_at)
            if updated_at is not None and resolved_now - updated_at <= FAILED_REVIEW_WINDOW:
                return _visible("failed_review_window")
            return _hidden("failed_stale")

        return _visible("active")

    def filter_for_priming(
        self,
        anima_name: str,
        board_tasks: list[BoardTask],
        now: datetime | None = None,
    ) -> list[BoardTask]:
        """Filter projected tasks to those allowed in prompt priming."""
        resolved_now = _normalize_now(now)
        return [
            task
            for task in board_tasks
            if task.anima_name == anima_name and self.resolve_task(task, resolved_now).visible_in_prompt
        ]

    def should_execute(
        self,
        anima_name: str,
        task_id: str,
        *,
        queue_status: str | None = None,
        now: datetime | None = None,
    ) -> AttentionDecision:
        """Return whether a runtime task may execute or be regenerated."""
        resolved_now = _normalize_now(now)
        metadata = self._get_metadata(anima_name, task_id)

        if queue_status in _EXECUTION_TERMINAL_STATUSES:
            return _hidden("terminal")

        if metadata is not None:
            if self._is_expired(metadata.expires_at, resolved_now):
                self._record_visibility(anima_name, task_id, AttentionVisibility.EXPIRED)
                return _hidden("expired")

            if metadata.visibility == AttentionVisibility.SNOOZED:
                snoozed_until = _parse_datetime(metadata.snoozed_until)
                if snoozed_until is None:
                    logger.warning("Invalid snoozed_until for metadata %s/%s", anima_name, task_id)
                elif snoozed_until > resolved_now:
                    return _hidden("snoozed")
                else:
                    self._record_visibility(anima_name, task_id, AttentionVisibility.ACTIVE)
                    return _visible("active")

            if metadata.visibility in _SUPPRESSED_VISIBILITIES:
                return _hidden(metadata.visibility.value)

        return _visible("active")

    def should_show_task_result(
        self,
        anima_name: str,
        task_id: str,
        result_mtime: float,
        now: datetime | None = None,
    ) -> bool:
        """Return whether a task_results entry may be injected into Channel E."""
        resolved_now = _normalize_now(now)
        metadata = self._get_metadata(anima_name, task_id)
        if metadata is not None:
            return not self._metadata_hidden_in_prompt(metadata, resolved_now)

        result_time = datetime.fromtimestamp(result_mtime, tz=resolved_now.tzinfo)
        return resolved_now - result_time <= PROMPT_REINJECTION_WINDOW

    def should_show_human_notify(
        self,
        anima_name: str,
        notification_key: str,
        ts: str,
        now: datetime | None = None,
    ) -> bool:
        """Return whether a human notification should be re-injected."""
        if not notification_key:
            return True

        resolved_now = _normalize_now(now)
        try:
            metadata_rows = self.store.list_metadata(anima_name=anima_name) if self.store else []
        except Exception:
            logger.debug("TaskBoard metadata unavailable for human_notify gate", exc_info=True)
            return True

        for metadata in metadata_rows:
            if metadata.notification_key != notification_key or not metadata.last_notified_at:
                continue
            last_notified_at = _parse_datetime(metadata.last_notified_at)
            if last_notified_at is not None and resolved_now - last_notified_at <= PROMPT_REINJECTION_WINDOW:
                return False

        return True

    def should_inject_current_state(self, anima_dir: Path | str, now: datetime | None = None) -> bool:
        """Return whether current_state.md is fresh enough for prompt injection."""
        resolved_now = _normalize_now(now)
        state_path = Path(anima_dir) / "state" / "current_state.md"
        try:
            if not state_path.exists():
                return True
            modified_at = datetime.fromtimestamp(state_path.stat().st_mtime, tz=resolved_now.tzinfo)
        except OSError:
            logger.debug("current_state freshness check failed", exc_info=True)
            return True
        return resolved_now - modified_at <= PROMPT_REINJECTION_WINDOW

    def filter_current_state(self, anima_dir: Path | str, state: str, now: datetime | None = None) -> str:
        """Remove lines that reference suppressed TaskBoard tasks."""
        resolved_now = _normalize_now(now)
        anima_name = Path(anima_dir).name
        try:
            metadata_rows = self.store.list_metadata() if self.store else []
        except Exception:
            logger.debug("TaskBoard metadata unavailable for current_state gate", exc_info=True)
            return state

        suppressed_refs: dict[str, set[str]] = {}
        suppressed_task_ids_for_anima: set[str] = set()
        for metadata in metadata_rows:
            if not self._metadata_hidden_in_current_state(metadata, resolved_now):
                continue
            suppressed_refs.setdefault(metadata.anima_name, set()).add(metadata.task_id)
            if metadata.anima_name == anima_name:
                suppressed_task_ids_for_anima.add(metadata.task_id)

        if not suppressed_refs:
            return state

        kept_lines = [
            line
            for line in state.splitlines()
            if not _line_references_suppressed_task(line, anima_name, suppressed_refs, suppressed_task_ids_for_anima)
        ]
        return "\n".join(kept_lines)

    def _get_metadata(self, anima_name: str, task_id: str) -> TaskBoardMetadata | None:
        if self.store is None:
            return None
        try:
            return self.store.get_metadata(anima_name, task_id)
        except Exception:
            logger.debug("TaskBoard metadata unavailable for %s/%s", anima_name, task_id, exc_info=True)
            return None

    def _metadata_hidden_in_prompt(self, metadata: TaskBoardMetadata, now: datetime) -> bool:
        if self._is_expired(metadata.expires_at, now):
            self._record_visibility(metadata.anima_name, metadata.task_id, AttentionVisibility.EXPIRED)
            return True
        if metadata.visibility == AttentionVisibility.SNOOZED:
            snoozed_until = _parse_datetime(metadata.snoozed_until)
            if snoozed_until is None:
                logger.warning("Invalid snoozed_until for metadata %s/%s", metadata.anima_name, metadata.task_id)
                return False
            if snoozed_until > now:
                return True
            self._record_visibility(metadata.anima_name, metadata.task_id, AttentionVisibility.ACTIVE)
            return False
        return metadata.visibility in _SUPPRESSED_VISIBILITIES

    def _metadata_hidden_in_current_state(self, metadata: TaskBoardMetadata, now: datetime) -> bool:
        if self._is_expired(metadata.expires_at, now):
            self._record_visibility(metadata.anima_name, metadata.task_id, AttentionVisibility.EXPIRED)
            return True
        return metadata.visibility in _SUPPRESSED_VISIBILITIES

    def _is_expired(self, expires_at: str | None, now: datetime) -> bool:
        if not expires_at:
            return False
        parsed = _parse_datetime(expires_at)
        if parsed is None:
            logger.warning("Invalid expires_at value: %s", expires_at)
            return False
        return parsed <= now

    def _record_visibility(self, anima_name: str, task_id: str, visibility: AttentionVisibility) -> None:
        if self.store is None:
            return
        try:
            self.store.upsert_metadata(
                anima_name=anima_name,
                task_id=task_id,
                actor="attention_resolver",
                visibility=visibility,
            )
        except Exception:
            logger.debug("Failed to record TaskBoard visibility change", exc_info=True)


def notification_key_for(subject: str, body: str) -> str:
    """Return the fallback human notification key."""
    return hashlib.sha256(f"{subject}\n{body}".encode()).hexdigest()


def taskboard_db_path_for_anima(anima_dir: Path | str) -> Path:
    """Resolve the shared TaskBoard DB path for a per-Anima directory."""
    resolved = Path(anima_dir)
    if resolved.parent.name == "animas":
        return resolved.parent.parent / "shared" / "taskboard.sqlite3"
    return get_taskboard_db_path()


def resolver_for_anima_dir(anima_dir: Path | str) -> AttentionResolver:
    """Create a resolver using the data directory that owns anima_dir."""
    return AttentionResolver(TaskBoardStore(taskboard_db_path_for_anima(anima_dir)))


def _visible(reason: str) -> AttentionDecision:
    return AttentionDecision(visible_in_prompt=True, executable=True, notify_allowed=True, reason=reason)


def _hidden(reason: str) -> AttentionDecision:
    return AttentionDecision(visible_in_prompt=False, executable=False, notify_allowed=False, reason=reason)


def _normalize_now(now: datetime | None) -> datetime:
    return ensure_aware(now or now_local())


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(value))
    except (TypeError, ValueError):
        return None


def _line_references_suppressed_task(
    line: str,
    anima_name: str,
    suppressed_refs: dict[str, set[str]],
    suppressed_task_ids_for_anima: set[str],
) -> bool:
    for ref_anima, ref_task_id in _AW_TASK_REF_RE.findall(line):
        if _token_matches_any_task_id(ref_task_id, suppressed_refs.get(ref_anima, set())):
            return True

    for token in _TASK_REF_RE.findall(line):
        if _token_matches_any_task_id(token, suppressed_task_ids_for_anima) or _token_matches_any_task_id(
            token,
            suppressed_refs.get(anima_name, set()),
        ):
            return True
    return False


def _token_matches_any_task_id(token: str, task_ids: set[str]) -> bool:
    return any(token == task_id or token in task_id or task_id in token for task_id in task_ids)
