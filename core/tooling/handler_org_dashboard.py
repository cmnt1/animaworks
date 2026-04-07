from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""DashboardMixin — org_dashboard and audit_subordinate."""

import json as _json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.i18n import t
from core.tooling.org_helpers import OrgHelpersMixin

if TYPE_CHECKING:
    from core.memory.activity import ActivityLogger

logger = logging.getLogger("animaworks.tool_handler")


class DashboardMixin(OrgHelpersMixin):
    """Mixin for org_dashboard and audit_subordinate tools."""

    # Declared for type-checker visibility
    _anima_dir: Path
    _anima_name: str
    _activity: ActivityLogger
    _process_supervisor: Any

    def _render_tree(
        self,
        by_supervisor: dict[str, list[dict[str, Any]]],
        lines: list[str],
        parent: str,
        indent: int = 0,
    ) -> None:
        """Render org tree recursively into lines."""
        children = by_supervisor.get(parent, [])
        for child in children:
            prefix = "  " * indent + "├─ " if indent > 0 else ""
            status_icon = (
                "🟢"
                if child["process_status"] in ("running", "enabled")
                else "🔴"
                if child["process_status"] == "disabled"
                else "⚪"
            )
            line = f"{prefix}{status_icon} **{child['name']}** [{child['process_status']}]"
            line += " | " + t("handler.dashboard_last", activity=child["last_activity"])
            line += " | " + t("handler.dashboard_tasks", count=child["active_tasks"])
            none_str = t("handler.current_state_none")
            if child["current_state"] != none_str:
                line += (
                    "\n" + "  " * (indent + 1) + "└ " + t("handler.dashboard_working_on", task=child["current_state"])
                )
            lines.append(line)
            self._render_tree(by_supervisor, lines, child["name"], indent + 1)

    def _handle_org_dashboard(self, args: dict[str, Any]) -> str:
        """Show organization dashboard with all descendants' status."""
        descendants = self._get_all_descendants()
        if not descendants:
            return t("handler.no_subordinates")

        from core.config.models import load_config
        from core.paths import get_animas_dir

        animas_dir = get_animas_dir()
        config = load_config()

        entries: list[dict[str, Any]] = []
        for name in descendants:
            desc_dir = animas_dir / name
            entry: dict[str, Any] = {"name": name, "supervisor": ""}

            cfg = config.animas.get(name)
            if cfg:
                entry["supervisor"] = cfg.supervisor or ""

            if self._process_supervisor:
                try:
                    ps = self._process_supervisor.get_process_status(name)
                    entry["process_status"] = ps.get("status", "unknown") if isinstance(ps, dict) else str(ps)
                except Exception:
                    entry["process_status"] = "unknown"
            else:
                status_file = desc_dir / "status.json"
                if status_file.exists():
                    try:
                        status_data = _json.loads(status_file.read_text(encoding="utf-8"))
                        entry["process_status"] = "enabled" if status_data.get("enabled", True) else "disabled"
                    except Exception:
                        entry["process_status"] = "unknown"
                else:
                    entry["process_status"] = "unknown"

            try:
                recent = self._read_recent_activity(desc_dir, limit=1)
                if recent:
                    entry["last_activity"] = recent[-1].ts
                else:
                    entry["last_activity"] = t("handler.last_activity_none")
            except Exception:
                entry["last_activity"] = t("handler.last_activity_unknown")

            task_file = desc_dir / "state" / "current_state.md"
            if task_file.exists():
                try:
                    task_text = task_file.read_text(encoding="utf-8").strip()
                    entry["current_state"] = task_text[:100] if task_text else t("handler.current_state_none")
                except Exception:
                    entry["current_state"] = t("handler.current_state_unreadable")
            else:
                entry["current_state"] = t("handler.current_state_none")

            try:
                from core.memory.task_queue import TaskQueueManager

                tqm = TaskQueueManager(desc_dir)
                active = tqm.get_all_active()
                entry["active_tasks"] = len(active)
            except Exception:
                entry["active_tasks"] = 0

            entries.append(entry)

        lines: list[str] = [t("handler.org_dashboard_title"), ""]
        by_supervisor: dict[str, list[dict[str, Any]]] = {}
        for e in entries:
            sup = e.get("supervisor", "")
            by_supervisor.setdefault(sup, []).append(e)

        self._render_tree(by_supervisor, lines, self._anima_name)

        self._activity.log(
            "tool_use",
            tool="org_dashboard",
            summary=t("handler.dashboard_summary", count=len(descendants)),
        )

        return "\n".join(lines)

    def _handle_audit_subordinate(self, args: dict[str, Any]) -> str:
        """Audit subordinate behavior from activity logs."""
        from core.memory.audit import AuditAggregator
        from core.paths import get_animas_dir

        target_name = args.get("name")
        # Backward compat: accept legacy "days" param, convert to hours
        raw_hours = args.get("hours")
        if raw_hours is None and "days" in args:
            raw_hours = args["days"] * 24
        if raw_hours is None:
            raw_hours = 24
        hours = min(max(raw_hours, 1), 168)
        direct_only = args.get("direct_only", False)

        since = self._parse_since(args.get("since"))

        if target_name:
            err = self._check_descendant(target_name)
            if err:
                return err
            targets = [target_name]
        else:
            if direct_only:
                targets = self._get_direct_subordinates()
            else:
                targets = self._get_all_descendants()
            if not targets:
                return t("handler.no_subordinates")

        animas_dir = get_animas_dir()
        is_batch = len(targets) > 1

        if is_batch:
            result = AuditAggregator.generate_merged_timeline(
                [animas_dir / n for n in targets],
                hours=hours,
                since=since,
            )
        else:
            agg = AuditAggregator(animas_dir / targets[0])
            result = agg.generate_report(hours=hours, since=since)

        self._activity.log(
            "tool_use",
            tool="audit_subordinate",
            summary=t(
                "handler.audit_log_summary",
                target_name=target_name or f"batch({len(targets)})",
                hours=hours,
            ),
            meta={"targets": targets, "hours": hours, "since": args.get("since")},
        )

        return result
