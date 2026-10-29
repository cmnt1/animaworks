"""Shared runtime state passed to ToolHandler mixin delegates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ToolContext:
    """Small, explicit context shared by ToolHandler mixins during migration."""

    anima_dir: Path
    anima_name: str
    check_command_permission: Callable[[str], str | None]
    task_cwd: Path | None = None
