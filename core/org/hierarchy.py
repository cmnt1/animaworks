from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Pure helpers for supervisor-tree authorization."""

from collections import deque
from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config.schemas import AnimaModelConfig


def is_direct_subordinate(
    animas_cfg: Mapping[str, AnimaModelConfig],
    supervisor: str,
    target: str,
) -> bool:
    """Return whether *target* is a distinct direct subordinate of *supervisor*."""
    target_cfg = animas_cfg.get(target)
    return target != supervisor and target_cfg is not None and target_cfg.supervisor == supervisor


def descendants_of(animas_cfg: Mapping[str, AnimaModelConfig], root: str) -> set[str]:
    """Return all descendants reachable through supervisor links, safely handling cycles."""
    descendants: set[str] = set()
    visited = {root}
    queue = deque(name for name, cfg in animas_cfg.items() if cfg.supervisor == root)
    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        descendants.add(current)
        queue.extend(name for name, cfg in animas_cfg.items() if cfg.supervisor == current)
    return descendants
