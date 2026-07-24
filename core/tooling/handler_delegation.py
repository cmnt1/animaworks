from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""DelegationMixin — delegate_task and task_tracker."""

import json as _json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.exceptions import TaskPersistenceError
from core.i18n import t
from core.memory._io import atomic_write_text
from core.tooling.handler_base import _error_result, build_outgoing_origin_chain
from core.tooling.org_helpers import OrgHelpersMixin

if TYPE_CHECKING:
    from core.memory.activity import ActivityLogger
    from core.messenger import Messenger

logger = logging.getLogger("animaworks.tool_handler")


def _server_base_url() -> str:
    return os.environ.get("ANIMAWORKS_SERVER_URL", "http://localhost:18500").rstrip("/")


def _record_taskboard_delegation(
    *,
    delegated_to: str,
    delegated_task_id: str,
    delegator: str,
    tracking_task_id: str | None = None,
) -> None:
    """Record delegation rows in TaskBoard before legacy queue compatibility writes."""
    from core.taskboard.models import AttentionVisibility, BoardColumn
    from core.taskboard.store import TaskBoardStore

    store = TaskBoardStore()
    store.upsert_metadata(
        anima_name=delegated_to,
        task_id=delegated_task_id,
        actor=delegator,
        event_type="metadata_upserted",
        visibility=AttentionVisibility.ACTIVE,
        column=BoardColumn.TODO,
        source_ref=f"task_queue:{delegated_to}:{delegated_task_id}",
    )
    if tracking_task_id:
        store.upsert_metadata(
            anima_name=delegator,
            task_id=tracking_task_id,
            actor=delegator,
            event_type="metadata_upserted",
            visibility=AttentionVisibility.ACTIVE,
            column=BoardColumn.WAITING,
            source_ref=f"task_queue:{delegator}:{tracking_task_id}",
        )


class DelegationMixin(OrgHelpersMixin):
    """Mixin for delegate_task and task_tracker tools."""

    # Declared for type-checker visibility
    _anima_dir: Path
    _anima_name: str
    _activity: ActivityLogger
    _messenger: Messenger | None
    _session_origin: str
    _session_origin_chain: list[str]
    _current_discord_origin: dict[str, str]

    def _persist_delegation_via_server(
        self,
        *,
        target_name: str,
        instruction: str,
        summary: str,
        deadline: str,
        sub_task_id: str,
        tracking_task_id: str,
        workspace: str,
        persist_sub: bool,
        persist_tracking: bool,
        persist_pending: bool,
    ) -> str | None:
        """Persist delegation via /api/internal/delegate-task when local FS is read-only.

        Returns None on success, or an error string on failure.
        """
        try:
            import httpx
        except ImportError as exc:
            return f"httpx unavailable: {exc}"

        payload: dict[str, Any] = {
            "delegator": self._anima_name,
            "target": target_name,
            "instruction": instruction,
            "summary": summary,
            "deadline": deadline,
            "sub_task_id": sub_task_id,
            "tracking_task_id": tracking_task_id,
            "workspace": workspace,
            "persist_sub": persist_sub,
            "persist_tracking": persist_tracking,
            "persist_pending": persist_pending,
        }
        try:
            resp = httpx.post(
                f"{_server_base_url()}/api/internal/delegate-task",
                json=payload,
                timeout=30.0,
            )
        except Exception as exc:
            return f"server unreachable: {exc}"

        if resp.status_code >= 400:
            detail = _extract_detail(resp)
            return f"HTTP {resp.status_code}: {detail}"

        try:
            data = resp.json()
        except Exception:
            data = {}
        if not isinstance(data, dict) or not data.get("ok"):
            return f"unexpected response: {data!r}"
        return None

    def _handle_delegate_task(self, args: dict[str, Any]) -> str:
        """Delegate a task to a direct subordinate."""
        from core.tooling.org_helpers import resolve_anima_name

        target_name = resolve_anima_name(args.get("name", ""))
        instruction = args.get("instruction", "")
        summary = args.get("summary", "") or instruction[:100]
        deadline = args.get("deadline", "")

        workspace_raw = args.get("workspace", "")
        resolved_wd = ""
        if workspace_raw:
            try:
                from core.workspace import resolve_workspace

                resolved_wd = str(resolve_workspace(workspace_raw))
            except ValueError as e:
                return _error_result("InvalidArguments", f"Workspace resolution failed: {e}")

        if not target_name:
            return _error_result("InvalidArguments", "name is required")
        if not instruction:
            return _error_result("InvalidArguments", "instruction is required")
        if not deadline:
            return _error_result(
                "InvalidArguments",
                "deadline is required. Use relative format ('30m', '2h', '1d') or ISO8601.",
            )

        err = self._check_subordinate(target_name)
        if err:
            return err

        from core.company import check_company_boundary
        from core.memory.task_queue import TaskQueueManager
        from core.paths import get_animas_dir
        from core.urgent import add_urgent, is_urgent_active

        animas_dir = get_animas_dir()
        boundary = check_company_boundary(
            self._anima_name,
            target_name,
            animas_dir=animas_dir,
        )
        if boundary.cross_company:
            if boundary.resolved_via == "fail_closed":
                return t("handler.company_boundary_unverifiable")
            return t(
                "handler.cross_company_delegation_blocked",
                display_name=boundary.display_name,
            )

        target_dir = animas_dir / target_name

        try:
            from core.config.model_config import load_model_config
            from core.task_granularity import assess_task_granularity, capability_for_model

            target_config = load_model_config(target_dir)
            target_model = target_config.background_model or target_config.model
            target_capability = capability_for_model(target_model)
            lightweight_subtask_limit = 1 if target_capability != "high" else None
            decision = assess_task_granularity(
                model_name=target_model,
                title=summary,
                description=instruction,
                allow_multistage=bool(args.get("allow_multistage")),
                honor_allow_multistage=target_capability == "high",
                max_phases=lightweight_subtask_limit,
            )
            if not decision.allowed:
                return _error_result(
                    "TaskTooBroadForModel",
                    (
                        f"{decision.guidance} "
                        "For lightweight or medium subordinate models, delegate one concrete phase at a time. "
                        f"Target={target_name}, model={decision.model_name}, capability={decision.capability}."
                    ),
                )
        except Exception:
            logger.debug(
                "delegate_task granularity preflight skipped for %s",
                target_name,
                exc_info=True,
            )

        # Urgent-mode cascade (Phase C-4): if the delegator is currently in
        # urgent mode, propagate priority=urgent to the subordinate so all
        # throttles bypass there too.  This recurses via further delegation.
        delegator_urgent = is_urgent_active(self._anima_dir)
        cascade_priority = "urgent" if delegator_urgent else "normal"

        sub_task_id = uuid.uuid4().hex[:12]
        tracking_task_id = uuid.uuid4().hex[:12]
        sub_tqm = TaskQueueManager(target_dir)
        own_tqm = TaskQueueManager(self._anima_dir)

        persisted_sub = persisted_tracking = persisted_pending = False
        used_server_fallback = False
        try:
            sub_tqm.add_task(
                source="anima",
                original_instruction=instruction,
                assignee=target_name,
                summary=summary,
                deadline=deadline,
                relay_chain=[self._anima_name],
                priority=cascade_priority,
                task_id=sub_task_id,
            )
            persisted_sub = True

            # Register urgent mode before publishing the pending descriptor so
            # the subordinate scheduler sees the bypass immediately.
            if delegator_urgent:
                try:
                    add_urgent(
                        target_dir,
                        sub_task_id,
                        note=f"delegated from {self._anima_name}",
                    )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "urgent cascade registration failed for %s -> %s",
                        self._anima_name,
                        target_name,
                        exc_info=True,
                    )

            task_desc = {
                "task_type": "llm",
                "task_id": sub_task_id,
                "title": summary,
                "description": instruction,
                "context": "",
                "acceptance_criteria": [],
                "constraints": [],
                "file_paths": [],
                "allow_multistage": bool(args.get("allow_multistage")),
                "submitted_by": self._anima_name,
                "submitted_at": datetime.now(UTC).isoformat(),
                "reply_to": self._anima_name,
                "source": "delegation",
                "working_directory": resolved_wd,
                "priority": cascade_priority,
            }
            sub_tqm.update_meta(sub_task_id, {"task_desc": task_desc})

            tracking_meta: dict[str, Any] = {
                "delegated_to": target_name,
                "delegated_task_id": sub_task_id,
            }
            discord_origin = getattr(self, "_current_discord_origin", {}) or {}
            if discord_origin.get("channel_id"):
                tracking_meta["discord_origin_channel_id"] = discord_origin["channel_id"]
                tracking_meta["discord_origin_thread_ts"] = discord_origin.get("thread_ts", "")
                tracking_meta["discord_origin_user_id"] = discord_origin.get("user_id", "")

            own_tqm.add_delegated_task(
                original_instruction=instruction,
                assignee=target_name,
                summary=t("handler.delegation_summary", summary=summary),
                deadline=deadline,
                relay_chain=[self._anima_name, target_name],
                task_id=tracking_task_id,
                meta=tracking_meta,
                priority=cascade_priority,
            )
            persisted_tracking = True

            pending_dir = target_dir / "state" / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_text(
                pending_dir / f"{sub_task_id}.json",
                _json.dumps(task_desc, ensure_ascii=False, indent=2) + "\n",
            )
            persisted_pending = True
        except ValueError as e:
            return _error_result("InvalidArguments", str(e))
        except (OSError, TaskPersistenceError) as e:
            # sandbox EROFS/EACCES: fall back to server internal API.
            # TaskQueueManager wraps OSError in TaskPersistenceError (not an
            # OSError subclass), so both must be caught here.
            fb_err = self._persist_delegation_via_server(
                target_name=target_name,
                instruction=instruction,
                summary=summary,
                deadline=deadline,
                sub_task_id=sub_task_id,
                tracking_task_id=tracking_task_id,
                workspace=resolved_wd,
                persist_sub=not persisted_sub,
                persist_tracking=not persisted_tracking,
                persist_pending=not persisted_pending,
            )
            if fb_err is not None:
                logger.error(
                    "delegate_task persistence failed (direct=%s, fallback=%s)",
                    e,
                    fb_err,
                )
                return _error_result(
                    "PersistenceFailed",
                    f"Failed to persist task to subordinate queue: {e}; server fallback failed: {fb_err}",
                )
            used_server_fallback = True
            logger.info(
                "delegate_task: persisted via server API (EROFS fallback) "
                "delegator=%s target=%s sub_task_id=%s tracking_task_id=%s "
                "persist_sub=%s persist_tracking=%s persist_pending=%s",
                self._anima_name,
                target_name,
                sub_task_id,
                tracking_task_id,
                not persisted_sub,
                not persisted_tracking,
                not persisted_pending,
            )
        except Exception as e:
            logger.error("Task persistence failed in delegate_task: %s", e)
            return _error_result(
                "PersistenceFailed",
                f"Failed to persist task to subordinate queue: {e}",
            )

        if not used_server_fallback:
            try:
                _record_taskboard_delegation(
                    delegated_to=target_name,
                    delegated_task_id=sub_task_id,
                    delegator=self._anima_name,
                    tracking_task_id=tracking_task_id,
                )
            except Exception as e:
                logger.warning(
                    "TaskBoard write failed in delegate_task; queue entries remain authoritative: %s",
                    e,
                )

        # Build outgoing origin_chain (provenance Phase 3)
        outgoing_chain = build_outgoing_origin_chain(
            self._session_origin,
            self._session_origin_chain,
        )

        dm_result = ""
        if self._messenger:
            try:
                self._messenger.send(
                    to=target_name,
                    content=t(
                        "handler.delegation_dm_content",
                        instruction=instruction,
                        deadline=deadline,
                        task_id=sub_task_id,
                    ),
                    intent="delegation",
                    origin_chain=outgoing_chain,
                    meta={"task_id": sub_task_id},
                )
                dm_result = t("handler.dm_sent")
            except Exception as e:
                dm_result = t("handler.dm_send_failed", e=e)
                logger.warning("delegate_task DM failed: %s -> %s: %s", self._anima_name, target_name, e)
        else:
            dm_result = t("handler.messenger_not_set")

        process_warning = ""
        try:
            from core.paths import get_data_dir

            sock = get_data_dir() / "run" / "sockets" / f"{target_name}.sock"
            if not sock.exists():
                status_file = target_dir / "status.json"
                if status_file.exists():
                    sdata = _json.loads(status_file.read_text(encoding="utf-8"))
                    if not sdata.get("enabled", True):
                        process_warning = t("handler.subordinate_disabled_warning", target_name=target_name)
        except Exception:
            logger.debug("Failed to check subordinate process status for %s", target_name, exc_info=True)

        self._activity.log(
            "tool_use",
            tool="delegate_task",
            summary=t("handler.delegate_log", target_name=target_name, summary=summary[:80]),
            meta={
                "target": target_name,
                "own_task_id": tracking_task_id,
                "sub_task_id": sub_task_id,
            },
        )

        result = t(
            "handler.delegated_success",
            target_name=target_name,
            sub_id=sub_task_id,
            own_id=tracking_task_id,
            dm_result=dm_result,
        )
        return result + process_warning

    def _handle_task_tracker(self, args: dict[str, Any]) -> str:
        """Track progress of delegated tasks."""
        status_filter = args.get("status", "active")

        from core.memory.task_queue import TaskQueueManager
        from core.paths import get_animas_dir

        own_tqm = TaskQueueManager(self._anima_dir)
        delegated = own_tqm.get_delegated_tasks()

        if not delegated:
            return t("handler.no_delegated_tasks")

        animas_dir = get_animas_dir()
        results: list[dict[str, Any]] = []

        for task in delegated:
            meta = task.meta or {}
            delegated_to = meta.get("delegated_to", "")
            delegated_task_id = meta.get("delegated_task_id", "")

            entry: dict[str, Any] = {
                "my_task_id": task.task_id,
                "delegated_to": delegated_to,
                "summary": task.summary,
                "delegated_at": task.ts,
                "deadline": task.deadline or "",
                "subordinate_status": "unknown",
                "last_updated": "",
            }

            if delegated_to and delegated_task_id:
                target_dir = animas_dir / delegated_to
                try:
                    sub_tqm = TaskQueueManager(target_dir)
                    sub_task = sub_tqm.get_task_by_id(delegated_task_id)
                    if sub_task:
                        entry["subordinate_status"] = sub_task.status
                        entry["last_updated"] = sub_task.updated_at
                except Exception:
                    entry["subordinate_status"] = "unknown"

            sub_status = entry["subordinate_status"]
            _terminal = {"done", "cancelled", "failed"}
            if status_filter == "active" and sub_status in _terminal:
                continue
            if status_filter == "completed" and sub_status not in _terminal:
                continue

            results.append(entry)

        self._activity.log(
            "tool_use",
            tool="task_tracker",
            summary=t("handler.task_tracker_log", status=status_filter, count=len(results)),
        )

        if not results:
            return t("handler.no_matching_delegated", status=status_filter)

        return _json.dumps(results, ensure_ascii=False, indent=2)


def _extract_detail(resp: Any) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            detail = data.get("detail", data)
            return str(detail)
    except Exception:
        logger.debug(
            "delegate_task: failed to parse error response JSON",
            exc_info=True,
        )
    return getattr(resp, "text", None) or f"HTTP {getattr(resp, 'status_code', '?')}"
