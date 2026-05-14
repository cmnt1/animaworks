"""Formatting helpers for TaskBoard prompt sections."""

from __future__ import annotations

from core.taskboard.models import BoardTask


def format_tasks_for_priming(board_tasks: list[BoardTask], budget_tokens: int = 400) -> str:
    """Format projected tasks in the compact Channel E style."""
    max_chars = budget_tokens * 4
    lines: list[str] = []
    total = 0

    for task in board_tasks:
        priority = "🔴 HIGH" if task.source == "human" else "⚪"
        status_icon = "🔄" if task.queue_status == "in_progress" else "📋"
        summary = task.summary or task.original_instruction or task.task_id
        assignee = task.assignee or task.anima_name
        line = f"- {status_icon} {priority} [{task.task_id[:8]}] {summary} (assignee: {assignee})"
        if task.queue_status and task.queue_status not in {"pending", "in_progress"}:
            line += f" status: {task.queue_status}"
        if task.relay_chain:
            line += f" chain: {' -> '.join(task.relay_chain)}"
        if task.deadline:
            line += f" deadline: {task.deadline}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line) + 1

    return "\n".join(lines)
