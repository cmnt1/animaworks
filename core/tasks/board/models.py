"""Pydantic models for the single TaskBoard view (read straight from TaskStore)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class BoardColumn(StrEnum):
    """Display columns for TaskBoard."""

    TODO = "todo"
    RUNNING = "running"
    WAITING = "waiting"
    DONE = "done"


class BoardRow(BaseModel):
    """One row in the unified TaskBoard view, derived from the canonical task."""

    anima_name: str
    task_id: str
    canonical_task_id: str
    assignee: str | None = None
    source: str | None = None
    summary: str | None = None
    original_instruction: str | None = None
    queue_status: str
    relay_chain: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    updated_at: str
    column: BoardColumn
    visibility: Literal["active", "archived"]
    waiting: bool = False
    lease: dict | None = None
