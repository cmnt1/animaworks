# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Read Obsidian Projects DB task metadata for meeting setup."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path

from core.reports.pending_review_surfacer import _demojibake, _looks_mojibake

DEFAULT_OBSIDIAN_VAULT = Path(r"E:\OneDriveBiz\Obsidian")
PROJECTS_DIR = Path("_notes") / "Projects"
COMPLETED_STATUS = "完了"
DEPARTMENT_ORDER = ("一般", "文芸", "会計", "不動産", "投資", "経営", "アフィリエイト")


@dataclass(frozen=True)
class ProjectTask:
    """A selectable task from Obsidian Projects DB."""

    department: str
    task_code: str
    title: str
    status: str
    note_path: str
    note_name: str
    current_work: str = ""
    next_action: str = ""
    corrupt: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize for API responses."""
        return asdict(self)


def get_obsidian_vault_root() -> Path:
    """Return the configured Obsidian vault root."""
    value = os.environ.get("ANIMAWORKS_OBSIDIAN_VAULT") or os.environ.get("OBSIDIAN_VAULT")
    return Path(value) if value else DEFAULT_OBSIDIAN_VAULT


def list_project_tasks(vault_root: Path | None = None, *, include_completed: bool = False) -> list[ProjectTask]:
    """List task records from Obsidian Projects DB Markdown frontmatter."""
    root = Path(vault_root) if vault_root is not None else get_obsidian_vault_root()
    projects_dir = root / PROJECTS_DIR
    if not projects_dir.exists():
        return []

    tasks: list[ProjectTask] = []
    for path in projects_dir.glob("*.md"):
        props = _read_frontmatter(path)
        if not props:
            continue
        task_code = props.get("タスクコード", "").strip()
        department = props.get("カテゴリ", "").strip()
        if not task_code or not department:
            # A cp932-corrupted note has mojibaked keys (カテゴリ → 繧ｫ繝･ざ繝ｪ), so the
            # real keys read empty and the note would silently drop out of the
            # meeting picker. Surface it as a flagged entry instead of skipping.
            if _looks_corrupt(props):
                recovered = _recover_props(props)
                tasks.append(
                    ProjectTask(
                        department=recovered.get("カテゴリ", "").strip(),
                        task_code=recovered.get("タスクコード", "").strip(),
                        title=recovered.get("タスク名", "").strip() or path.stem,
                        status=recovered.get("ステータス", "").strip(),
                        note_path=str(path),
                        note_name=path.name,
                        corrupt=True,
                    )
                )
            continue
        status = props.get("ステータス", "").strip()
        if not include_completed and status == COMPLETED_STATUS:
            continue
        title = props.get("タスク名", "").strip() or path.stem
        tasks.append(
            ProjectTask(
                department=department,
                task_code=task_code,
                title=title,
                status=status,
                note_path=str(path),
                note_name=path.name,
                current_work=props.get("今週タスク", "").strip(),
                next_action=props.get("当面の作業", "").strip(),
            )
        )

    return sorted(tasks, key=_task_sort_key)


def grouped_project_tasks(vault_root: Path | None = None, *, include_completed: bool = False) -> dict[str, object]:
    """Return tasks plus department groupings for the meeting setup UI."""
    tasks = list_project_tasks(vault_root, include_completed=include_completed)
    departments = sorted({task.department for task in tasks if not task.corrupt}, key=_department_sort_key)
    return {
        "departments": departments,
        "tasks": [task.to_dict() for task in tasks],
    }


def _looks_corrupt(props: dict[str, str]) -> bool:
    """True if any frontmatter key/value shows cp932 mojibake or decode loss."""
    for key, value in props.items():
        if "�" in key or "�" in value:
            return True
        if _looks_mojibake(key) or _looks_mojibake(value):
            return True
    return False


def _recover_props(props: dict[str, str]) -> dict[str, str]:
    """Best-effort cp932-double-encoding recovery of each key and value."""
    recovered: dict[str, str] = {}
    for key, value in props.items():
        recovered_key = _demojibake(key) or key
        recovered[recovered_key] = _demojibake(value) or value
    return recovered


def _read_frontmatter(path: Path) -> dict[str, str]:
    try:
        # Tolerate cp932-corrupted notes: decode with replacement instead of
        # raising so the corruption can be detected and surfaced downstream.
        text = path.read_bytes().decode("utf-8-sig", errors="replace")
    except OSError:
        return {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    props: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = _clean_scalar(value.strip())
        if key:
            props[key] = value
    return props


def _clean_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _department_sort_key(department: str) -> tuple[int, str]:
    try:
        return (DEPARTMENT_ORDER.index(department), department)
    except ValueError:
        return (len(DEPARTMENT_ORDER), department)


def _task_sort_key(task: ProjectTask) -> tuple[int, str, str]:
    department_order, _ = _department_sort_key(task.department)
    return (department_order, task.task_code, task.title)
