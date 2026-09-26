from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unified activity log: writing, replay, timelines, rotation and formatting.

The main names are re-exported lazily, so importing a submodule does not
load the whole package.
"""

import importlib
from typing import Any

__all__ = [
    "ActivityLogger",
    "activity_context_from_trigger",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        return getattr(importlib.import_module("core.memory.activity.logger"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
