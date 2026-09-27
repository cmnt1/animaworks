"""SSoT compliance tests for the per-task ``model`` override.

The model override's single source of truth is the pending task_desc and the
task queue entry meta (``meta.model``), **not** a field on the canonical
TaskBoard row / external-task projection schemas.  These models must still
load legacy JSON without a ``model`` key, and the SSoT propagation paths
(queue meta -> pending task_desc) must carry the model through.
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from core.schemas import TaskEntry
from core.tasks.board.models import BoardColumn, BoardRow
from core.tasks.external.models import ExternalTask


def _entry(**overrides) -> TaskEntry:
    fields = {
        "task_id": "abc123",
        "ts": "2026-01-01T00:00:00+00:00",
        "source": "anima",
        "original_instruction": "do the thing",
        "assignee": "anima",
        "status": "blocked",
        "summary": "thing",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    fields.update(overrides)
    return TaskEntry(**fields)


def _board_row(**overrides):
    fields = {
        "anima_name": "a",
        "task_id": "t1",
        "canonical_task_id": "t1",
        "queue_status": "pending",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "column": BoardColumn.TODO,
        "visibility": "active",
    }
    fields.update(overrides)
    return BoardRow(**fields)


class TestExternalTaskNoModelField:
    def test_loads_without_model_field(self):
        # Legacy JSON (without any model key) must still parse cleanly.
        data = {
            "id": "github-pr-42",
            "title": "Fix bug",
            "status": "open",
            "source_type": "github",
            "source_icon": "gh",
            "created_at": "2026-01-01T00:00:00+00:00",
            "last_updated_at": "2026-01-01T00:00:00+00:00",
            "priority": 1,
        }
        task = ExternalTask.model_validate(data)
        assert task.id == "github-pr-42"

    def test_model_is_not_a_schema_field(self):
        # The ``model`` key is no longer part of the ExternalTask schema
        # (the SSoT is the task queue meta + pending task_desc).
        assert "model" not in ExternalTask.model_fields


class TestBoardRowNoModelField:
    def test_loads_without_model_field(self):
        row = _board_row()
        assert row.task_id == "t1"

    def test_model_is_not_a_schema_field(self):
        # SSoT is the pending task_desc + queue meta, not a TaskBoard row field.
        assert "model" not in BoardRow.model_fields

    def test_meta_carries_model_through(self):
        # The canonical row keeps the model in ``meta``, as a plain value.
        row = _board_row(meta={"model": "claude-opus"})
        assert row.meta["model"] == "claude-opus"
