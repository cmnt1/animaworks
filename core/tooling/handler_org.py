from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""OrgToolsMixin — anima creation, supervisor tools, org dashboard, delegation."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.tooling.handler_create_anima import CreateAnimaMixin
from core.tooling.handler_delegation import DelegationMixin
from core.tooling.handler_org_dashboard import DashboardMixin
from core.tooling.handler_subordinate_control import SubordinateControlMixin

if TYPE_CHECKING:
    from core.memory.activity.logger import ActivityLogger
    from core.messenger import Messenger


class OrgToolsMixin(DashboardMixin, DelegationMixin, SubordinateControlMixin, CreateAnimaMixin):
    """Organization management: anima creation, supervisor tools, dashboard, delegation.

    Composes:
    - DashboardMixin: org_dashboard, audit_subordinate
    - DelegationMixin: delegate_task, task_tracker
    - SubordinateControlMixin: disable/enable/set_model/restart/ping/read_state
    - CreateAnimaMixin: create_anima
    """

    # Declared for type-checker visibility (used by ToolHandler and mixins)
    _anima_dir: Path
    _anima_name: str
    _activity: ActivityLogger
    _process_supervisor: Any
    _messenger: Messenger | None
    _session_origin: str
    _session_origin_chain: list[str]
