from __future__ import annotations

from pathlib import Path

from server.project_tasks import grouped_project_tasks, list_project_tasks


def _write_project_note(projects_dir: Path, name: str, frontmatter: str) -> None:
    projects_dir.mkdir(parents=True, exist_ok=True)
    (projects_dir / f"{name}.md").write_text(f"---\n{frontmatter}\n---\n\nbody\n", encoding="utf-8")


def test_list_project_tasks_reads_projects_db_frontmatter(tmp_path: Path):
    projects_dir = tmp_path / "_notes" / "Projects"
    _write_project_note(
        projects_dir,
        "ブログ立ち上げ機械",
        "\n".join(
            [
                "タスク名: ブログ立ち上げ機械",
                "カテゴリ: アフィリエイト",
                "ステータス: 進行中",
                "タスクコード: AFF-012",
                "当面の作業: 1本通す",
            ]
        ),
    )

    tasks = list_project_tasks(tmp_path)

    assert len(tasks) == 1
    assert tasks[0].department == "アフィリエイト"
    assert tasks[0].task_code == "AFF-012"
    assert tasks[0].title == "ブログ立ち上げ機械"
    assert tasks[0].next_action == "1本通す"


def test_list_project_tasks_excludes_completed_by_default(tmp_path: Path):
    projects_dir = tmp_path / "_notes" / "Projects"
    _write_project_note(
        projects_dir,
        "done",
        "\n".join(
            [
                "タスク名: 完了済み",
                "カテゴリ: 一般",
                "ステータス: 完了",
                "タスクコード: GEN-001",
            ]
        ),
    )

    assert list_project_tasks(tmp_path) == []
    assert len(list_project_tasks(tmp_path, include_completed=True)) == 1


def test_list_project_tasks_surfaces_cp932_corrupt_note(tmp_path: Path):
    projects_dir = tmp_path / "_notes" / "Projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    clean = (
        "---\n"
        "タスク名: 群像 投稿準備\n"
        "カテゴリ: 文芸\n"
        "ステータス: 進行中\n"
        "タスクコード: Ships 2\n"
        "---\n\nbody\n"
    )
    # Reproduce the cp932 double-encoding: UTF-8 bytes misread as cp932, then the
    # mojibake string stored back to disk (カテゴリ → 繧ｫ繝･ざ繝ｪ).
    mojibake = clean.encode("utf-8").decode("cp932", errors="replace")
    (projects_dir / "bungei.md").write_text(mojibake, encoding="utf-8")

    tasks = list_project_tasks(tmp_path)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.corrupt is True
    assert task.note_name == "bungei.md"
    # best-effort recovery; falls back to the (clean) filename / "" when lossy
    assert task.department in ("文芸", "")
    assert task.title in ("群像 投稿準備", "bungei")

    # a corrupt note must not pollute the clean department list
    assert grouped_project_tasks(tmp_path)["departments"] == []


def test_grouped_project_tasks_returns_departments_and_tasks(tmp_path: Path):
    projects_dir = tmp_path / "_notes" / "Projects"
    _write_project_note(projects_dir, "finance", "タスク名: NBO\nカテゴリ: 投資\nステータス: 進行中\nタスクコード: FIN-017")
    _write_project_note(projects_dir, "general", "タスク名: 基盤\nカテゴリ: 一般\nステータス: 未着手\nタスクコード: GEN-012")

    data = grouped_project_tasks(tmp_path)

    assert data["departments"] == ["一般", "投資"]
    assert [task["task_code"] for task in data["tasks"]] == ["GEN-012", "FIN-017"]
